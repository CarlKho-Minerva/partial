"""Meta Model API, through the OpenAI-compatible chat completions endpoint."""
from __future__ import annotations

import os

BASE_URL = "https://api.meta.ai/v1"
DEFAULT_MODEL = os.environ.get("PARTIAL_MODEL", "muse-spark-1.3")


def client():
    from openai import OpenAI
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise SystemExit("MODEL_API_KEY is not set. Create one at dev.meta.ai (API keys) and put it in .env")
    return OpenAI(base_url=BASE_URL, api_key=key)


def chat(messages, tools, model=DEFAULT_MODEL, **kw):
    # Only tool_choice "auto" is accepted by the Meta Model API.
    return client().chat.completions.create(model=model, messages=messages, tools=tools,
                                            tool_choice="auto", **kw)
