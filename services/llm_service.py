"""The ONE place that talks to Groq. Every node calls structured_call() or text_call() from here,
so models, retries, caching and rate-limit handling live in a single file."""
import hashlib
import re
import time

from groq import RateLimitError
from langchain_groq import ChatGroq

from config import GROQ_API_KEY, LLM_MODEL, LLM_MODEL_FAST


class RateLimited(Exception):
    pass


_cache = {}     # same prompt + same schema -> reuse the answer, no new API call
_clients = {}   # one client per model, created once


def _client(fast):
    model = LLM_MODEL_FAST if fast else LLM_MODEL
    if model not in _clients:
        _clients[model] = ChatGroq(model=model, api_key=GROQ_API_KEY, temperature=0)
    return _clients[model]


def _wait_seconds(error):
    """Groq tells us how long to wait, e.g. 'Please try again in 7.5s' or 'in 1m2.3s'."""
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(error))
    if not m:
        return 15.0
    return int(m.group(1) or 0) * 60 + float(m.group(2))


def _invoke(runnable, prompt, retries):
    last_error = None
    for attempt in range(retries):
        try:
            return runnable.invoke(prompt)
        except RateLimitError as e:
            # per-DAY limit: waiting won't help today
            if "per day" in str(e).lower():
                raise RateLimited("Daily AI usage limit reached. Please try again tomorrow.")
            # per-MINUTE limit: wait as long as Groq asks, then retry
            wait = _wait_seconds(e)
            if wait > 60 or attempt == retries - 1:
                raise RateLimited("The AI is busy right now (per-minute limit). Please try again in a minute.")
            time.sleep(wait + 1)
            last_error = e
        except Exception as e:
            last_error = e
            time.sleep(1 + attempt)   # wait 1s, 2s, 3s before retrying
    raise last_error


def structured_call(schema, prompt, fast=False, retries=3):
    """LLM call that must return a pydantic object matching `schema`."""
    key = hashlib.sha256(f"{schema.__name__}|{fast}|{prompt}".encode()).hexdigest()
    if key in _cache:
        return _cache[key]
    structured = _client(fast).with_structured_output(schema, method="json_schema")
    result = _invoke(structured, prompt, retries)
    _cache[key] = result
    return result


def text_call(prompt, fast=False, retries=3):
    """Plain LLM call that returns text."""
    return _invoke(_client(fast), prompt, retries).content