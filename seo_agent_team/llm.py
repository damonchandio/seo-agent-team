"""Model calls. One function, call(), so you can swap the model for anything you like:

    from seo_agent_team import llm
    llm.backend = lambda system, user, max_tokens, temperature: my_model(system, user)

By default it talks to any OpenAI-compatible chat endpoint (settings.LLM_BASE_URL), which covers Groq, Gemini's
OpenAI endpoint, OpenRouter and a local Ollama. Free tiers limit tokens per minute, so a 429 is waited out (as long
as the server asks) and retried.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Callable

import requests

from . import settings

log = logging.getLogger("seo_agent_team")
backend: Callable[[str, str, int, float], str] | None = None


class LLMError(RuntimeError):
    pass


def _openai(system: str, user: str, max_tokens: int, temperature: float) -> str:
    url = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    body = {"model": settings.LLM_MODEL, "temperature": temperature, "max_tokens": min(max_tokens, settings.LLM_MAX_TOKENS),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if "gpt-oss" in settings.LLM_MODEL:
        body["reasoning_effort"] = "low"   # keep thinking short so the token budget goes on the article
    headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"} if settings.LLM_API_KEY else {}
    for attempt in range(3):
        try:
            r = requests.post(url, json=body, headers=headers, timeout=600)
        except requests.RequestException as e:
            raise LLMError(f"can't reach the model ({type(e).__name__})") from e
        if r.status_code == 400 and "reasoning" in r.text.lower() and "reasoning_effort" in body:
            body.pop("reasoning_effort")   # a model without that setting
            continue
        if r.status_code == 429 and attempt < 2:
            try:
                wait = float(r.headers.get("retry-after") or 30)
            except ValueError:
                wait = 30
            if wait > 120:   # a daily limit, not a per-minute one: don't hang for hours
                raise LLMError(f"the model's free limit is used up for now (retry after {wait:.0f}s)")
            log.info("model busy (429), waiting %.0fs", wait)
            time.sleep(wait)
            continue
        if r.status_code != 200:
            raise LLMError(f"model error {r.status_code}: {r.text[:200]}")
        msg = ((r.json().get("choices") or [{}])[0].get("message") or {})
        text = re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=re.S).strip()
        if not text:
            raise LLMError("the model sent an empty answer")
        return text
    raise LLMError("the model kept refusing")


def call(system: str, user: str, max_tokens: int = 4000, temperature: float = 0.4) -> str:
    return (backend or _openai)(system, user, max_tokens, temperature)


def parse_json(text: str):
    """The first JSON object or array in a reply (models wrap it in prose or code fences)."""
    t = re.sub(r"```(?:json)?", "", text or "").strip()
    starts = [i for i in (t.find("{"), t.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON in the model's reply")
    return json.JSONDecoder().raw_decode(t[min(starts):])[0]
