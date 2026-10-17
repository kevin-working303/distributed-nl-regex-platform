"""Generator falls back to deterministic heuristics when no API key is set
(the test env forces ANTHROPIC_API_KEY=""). Redis may be absent — the client
degrades to no-cache, so these run standalone."""
import re

import pytest

from apps.common.exceptions import ValidationError
from apps.llm.generator import generate_spec


def test_email_heuristic_replace():
    spec = generate_spec("replace", "find email addresses", ["Email"])
    assert spec["operation"] == "replace"
    assert spec["source"] in ("heuristic", "cache")
    # The generated pattern should actually match an email.
    assert re.search(spec["pattern"], "john.doe@example.com")


def test_phone_heuristic():
    spec = generate_spec("replace", "match phone numbers", ["Phone"])
    assert re.search(spec["pattern"], "+1 (415) 555-2671")


def test_extract_operation():
    spec = generate_spec("extract", "extract the URL", ["Notes"])
    assert spec["operation"] == "extract"
    assert re.search(spec["pattern"], "see https://example.org/path")


def test_standardize_returns_rules():
    spec = generate_spec("standardize", "normalize whitespace", ["Name"])
    assert spec["operation"] == "standardize"
    assert isinstance(spec["rules"], list) and spec["rules"]


def test_unknown_description_without_llm_raises():
    with pytest.raises(ValidationError):
        generate_spec("replace", "something totally unmatchable xyzzy", ["Col"])


def test_unknown_operation_raises():
    with pytest.raises(ValidationError):
        generate_spec("frobnicate", "emails", ["Col"])
