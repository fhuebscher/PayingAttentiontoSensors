import math

import pytest

from obsplacement.gate_driver.errors import PathAlreadyExists
from obsplacement.gate_driver.json_io import read_json, write_json, write_new_json


def test_write_json_is_canonical_sorted_indented_with_trailing_newline(tmp_path):
    path = tmp_path / "nested" / "doc.json"
    write_json(path, {"b": 2, "a": 1})
    text = path.read_text()
    assert text.endswith("\n")
    assert text.index('"a"') < text.index('"b"')  # sort_keys
    assert "\n  " in text  # indent=2


def test_write_json_creates_parent_directories(tmp_path):
    path = tmp_path / "a" / "b" / "c" / "doc.json"
    write_json(path, {"x": 1})
    assert path.is_file()


def test_write_json_rejects_nan(tmp_path):
    path = tmp_path / "doc.json"
    with pytest.raises(ValueError):
        write_json(path, {"x": float("nan")})
    assert not path.exists()


def test_read_json_round_trips(tmp_path):
    path = tmp_path / "doc.json"
    document = {"kind": "gate-plan", "runs": [1, 2, 3], "ok": True}
    write_json(path, document)
    assert read_json(path) == document


def test_write_json_overwrites_unconditionally(tmp_path):
    path = tmp_path / "doc.json"
    write_json(path, {"version": 1})
    write_json(path, {"version": 2})
    assert read_json(path) == {"version": 2}


def test_write_new_json_refuses_to_overwrite_a_prior_gate_document(tmp_path):
    """Non-negotiable property #5: refuse to overwrite prior gate documents
    rather than silently replacing them."""
    path = tmp_path / "gate-plan.json"
    write_new_json(path, {"approvedBy": "Florian Huebscher", "decision": "approve-exact-plan"})
    with pytest.raises(PathAlreadyExists):
        write_new_json(path, {"approvedBy": "Florian Huebscher", "decision": "a-different-decision"})
    # The original document must be untouched by the failed second write.
    assert read_json(path)["decision"] == "approve-exact-plan"


def test_write_new_json_refuses_a_dangling_symlink_via_o_excl(tmp_path):
    """Section 2.4: `write_new_json` now uses `os.open(O_CREAT | O_EXCL)`
    directly rather than a separate `exists()` check followed by a write --
    POSIX guarantees O_EXCL fails on a pre-existing symlink regardless of
    whether its target exists, closing the check-then-write TOCTOU gap a
    concurrent `mv` onto the path could otherwise land in."""
    target = tmp_path / "gate-plan.json"
    target.symlink_to(tmp_path / "nowhere")
    with pytest.raises(PathAlreadyExists):
        write_new_json(target, {"decision": "approve-exact-plan"})


def test_write_new_json_output_is_byte_identical_to_write_json(tmp_path):
    """The O_EXCL refactor must not change the on-disk format every existing
    reader of these files expects (indent=2, sort_keys, trailing newline)."""
    a = tmp_path / "via-write-json.json"
    b = tmp_path / "via-write-new-json.json"
    document = {"b": 2, "a": 1, "nested": {"z": 9, "y": 8}}
    write_json(a, document)
    write_new_json(b, document)
    assert a.read_bytes() == b.read_bytes()
