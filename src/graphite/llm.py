"""The one place any pipeline talks to the model.

Same model for every tier, set in .env. Retries through Groq's rate limits,
and counts tokens and calls per case, since both go in the answer files and
token efficiency is scored.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from openai import APIStatusError, OpenAI, RateLimitError

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MODEL = os.environ.get("LLM_MODEL") or "openai/gpt-oss-120b"
_client = OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1")


@dataclass
class Usage:
    tokens: int = 0
    calls: int = 0
    tool_calls: int = 0
    seconds: float = 0.0
    log: list = field(default_factory=list)


def _wait_from(err):
    """Seconds to wait from Groq's 'try again in 12m56.7s' / '4.2s' / '350ms'."""
    m = re.search(r"try again in ([\d.]+ms|(?:\d+h)?(?:\d+m)?(?:[\d.]+s)?)", str(err))
    if not m or not m.group(1):
        return 10.0
    text = m.group(1)
    if text.endswith("ms"):
        return float(text[:-2]) / 1000
    total = 0.0
    for n, unit in re.findall(r"([\d.]+)([hms])", text):
        total += float(n) * {"h": 3600, "m": 60, "s": 1}[unit]
    return total or 10.0


def chat(messages, usage, tools=None, json_mode=False, max_tokens=1500):
    kwargs = {"model": MODEL, "messages": messages, "temperature": 0, "max_tokens": max_tokens,
              "reasoning_effort": "low"}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(12):
        start = time.time()
        try:
            r = _client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            wait = _wait_from(e)
            # The daily token cap is a rolling window and the error says when
            # enough frees up. Wait out gaps under half an hour so long runs
            # keep moving unattended; give up only on longer waits.
            if ("per day" in str(e).lower() or "TPD" in str(e)) and wait > 1800:
                raise
            time.sleep(wait + 1)
            continue
        except APIStatusError as e:
            if e.status_code >= 500 and attempt < 11:
                time.sleep(2 ** min(attempt, 5))
                continue
            raise
        usage.seconds += time.time() - start
        usage.calls += 1
        usage.tokens += r.usage.total_tokens
        usage.log.append({"prompt": r.usage.prompt_tokens, "completion": r.usage.completion_tokens})
        return r.choices[0].message
    raise RuntimeError("rate limited through 12 retries")


def parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])
