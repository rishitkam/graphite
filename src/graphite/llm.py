"""The one place any pipeline talks to the model.

Same model for every tier, set in .env. Retries through Groq's rate limits,
and counts tokens and calls per case, since both go in the answer files and
token efficiency is scored.
"""

import json
import os
import re
import time
from types import SimpleNamespace
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MODEL = os.environ.get("LLM_MODEL") or "openai/gpt-oss-120b"
# Several free-tier keys can be listed (GROQ_API_KEY, GROQ_API_KEY_2, ...).
# When one hits its daily cap the run moves to the next rather than waiting.
_KEYS = [os.environ[k] for k in sorted(os.environ) if re.fullmatch(r"GROQ_API_KEY(_\d+)?", k) and os.environ[k]]
_clients = [OpenAI(api_key=k, base_url="https://api.groq.com/openai/v1") for k in _KEYS]
_current = 0


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

    global _current
    rotations = 0
    for attempt in range(20 + len(_clients)):
        start = time.time()
        try:
            r = _clients[_current].chat.completions.create(**kwargs)
        except RateLimitError as e:
            wait = _wait_from(e)
            if ("per day" in str(e).lower() or "TPD" in str(e)) and wait > 60 and rotations < len(_clients) - 1:
                # Try the next key; once every key has said no, fall through
                # and wait for the soonest one instead of spinning.
                _current = (_current + 1) % len(_clients)
                rotations += 1
                continue
            # The daily token cap is a rolling window and the error says when
            # enough frees up. Wait out gaps under half an hour so long runs
            # keep moving unattended; give up only on longer waits.
            if ("per day" in str(e).lower() or "TPD" in str(e)) and wait > 1800:
                raise
            time.sleep(wait + 1)
            continue
        except APIConnectionError:
            # Timeouts and dropped connections: nothing wrong with the request.
            time.sleep(2 ** min(attempt, 5))
            continue
        except APIStatusError as e:
            # Strict JSON mode rejects small slips (the model once wrote "0. nine"
            # for a probability). Retry without it; parse_json copes with the text.
            if e.status_code == 400 and "json_validate_failed" in str(e) and "response_format" in kwargs:
                kwargs.pop("response_format")
                kwargs["temperature"] = 0.3
                continue
            # Sometimes the model wraps its final answer in a tool call to a
            # made-up tool ("json"). Groq rejects that, but the answer is in the
            # error. Take it as the plain reply it was meant to be.
            if e.status_code == 400 and "tool_use_failed" in str(e):
                body = e.body if isinstance(e.body, dict) else {}
                gen = body.get("failed_generation") or (body.get("error") or {}).get("failed_generation") or ""
                try:
                    args = json.loads(gen).get("arguments")
                except (ValueError, AttributeError):
                    args = None
                if isinstance(args, dict) and "fraud_probability" in args:
                    usage.calls += 1
                    return SimpleNamespace(content=json.dumps(args), tool_calls=None)
                kwargs["temperature"] = 0.3
                continue
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
