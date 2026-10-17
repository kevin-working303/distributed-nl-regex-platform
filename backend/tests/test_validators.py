import pytest

from apps.common.exceptions import RegexValidationError
from apps.llm.validators import validate_pattern


def test_valid_email_pattern():
    vp = validate_pattern(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b", probe=False)
    assert vp.pattern.startswith(r"\b")


def test_invalid_regex_rejected():
    with pytest.raises(RegexValidationError):
        validate_pattern("(unclosed", probe=False)


def test_empty_pattern_rejected():
    with pytest.raises(RegexValidationError):
        validate_pattern("   ", probe=False)


def test_catastrophic_backtracking_rejected():
    # Classic nested-quantifier ReDoS shape.
    with pytest.raises(RegexValidationError):
        validate_pattern(r"(a+)+$", probe=False)


def test_overlapping_alternation_rejected():
    with pytest.raises(RegexValidationError):
        validate_pattern(r"(a|a)*", probe=False)


def test_overlong_pattern_rejected():
    with pytest.raises(RegexValidationError):
        validate_pattern("a" * 1001, probe=False)
