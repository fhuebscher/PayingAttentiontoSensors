"""Abort-time evidence preservation for blocked candidate cells.

A blocked terminal validation must leave a byte-complete quarantine copy of
the attempted output root so the entire validation can be replayed offline;
three one-shot campaigns died to gates that could not be diagnosed after the
abort settled.
"""
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def _load(relative: str, name: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


campaign = _load(
    "modules/teastore/execution/performance_campaign.py",
    "blocked_evidence_campaign_tests",
)


def _populate_output(root: Path) -> dict[str, bytes]:
    contents = {
        "receipt.json": b'{"run": {"runId": "run-1"}}\n',
        "auth.log": b"token-bridge line\n",
        "journey-ledger.jsonl": b'{"opaqueToken": "t1"}\n',
        "traces.json": b"[]\n",
        "candidate-validation.json": b'{"verdict": "blocked"}\n',
        ".operational/collector.stderr": b"correlation summary\n",
        ".operational/kieker-amqp.spool": b"\x00\x01raw-spool-bytes",
    }
    for name, payload in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return contents


def test_preserves_complete_quarantine_copy_with_manifest(tmp_path: Path):
    output = tmp_path / "runs" / "no-fault-cost" / "b01-01-selected"
    output.mkdir(parents=True)
    contents = _populate_output(output)
    error = RuntimeError("candidate scientific validation blocked: unsupported")

    quarantine = campaign.preserve_blocked_evidence(
        output, error, run_id="run-1",
        run_key={"regime": "no-fault-cost", "posture": "selected"},
    )

    assert quarantine == output.parent / (
        output.name + campaign.BLOCKED_EVIDENCE_SUFFIX)
    for name, payload in contents.items():
        assert (quarantine / name).read_bytes() == payload
    manifest = json.loads(
        (quarantine / "blocked-evidence-manifest.json").read_text())
    assert manifest["kind"] == "teastore-candidate-blocked-evidence-v1"
    assert manifest["runId"] == "run-1"
    assert manifest["runKey"]["posture"] == "selected"
    assert manifest["errorType"] == "RuntimeError"
    assert "validation blocked" in manifest["error"]
    listed = {entry["path"] for entry in manifest["preservedFiles"]}
    assert listed == set(contents)
    for entry in manifest["preservedFiles"]:
        assert entry["bytes"] == len(contents[entry["path"]])
    # The original evidence root is untouched.
    for name, payload in contents.items():
        assert (output / name).read_bytes() == payload


def test_never_overwrites_an_existing_quarantine(tmp_path: Path):
    output = tmp_path / "b01-01-selected"
    output.mkdir()
    _populate_output(output)
    first = campaign.preserve_blocked_evidence(output, RuntimeError("first"))
    marker = first / "blocked-evidence-manifest.json"
    original = marker.read_bytes()

    second = campaign.preserve_blocked_evidence(output, RuntimeError("second"))

    assert second == first
    assert marker.read_bytes() == original


def test_missing_output_root_is_a_noop(tmp_path: Path):
    assert campaign.preserve_blocked_evidence(
        tmp_path / "absent", RuntimeError("boom")) is None


def test_producer_abort_path_preserves_and_reraises(tmp_path: Path, monkeypatch):
    """execute_candidate_cell quarantines evidence before propagating an abort."""
    output = tmp_path / "runs" / "no-fault-cost" / "b01-01-selected"
    contract = {
        "runId": "run-1",
        "runKey": {"regime": "no-fault-cost", "block": 1, "posture": "selected",
                   "attempt": 1},
        "ordinalPosition": 1,
        "campaignId": "campaign-1",
        "runtimeInputs": {"imageDigests": {}},
    }
    monkeypatch.setattr(
        campaign, "_validate_candidate_contract", lambda document: document)

    def blocked_slice(root, run_id, posture, args, *, expected_image_references):
        _populate_output(output)
        raise RuntimeError("candidate scientific validation blocked: unsupported")

    monkeypatch.setattr(
        campaign, "_execute_candidate_runtime_slice", blocked_slice)
    monkeypatch.setattr(
        campaign, "_candidate_args",
        lambda contract, output: None,
    )

    with pytest.raises(RuntimeError, match="validation blocked"):
        campaign.execute_candidate_cell(contract, output)

    quarantine = output.parent / (output.name + campaign.BLOCKED_EVIDENCE_SUFFIX)
    assert (quarantine / "auth.log").read_bytes() == b"token-bridge line\n"
    assert (quarantine / ".operational/kieker-amqp.spool").exists()
    manifest = json.loads(
        (quarantine / "blocked-evidence-manifest.json").read_text())
    assert manifest["runId"] == "run-1"
    # The producer's own contract still holds: the attempted root remains.
    assert (output / "auth.log").is_file()
