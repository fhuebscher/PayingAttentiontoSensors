import pytest

from obsplacement.gate_driver.hashing import canonical_sha256


def test_deterministic_for_identical_content():
    document = {"a": 1, "b": [1, 2, 3], "c": {"nested": True}}
    assert canonical_sha256(document) == canonical_sha256(dict(document))


def test_independent_of_key_order():
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


def test_sensitive_to_content_changes():
    assert canonical_sha256({"a": 1}) != canonical_sha256({"a": 2})


def test_sensitive_to_key_renaming():
    assert canonical_sha256({"a": 1}) != canonical_sha256({"aa": 1})


def test_rejects_nan():
    with pytest.raises(ValueError):
        canonical_sha256({"a": float("nan")})


def test_returns_hex_sha256():
    digest = canonical_sha256({"a": 1})
    assert len(digest) == 64
    int(digest, 16)  # must be valid hex
