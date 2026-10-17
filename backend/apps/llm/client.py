"""Thin wrapper around the Anthropic Claude API + a Redis prompt cache.

Design goals:
  * Identical natural-language prompts never hit the LLM twice — the generated
    spec is cached in Redis keyed by a hash of (operation, description).
  * The app degrades gracefully: if no ANTHROPIC_API_KEY is configured (or the
    call fails), we fall back to a deterministic heuristic generator that
    covers the common pattern classes (emails, phones, URLs, …). This keeps the
    whole pipeline testable and demo-able without an API key.
"""
from __future__ import annotations

import hashlib
import json
import logging

import redis
from django.conf import settings

logger = logging.getLogger("apps.llm")

_redis_client: redis.Redis | None = None


def _cache() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


def _cache_key(operation: str, description: str, columns: list[str]) -> str:
    raw = json.dumps(
        {"op": operation, "desc": description.strip().lower(), "cols": sorted(columns)},
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"llm:spec:{digest}"


def get_cached_spec(operation: str, description: str, columns: list[str]) -> dict | None:
    try:
        raw = _cache().get(_cache_key(operation, description, columns))
    except redis.RedisError:
        logger.warning("Redis cache read failed; proceeding without cache.")
        return None
    return json.loads(raw) if raw else None


def set_cached_spec(operation: str, description: str, columns: list[str], spec: dict) -> None:
    try:
        _cache().set(
            _cache_key(operation, description, columns),
            json.dumps(spec, separators=(",", ":")),
            ex=settings.LLM_CACHE_TTL_SECONDS,
        )
    except redis.RedisError:
        logger.warning("Redis cache write failed; continuing.")


def llm_available() -> bool:
    return bool(settings.ANTHROPIC_API_KEY)


def _extract_json(text: str) -> dict:
    """Parse a JSON object out of the model's response, tolerating stray prose
    or code fences around it."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the first {...} block.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise RuntimeError("LLM did not return parseable JSON.")


def call_claude(system: str, user: str) -> dict:
    """Call Claude and return the parsed JSON object from its response.

    Kept intentionally to the basic Messages API surface (model, max_tokens,
    system, messages) so it works across SDK versions; the system prompt
    instructs the model to return JSON only. Raises on any failure so the
    caller can fall back to the heuristic generator.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if getattr(response, "stop_reason", None) == "refusal":
        raise RuntimeError("LLM refused the request.")
    text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
    if not text:
        raise RuntimeError("LLM returned no content.")
    return _extract_json(text)
