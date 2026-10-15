"""Abort-time evidence quarantine and the declared posture ceiling (D6).

A blocked Hotel cell loses its Docker-side state to the owned
``compose down -v`` in ``run_cell``'s ``finally``, and a cell blocked at
terminal validation never receives a content manifest.  The Jaeger capture,
the normalized traces, the application log and the correlation document are
then the only diagnosis surface left, so they must be quarantined before any
cleanup layer observes the abort -- the pattern that let the sibling SUT
diagnose its seventh gate offline instead of spending another one-shot.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/hotel-reservation"


def load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runtime = load(
    "hotel_blocked_evidence_runtime",
    "modules/hotel-reservation/execution/candidate_runtime.py",
)
cell = load(
    "hotel_blocked_evidence_cell",
    "modules/hotel-reservation/execution/candidate_cell.py",
)
terminal = load(
    "hotel_blocked_evidence_terminal",
    "modules/hotel-reservation/validation/candidate_terminal.py",
)


def _populate_run_root(root: Path) -> dict[str, bytes]:
    contents = {
        "cell-contract.json": b'{"runId": "no-fault-cost-b01-full-a01"}\n',
        "opportunity-ledger.jsonl": b'{"opaqueToken": "t1"}\n',
        "application.log": b"frontend | OBSPLACEMENT_WITNESS {}\n",
        "jaeger-raw.json": b'{"queries": []}\n',
        "traces-normalized.json": b'{"events": []}\n',
        "correlation.json": b'{"rows": []}\n',
        "cpu.json": b'{"project": "hotel_candidate_v4_deadbeef_01"}\n',
        "emissions.json": b'{"eventCount": 0}\n',
        "logs/compose-up.log": b"attaching to frontend\n",
    }
    for name, payload in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return contents


def test_quarantine_is_byte_complete_and_leaves_the_run_root_untouched(tmp_path: Path):
    run_root = tmp_path / "runs" / "cost" / "b01" / "p01-full" / "attempt-01"
    run_root.mkdir(parents=True)
    contents = _populate_run_root(run_root)
    error = RuntimeError("full posture has no source-emitted sampled spans")

    quarantine = cell.preserve_blocked_evidence(
        run_root, error, run_id="no-fault-cost-b01-full-a01",
        run_key={"regime": "no-fault-cost", "posture": "full", "attempt": 1},
    )

    assert quarantine == run_root.parent / (
        run_root.name + cell.BLOCKED_EVIDENCE_SUFFIX
    )
    for name, payload in contents.items():
        assert (quarantine / name).read_bytes() == payload
    manifest = json.loads((quarantine / cell.BLOCKED_EVIDENCE_MANIFEST).read_text())
    assert manifest["kind"] == "hotel-candidate-blocked-evidence-v1"
    assert manifest["runId"] == "no-fault-cost-b01-full-a01"
    assert manifest["runKey"]["posture"] == "full"
    assert manifest["errorType"] == "RuntimeError"
    assert "sampled spans" in manifest["error"]
    assert manifest["promotionAuthorized"] is False
    listed = {row["path"] for row in manifest["preservedFiles"]}
    assert listed == set(contents)
    for row in manifest["preservedFiles"]:
        assert row["bytes"] == len(contents[row["path"]])
    # The attempted evidence itself is never mutated by preservation.
    assert {
        path.relative_to(run_root).as_posix()
        for path in run_root.rglob("*") if path.is_file()
    } == set(contents)
    for name, payload in contents.items():
        assert (run_root / name).read_bytes() == payload


def test_preserved_files_carry_a_per_file_sha256(tmp_path: Path):
    """Section 3.5: a per-file sha256 lets the quarantine copy's integrity be
    verified independently later, without re-trusting the byte count alone."""
    run_root = tmp_path / "attempt-01"
    run_root.mkdir()
    contents = _populate_run_root(run_root)

    quarantine = cell.preserve_blocked_evidence(run_root, RuntimeError("boom"))

    manifest = json.loads((quarantine / cell.BLOCKED_EVIDENCE_MANIFEST).read_text())
    by_path = {row["path"]: row for row in manifest["preservedFiles"]}
    assert set(by_path) == set(contents)
    for name, payload in contents.items():
        assert by_path[name]["sha256"] == hashlib.sha256(payload).hexdigest()
        # Also verifiable against the quarantined copy directly, not just the
        # in-memory fixture payload -- the point of the field.
        assert by_path[name]["sha256"] == hashlib.sha256((quarantine / name).read_bytes()).hexdigest()


def test_quarantine_is_idempotent_and_never_overwrites(tmp_path: Path):
    run_root = tmp_path / "attempt-01"
    run_root.mkdir()
    _populate_run_root(run_root)
    first = cell.preserve_blocked_evidence(run_root, RuntimeError("first"))
    manifest = first / cell.BLOCKED_EVIDENCE_MANIFEST
    original = manifest.read_bytes()

    second = cell.preserve_blocked_evidence(run_root, RuntimeError("second"))

    assert second == first
    assert manifest.read_bytes() == original
    assert not (tmp_path / (first.name + ".tmp")).exists()


def test_absent_or_non_directory_run_root_is_a_noop(tmp_path: Path):
    assert cell.preserve_blocked_evidence(tmp_path / "absent", RuntimeError("x")) is None
    regular = tmp_path / "regular"
    regular.write_text("not a directory")
    assert cell.preserve_blocked_evidence(regular, RuntimeError("x")) is None


def test_preservation_failure_never_masks_the_original_abort(tmp_path: Path, monkeypatch):
    run_root = tmp_path / "attempt-01"
    run_root.mkdir()
    _populate_run_root(run_root)

    def explode(*_args, **_kwargs):
        raise OSError("planted quarantine failure")

    monkeypatch.setattr(cell, "preserve_blocked_evidence", explode)
    abort = RuntimeError("original terminal gate abort")
    assert cell._quarantine_blocked_cell(
        run_root, {"runId": "r1", "runKey": {"posture": "full"}}, abort,
    ) is None
    notes = getattr(abort, "__notes__", [])
    assert any("blocked-evidence preservation failed" in note for note in notes)


def test_run_cell_quarantines_before_the_owned_docker_teardown(tmp_path: Path, monkeypatch):
    """The quarantine must observe the abort before cleanup, not after."""
    order: list[str] = []
    run_root = tmp_path / "attempt-01"

    def fake_preserve(root, error, *, run_id=None, run_key=None):
        order.append("quarantine")
        return Path(str(root) + cell.BLOCKED_EVIDENCE_SUFFIX)

    monkeypatch.setattr(cell, "preserve_blocked_evidence", fake_preserve)

    # Model run_cell's control flow: the producer body raises, the abort is
    # quarantined, and only then does the owned teardown in the finally run.
    def body() -> None:
        try:
            raise RuntimeError("planted producer defect")
        except BaseException as failure:
            cell._quarantine_blocked_cell(run_root, {"runId": "r1", "runKey": {}}, failure)
            raise
        finally:
            order.append("owned-cleanup")

    with pytest.raises(RuntimeError):
        body()
    assert order == ["quarantine", "owned-cleanup"]


def test_run_cell_source_orders_quarantine_ahead_of_cleanup():
    """Pin the real control flow, not only the model above."""
    source = (MODULE / "execution/candidate_cell.py").read_text()
    body = source.split("def run_cell(", 1)[1].split("\ndef ", 1)[0]
    quarantine_at = body.index("_quarantine_blocked_cell")
    cleanup_at = body.index("_owned_cleanup(source, contract, environment)")
    assert quarantine_at < cleanup_at
    # The terminal-validation stage is quarantined too, after cleanup has run.
    assert body.count("_quarantine_blocked_cell") == 2
    assert body.index("terminal.validate_cell") < body.rindex("_quarantine_blocked_cell")


# --------------------------------------------------------------------------
# D6: the unsupported-posture claim ceiling is declared policy, not a literal.
# --------------------------------------------------------------------------


def test_policy_declares_the_posture_ceiling_and_the_plan_binding_reads_it():
    ceiling = runtime.posture_ceiling()
    # Hotel `selected` ceiling (2026-09-29): logs + sampler, then the frontend tracer, then every tracer.
    assert ceiling["supportedPostures"] == ["none", "metrics", "selected", "full"]
    assert "sample-zero" not in ceiling["supportedPostures"]
    assert "logs" not in ceiling["supportedPostures"]
    assert runtime.unsupported_posture_ids(ceiling) == ["source-off"]
    assert ceiling["sourceCostComparisonState"] == "unsupported"
    declared = json.loads((MODULE / "execution/runtime-policy.json").read_text())
    assert declared["postureCeiling"] == ceiling
    # The ceiling is nowhere restated as a literal in the runtime or terminal
    # validators; both derive it from the one declared source.
    for relative in (
        "execution/candidate_runtime.py", "validation/candidate_terminal.py",
    ):
        text = (MODULE / relative).read_text()
        assert '"none", "selected", "source-off"' not in text
        assert "unsupported=none,selected,source-off" not in text


def test_gate_plan_text_and_binding_derive_the_ceiling_from_policy():
    ceiling = runtime.posture_ceiling()
    bindings = runtime.Bindings(
        framework_commit="a" * 40, framework_tree="b" * 40,
        descriptor_sha256="c" * 64, compiled_plan_sha256="d" * 64,
        runtime_policy_sha256="e" * 64,
        controller_sha256={name: "f" * 64 for name in runtime.CONTROLLER_PATHS},
        run_count=24,
        unsupported_postures=tuple(runtime.unsupported_posture_ids(ceiling)),
        source_cost_comparison_state=ceiling["sourceCostComparisonState"],
    )
    binding = runtime.plan_binding(bindings)
    assert binding["unsupportedPostures"] == ["source-off"]
    assert binding["sourceCostComparisonState"] == "unsupported"
    text = runtime.expected_gate_plan_text(bindings)
    assert text.endswith("unsupported=source-off,source-cost")
    assert f" cells={bindings.run_count} " in text  # the sentence carries the bound run count, not a literal

    # A different declared ceiling changes the typed sentence: the gate is
    # rebound by policy, not by editing the validator.
    narrowed = dataclasses.replace(bindings, unsupported_postures=("none", "selected"))
    assert runtime.expected_gate_plan_text(narrowed).endswith(
        "unsupported=none,selected,source-cost"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"supportedPostures": ["full", "sample-zero", "none", "selected"]},
        {"sourceCostComparisonState": "supported"},
        {"sourceCostUnsupportedReason": "sample-zero-is-source-off"},
        {"unsupportedPostures": [{"id": "none", "state": "unsupported", "numericValue": 0}]},
        {"unsupportedPostures": [{"id": "none", "state": "supported", "numericValue": None}]},
        {"unsupportedPostures": []},
        {"unsupportedReason": ""},
    ],
)
def test_policy_validator_fails_closed_on_a_malformed_ceiling(mutation: dict):
    document = json.loads((MODULE / "execution/runtime-policy.json").read_text())
    document["postureCeiling"] = {**document["postureCeiling"], **mutation}
    with pytest.raises(runtime.GateError):
        runtime._validate_policy(document)


def test_policy_validator_requires_the_declared_ceiling():
    document = json.loads((MODULE / "execution/runtime-policy.json").read_text())
    document.pop("postureCeiling")
    with pytest.raises(runtime.GateError):
        runtime._validate_policy(document)


def test_terminal_validator_reads_the_ceiling_from_declared_policy(monkeypatch):
    ceiling = terminal.posture_ceiling()
    assert ceiling == runtime.posture_ceiling()
    narrowed = {
        **ceiling,
        "unsupportedPostures": [
            {"id": "none", "state": "unsupported", "numericValue": None},
        ],
    }
    monkeypatch.setattr(terminal.runtime_policy, "posture_ceiling", lambda: narrowed)
    document = {
        "posture": "full", "scenario": None, "offered": 1200,
        "sourceCostComparison": {
            "state": "unsupported", "numericValue": None,
            "reason": "sample-zero-is-not-source-off",
        },
        "unsupportedPostures": ceiling["unsupportedPostures"],
        "rows": [{"state": "supported", "phase": "pre"}],
    }
    contract = {"runKey": {"posture": "full"}, "fault": None}
    # The retained producer document still claims the wider ceiling, so the
    # replay fails closed against the narrowed declared policy.
    with pytest.raises(terminal.TerminalError):
        terminal._correlation(document, document, contract)


def test_terminal_validator_refuses_a_posture_outside_the_declared_ceiling(monkeypatch):
    ceiling = terminal.posture_ceiling()
    monkeypatch.setattr(
        terminal.runtime_policy, "posture_ceiling",
        lambda: {**ceiling, "supportedPostures": ["sample-zero"]},
    )
    document = {"posture": "full"}
    with pytest.raises(terminal.TerminalError):
        terminal._correlation(document, document, {"runKey": {"posture": "full"}, "fault": None})


def test_declared_ceiling_must_match_the_frozen_compiled_plan(monkeypatch):
    """A ceiling that drifts from the digest-pinned plan is a governance defect."""
    document = json.loads((MODULE / "execution/runtime-policy.json").read_text())
    document["postureCeiling"] = {
        **document["postureCeiling"],
        "unsupportedPostures": [
            {"id": "none", "state": "unsupported", "numericValue": None},
        ],
        # Kept internally consistent with the narrowed unsupported set so the
        # claim-ceiling check passes and the assertion actually under test is
        # the plan-versus-ceiling comparison, not a malformed-ceiling reject.
        "prohibitedClaims": [
            "none-posture-comparison", "placement-lattice-nesting",
        ],
    }
    monkeypatch.setattr(runtime, "_json_file", lambda *_args, **_kwargs: document)
    monkeypatch.setattr(runtime, "_verify_git", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        runtime, "_git_state",
        lambda: runtime.GitState(
            commit="a" * 40, tree="b" * 40, commit_tree="b" * 40, dirty=False,
            status=b"", concealment=b"", index_concealment=(),
        ),
    )
    with pytest.raises(runtime.GateError):
        runtime.inspect_bindings("a" * 40)


# --------------------------------------------------------------------------
# D6: the claim ceiling -- what a Hotel campaign may never be used to argue.
# --------------------------------------------------------------------------


def _policy() -> dict:
    return json.loads((MODULE / "execution/runtime-policy.json").read_text())


def test_policy_declares_what_hotel_evidence_may_never_claim():
    """Hotel backs the ladder's contrasts only, never a placement-lattice nesting.

    ``source-off`` is unsupported rather than untested: the entry point is always
    woven and upstream ships no service-level source guard.  ``selected`` is a
    tracer-level placement (frontend only), not source-off.  So the ceiling is a
    property of the SUT, and it has to be machine-checked rather than remembered.
    """
    ceiling = runtime.posture_ceiling()
    # Each adjacent step of the ladder, the tracer-on step over metrics, and the end-to-end contrast.
    assert ceiling["admissibleContrasts"] == [
        ["none", "metrics"], ["metrics", "selected"], ["selected", "full"],
        ["metrics", "full"], ["none", "full"],
    ]
    assert ceiling["prohibitedClaims"] == [
        "placement-lattice-nesting",
        "source-off-posture-comparison",
    ]
    # Every unsupported posture is named as a forbidden comparison, and the
    # lattice claim is forbidden outright -- a lattice needs the rungs this SUT
    # cannot express, so no Hotel cell count can ever supply one.
    for identifier in runtime.unsupported_posture_ids(ceiling):
        assert "{0}-posture-comparison".format(identifier) in ceiling["prohibitedClaims"]
    assert runtime.LATTICE_NESTING_CLAIM in ceiling["prohibitedClaims"]
    # Every admissible member is a supported posture, so the only contrasts the
    # policy permits are the ones the campaign exists to measure.
    assert all(
        value in ceiling["supportedPostures"]
        for row in ceiling["admissibleContrasts"] for value in row
    )
    assert _policy()["postureCeiling"] == ceiling


def test_claim_ceiling_rides_inside_the_gate_plan_policy_digest():
    """Re-scoping the ceiling moves runtimePolicyCanonicalSha256, so the
    GATE-PLAN text and every receipt commit to it by digest, not by prose."""
    policy = _policy()
    baseline = runtime.canonical_sha256(policy)
    widened = _policy()
    widened["postureCeiling"]["prohibitedClaims"] = [
        value for value in policy["postureCeiling"]["prohibitedClaims"]
        if value != runtime.LATTICE_NESTING_CLAIM
    ]
    assert runtime.canonical_sha256(widened) != baseline
    # And the widened document does not merely hash differently, it is refused.
    with pytest.raises(runtime.GateError):
        runtime._validate_policy(widened)


@pytest.mark.parametrize(
    "mutation",
    [
        # Dropping the lattice prohibition would silently re-admit the nesting
        # claim that this SUT structurally cannot support.
        {"prohibitedClaims": [
            "none-posture-comparison", "selected-posture-comparison",
            "source-off-posture-comparison",
        ]},
        # Forgetting one unsupported posture re-admits that comparison.
        {"prohibitedClaims": [
            "none-posture-comparison", "placement-lattice-nesting",
            "selected-posture-comparison",
        ]},
        # Forbidding a supported posture would gut the only admissible contrast.
        {"prohibitedClaims": [
            "full-posture-comparison", "none-posture-comparison",
            "placement-lattice-nesting", "selected-posture-comparison",
            "source-off-posture-comparison",
        ]},
        {"prohibitedClaims": []},
        {"prohibitedClaims": "placement-lattice-nesting"},
        # Unsorted or duplicated entries defeat byte-exact review of the policy.
        {"prohibitedClaims": [
            "placement-lattice-nesting", "none-posture-comparison",
            "selected-posture-comparison", "source-off-posture-comparison",
        ]},
        {"prohibitedClaims": [
            "none-posture-comparison", "none-posture-comparison",
            "placement-lattice-nesting", "selected-posture-comparison",
            "source-off-posture-comparison",
        ]},
        # An unsupported posture may never appear in an admissible contrast.
        {"admissibleContrasts": [["full", "logs"]]},
        {"admissibleContrasts": [["full", "source-off"]]},
        # A contrast must be a distinct, non-repeated pair.
        {"admissibleContrasts": [["full", "full"]]},
        {"admissibleContrasts": [["full", "sample-zero"], ["sample-zero", "full"]]},
        {"admissibleContrasts": [["full", "sample-zero", "none"]]},
        {"admissibleContrasts": [["full"]]},
        {"admissibleContrasts": []},
        {"admissibleContrasts": ["full-vs-sample-zero"]},
    ],
)
def test_policy_validator_fails_closed_on_a_widened_claim_ceiling(mutation):
    document = _policy()
    document["postureCeiling"] = {**document["postureCeiling"], **mutation}
    with pytest.raises(runtime.GateError):
        runtime._validate_policy(document)


def test_claim_ceiling_is_coupled_to_the_supported_posture_set():
    """Narrowing the supported set invalidates a contrast naming the dropped
    posture, so the two halves of the ceiling cannot drift apart."""
    document = _policy()
    document["postureCeiling"] = {
        **document["postureCeiling"], "supportedPostures": ["full"],
    }
    with pytest.raises(runtime.GateError):
        runtime._validate_policy(document)


def test_terminal_replay_also_enforces_the_claim_ceiling(monkeypatch):
    """The ceiling is read through the same validated accessor on the replay
    path, so an offline terminal replay cannot see a widened ceiling."""
    # Control: the declared policy itself replays cleanly through this seam, so
    # the rejection below is the mutation and not the monkeypatch.
    monkeypatch.setattr(terminal.runtime_policy, "_json_file", lambda *a, **k: _policy())
    assert terminal.posture_ceiling() == runtime.posture_ceiling()

    document = _policy()
    document["postureCeiling"]["admissibleContrasts"] = [["full", "source-off"]]
    monkeypatch.setattr(terminal.runtime_policy, "_json_file", lambda *a, **k: document)
    with pytest.raises(terminal.TerminalError, match="admissible contrast"):
        terminal.posture_ceiling()
