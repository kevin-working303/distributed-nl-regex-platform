"""Regex safety + validity checks.

Two concerns:
  1. The pattern must compile.
  2. It must not be vulnerable to catastrophic backtracking (ReDoS), which
     would hang a Spark executor on adversarial input.

Spark's ``regexp_replace`` uses java.util.regex, which — like Python's ``re`` —
backtracks. We validate with Python ``re`` (close enough for the common classes
of pattern we generate) plus a structural heuristic that rejects the nested-
quantifier shapes responsible for exponential blow-up, and a runtime timeout
probe against a pathological input.
"""
from __future__ import annotations

import re
import signal
from dataclasses import dataclass

from apps.common.exceptions import RegexValidationError

# Hard cap: absurdly long patterns are almost always a mistake / attack.
MAX_PATTERN_LENGTH = 1000

# Structural red flags for catastrophic backtracking:
#   (a+)+   (a*)*   (a+)*   (.*)*   (a|a)*   nested quantified groups
_NESTED_QUANTIFIER = re.compile(
    r"""
    \(                      # group open
    [^)]*                   # group body
    [+*]                    # quantifier inside the group
    [^)]*
    \)
    [+*]                    # quantifier applied to the whole group
    """,
    re.VERBOSE,
)

# Overlapping alternation under a quantifier, e.g. (a|a)+ or (\d|\d)*
_OVERLAP_ALT = re.compile(r"\([^)]*\|[^)]*\)[+*]")


@dataclass(frozen=True)
class ValidatedPattern:
    pattern: str
    flags: int = 0


def _looks_catastrophic(pattern: str) -> bool:
    return bool(_NESTED_QUANTIFIER.search(pattern) or _OVERLAP_ALT.search(pattern))


class _Timeout(Exception):
    pass


def _runtime_probe(pattern: str, timeout_seconds: int = 1) -> None:
    """Run the compiled pattern against a known-pathological string under a
    wall-clock timeout. Only effective on POSIX (uses SIGALRM); on platforms
    without it we skip the probe and rely on the structural heuristic.

    This runs inside the Celery worker (Linux container), where SIGALRM works.
    """
    if not hasattr(signal, "SIGALRM"):
        return

    adversarial = "a" * 40 + "!"  # classic ReDoS trigger for nested quantifiers

    def _handler(signum, frame):
        raise _Timeout()

    old = signal.signal(signal.SIGALRM, _handler)
    try:
        signal.alarm(timeout_seconds)
        try:
            re.compile(pattern).search(adversarial)
        except _Timeout:
            raise RegexValidationError(
                "Pattern is too slow (possible catastrophic backtracking)."
            )
        finally:
            signal.alarm(0)
    finally:
        signal.signal(signal.SIGALRM, old)


def validate_pattern(pattern: str, *, probe: bool = True) -> ValidatedPattern:
    """Validate a regex; raise RegexValidationError if unsafe or invalid."""
    if not pattern or not pattern.strip():
        raise RegexValidationError("Empty pattern.")
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise RegexValidationError(
            f"Pattern exceeds the maximum length of {MAX_PATTERN_LENGTH} characters."
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise RegexValidationError(f"Invalid regular expression: {exc}")

    if _looks_catastrophic(pattern):
        raise RegexValidationError(
            "Pattern contains nested quantifiers prone to catastrophic backtracking."
        )

    if probe:
        _runtime_probe(pattern)

    return ValidatedPattern(pattern=pattern)
