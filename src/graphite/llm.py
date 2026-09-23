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
    m = re.search(r"try again in ([\d.]+)(ms|s|m)", str(err))
    if not m:
        return 10.0
    n, unit = float(m.group(1)), m.group(2)
    return n / 1000 if unit == "ms" else n * 60 if unit == "m" else n


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
            if "per day" in str(e).lower() or "TPD" in str(e) or "RPD" in str(e):
                raise
            time.sleep(_wait_from(e) + 0.5)
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
