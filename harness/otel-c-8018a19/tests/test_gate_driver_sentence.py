import pytest

from obsplacement.gate_driver.sentence import SentenceMismatch, verify_typed_sentence


def test_exact_match_returns_expected():
    expected = "APPROVE GATE-PLAN study=x plan=abc123"
    assert verify_typed_sentence(expected, expected) == expected


def test_surrounding_whitespace_is_stripped_before_comparison():
    expected = "APPROVE GATE-PLAN study=x plan=abc123"
    assert verify_typed_sentence(f"  {expected}\n", expected) == expected


def test_internal_whitespace_is_not_normalized():
    expected = "APPROVE GATE-PLAN study=x  plan=abc123"
    with pytest.raises(SentenceMismatch):
        verify_typed_sentence("APPROVE GATE-PLAN study=x plan=abc123", expected)


def test_mismatch_raises_with_both_strings_preserved():
    expected = "APPROVE GATE-RUN campaign=teastore-candidate-pilot-v1 deadline=2026-09-04T12:00:00Z"
    typed = "APPROVE GATE-RUN campaign=teastore-candidate-pilot-v1 deadline=2026-09-04T13:00:00Z"
    with pytest.raises(SentenceMismatch) as excinfo:
        verify_typed_sentence(typed, expected)
    assert excinfo.value.expected == expected
    assert excinfo.value.typed == typed


def test_never_authors_or_repairs_a_sentence():
    """verify_typed_sentence must be a pure comparison: given a bad typed
    string, it never returns anything derived from `typed` -- it only ever
    returns `expected` on success or raises on failure."""
    expected = "APPROVE GATE-SETUP setupId=abc deadline=2026-09-04T12:00:00Z"
    with pytest.raises(SentenceMismatch):
        verify_typed_sentence("APPROVE GATE-SETUP setupId=abc deadline=2026-09-04T99:99:99Z", expected)
    # A near-miss (case difference) is still a hard failure, not a fuzzy accept.
    with pytest.raises(SentenceMismatch):
        verify_typed_sentence(expected.lower(), expected)


def test_empty_typed_input_fails_closed():
    with pytest.raises(SentenceMismatch):
        verify_typed_sentence("", "APPROVE GATE-PLAN study=x plan=abc123")
    with pytest.raises(SentenceMismatch):
        verify_typed_sentence("   ", "APPROVE GATE-PLAN study=x plan=abc123")
