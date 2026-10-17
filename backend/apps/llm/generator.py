"""Natural-language → transformation spec.

Three operations, all executed through the same async/Spark pipeline:

  * ``replace``     — find a pattern and replace matches with a fixed value
                      (the core requirement).
  * ``extract``     — pull the matched text (or a capture group) into a NEW
                      column (creative transform #1).
  * ``standardize`` — normalize a column by applying an ordered list of
                      regex → replacement rules the LLM derives from the
                      description, e.g. "standardize US phone numbers to
                      (XXX) XXX-XXXX" (creative transform #2).

Each operation produces a spec (a plain dict, so it serializes cleanly through
Celery/Redis). Every regex in a spec is run through ``validators.validate_pattern``
before it is returned, guarding against invalid regexes and ReDoS.
"""
from __future__ import annotations

import logging
import re

from apps.common.exceptions import ValidationError

from . import client
from .validators import validate_pattern

logger = logging.getLogger("apps.llm")

OPERATIONS = ("replace", "extract", "standardize")

# --- Heuristic fallback library ---------------------------------------------
# Maps keyword triggers -> a known-good regex. Used when no API key is set or
# the LLM call fails, so common requests still work end-to-end.
_HEURISTICS: list[tuple[tuple[str, ...], str]] = [
    (("email", "e-mail", "mail address"),
     r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b"),
    (("phone", "telephone", "mobile", "cell"),
     r"\+?\d{0,3}[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}"),
    (("url", "link", "website", "http"),
     r"https?://[^\s/$.?#].[^\s]*"),
    (("ip address", "ipv4", "ip"),
     r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    (("ssn", "social security"),
     r"\b\d{3}-\d{2}-\d{4}\b"),
    (("credit card", "card number"),
     r"\b(?:\d[ -]*?){13,16}\b"),
    (("zip", "postal code", "zipcode"),
     r"\b\d{5}(?:-\d{4})?\b"),
    (("date",),
     r"\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b"),
    (("number", "digit", "numeric"),
     r"\d+"),
    (("whitespace", "spaces", "extra space"),
     r"\s+"),
]


def _heuristic_pattern(description: str) -> str | None:
    text = description.lower()
    for triggers, pattern in _HEURISTICS:
        if any(t in text for t in triggers):
            return pattern
    return None


# --- LLM prompt / schema ----------------------------------------------------
_SYSTEM = (
    "You translate a user's natural-language description of a text pattern into "
    "a single valid regular expression using standard (PCRE/Java-compatible) "
    "syntax that also works with Python's re module. Do not anchor to the whole "
    "string unless the user asks. Prefer a concise, safe pattern; never use "
    "nested quantifiers like (a+)+ that cause catastrophic backtracking.\n"
    'Respond with ONLY a JSON object, no prose and no code fences: '
    '{"pattern": "<regex>", "explanation": "<one sentence>"}'
)

_STANDARDIZE_SYSTEM = (
    "You translate a user's description of how to standardize/normalize a text "
    "column into an ORDERED list of find/replace rules. Each rule has a regex "
    "'pattern' (PCRE/Java/Python-compatible) and a 'replacement' string that may "
    "reference capture groups as $1, $2, ... (Java/Spark style). Keep patterns "
    "safe — never nested quantifiers. Use 1-6 rules applied top to bottom.\n"
    'Respond with ONLY a JSON object, no prose and no code fences: '
    '{"rules": [{"pattern": "<regex>", "replacement": "<str>", "description": "<str>"}], '
    '"explanation": "<one sentence>"}'
)


def _generate_single_pattern(description: str, columns: list[str]) -> dict:
    """Return {pattern, explanation, source} for replace/extract."""
    if client.llm_available():
        try:
            user = (
                f"Columns available: {columns}\n"
                f"Describe the pattern to match: {description}"
            )
            result = client.call_claude(_SYSTEM, user)
            return {
                "pattern": result["pattern"],
                "explanation": result.get("explanation", ""),
                "source": "llm",
            }
        except Exception as exc:  # noqa: BLE001 - fall back to heuristic
            logger.warning("LLM regex generation failed (%s); using heuristic.", exc)

    pattern = _heuristic_pattern(description)
    if pattern is None:
        raise ValidationError(
            "Could not derive a pattern from the description. "
            "Try naming a known entity (email, phone, URL, number, date, …) "
            "or configure an ANTHROPIC_API_KEY for free-form descriptions."
        )
    return {"pattern": pattern, "explanation": "Heuristic match.", "source": "heuristic"}


def _generate_standardize_rules(description: str, columns: list[str]) -> dict:
    if client.llm_available():
        try:
            user = (
                f"Columns available: {columns}\n"
                f"Describe the standardization: {description}"
            )
            result = client.call_claude(_STANDARDIZE_SYSTEM, user)
            return {
                "rules": result["rules"],
                "explanation": result.get("explanation", ""),
                "source": "llm",
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM standardize generation failed (%s); using heuristic.", exc)

    # Heuristic: collapse runs of whitespace and trim — a universally-safe
    # normalization when the LLM is unavailable.
    return {
        "rules": [{"pattern": r"\s+", "replacement": " ", "description": "Collapse whitespace."}],
        "explanation": "Heuristic whitespace normalization.",
        "source": "heuristic",
    }


def generate_spec(operation: str, description: str, columns: list[str]) -> dict:
    """Produce a validated, cacheable transformation spec.

    Checks the Redis cache first, then the LLM (or heuristic), validates every
    regex, and caches the result.
    """
    if operation not in OPERATIONS:
        raise ValidationError(f"Unknown operation '{operation}'. Use one of {OPERATIONS}.")

    cached = client.get_cached_spec(operation, description, columns)
    if cached is not None:
        cached["source"] = "cache"
        return cached

    if operation in ("replace", "extract"):
        spec = _generate_single_pattern(description, columns)
        validate_pattern(spec["pattern"])
        spec["operation"] = operation
    else:  # standardize
        spec = _generate_standardize_rules(description, columns)
        for rule in spec["rules"]:
            validate_pattern(rule["pattern"])
        spec["operation"] = operation

    client.set_cached_spec(operation, description, columns, spec)
    return spec
