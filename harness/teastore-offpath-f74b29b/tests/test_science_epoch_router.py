from __future__ import annotations

import copy
import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ROUTER = _module("validate_science_epochs", "tools/validate_science_epochs.py")
CONSTRUCTION = _module(
    "validate_openspec_construction_root_test",
    "tools/validate_openspec_construction.py",
)


def registry() -> dict:
    return json.loads((ROOT / ROUTER.REGISTRY_PATH).read_text(encoding="utf-8"))


def _markers(root: Path, change_ids: tuple[str, ...]) -> None:
    for change_id in change_ids:
        target = root / "openspec" / "changes" / change_id
        target.mkdir(parents=True)
        (target / ".openspec.yaml").write_text(
            "schema: scientific-change\n", encoding="utf-8"
        )


def test_root_registry_schema_bytes_and_all_code_owned_bindings_are_exact() -> None:
    value = registry()
    assert ROUTER.validate_registry(ROOT, value) == []
    assert value["permissions"] == ROUTER.EXPECTED_PERMISSIONS


def test_root_registry_rejects_parent_tree_schema_validator_and_observation_drift() -> None:
    mutations = []

    wrong_parent = copy.deepcopy(registry())
    wrong_parent["transition"]["parentTree"] = "0" * 40
    mutations.append(wrong_parent)

    wrong_schema = copy.deepcopy(registry())
    wrong_schema["epochs"][1]["schema"]["sha256"] = "0" * 64
    mutations.append(wrong_schema)

    wrong_validator = copy.deepcopy(registry())
    wrong_validator["epochs"][1]["validator"]["sha256"] = "0" * 64
    mutations.append(wrong_validator)

    false_observation = copy.deepcopy(registry())
    false_observation["epochs"][1]["diagnosticObservations"][0][
        "manifestSha256"
    ] = "0" * 64
    mutations.append(false_observation)

    omitted_source = copy.deepcopy(registry())
    omitted_source["epochs"][1]["sourceBindings"].pop()
    mutations.append(omitted_source)

    source_tamper = copy.deepcopy(registry())
    source_tamper["epochs"][1]["supersessions"][0][
        "successorSourceSha256"
    ] = "0" * 64
    mutations.append(source_tamper)

    prefix_tamper = copy.deepcopy(registry())
    prefix_tamper["epochs"][1]["supersessions"][-1]["predecessorLength"] += 1
    mutations.append(prefix_tamper)

    transition_extension = copy.deepcopy(registry())
    transition_extension["transition"]["ownedPaths"].append("unowned/root.py")
    mutations.append(transition_extension)

    for planted in mutations:
        assert ROUTER.validate_registry(ROOT, planted, pin_bytes=False)


def _successor_manifest(value: dict, transition: str) -> tuple[dict, dict]:
    epoch = next(item for item in value["epochs"] if item["id"] == ROUTER.V2_EPOCH_ID)
    observations = [
        {
            "campaignId": item["campaignId"],
            "terminalStatus": item["terminalStatus"],
            "manifestSha256": item["manifestSha256"],
            "qualification": "diagnostic-only",
            "canonical": False,
            "candidateCellEligible": False,
        }
        for item in epoch["diagnosticObservations"]
    ]
    return epoch, {
        "parentEpoch": {
            "changeId": epoch["parent"]["changeId"],
            "commit": epoch["parent"]["commit"],
            "tree": epoch["parent"]["tree"],
        },
        "pathOwnership": {
            "baseCommit": transition,
            "allowed": copy.deepcopy(epoch["allowedPaths"]),
        },
        "sourceBindings": copy.deepcopy(epoch["sourceBindings"]),
        "diagnosticObservations": observations,
    }


def test_child_cannot_extend_paths_or_omit_a_root_owned_source_binding() -> None:
    transition = "a" * 40
    epoch, manifest = _successor_manifest(registry(), transition)
    assert ROUTER.successor_manifest_contract_errors(manifest, epoch, transition) == []

    manifest["pathOwnership"]["allowed"].append("unregistered/new.py")
    assert any(
        "allowed path set" in error
        for error in ROUTER.successor_manifest_contract_errors(
            manifest, epoch, transition
        )
    )
    manifest["pathOwnership"]["allowed"] = copy.deepcopy(epoch["allowedPaths"])
    manifest["sourceBindings"].pop()
    assert any(
        "source bindings" in error
        for error in ROUTER.successor_manifest_contract_errors(
            manifest, epoch, transition
        )
    )


def test_malformed_child_allowed_paths_returns_a_typed_failure(monkeypatch) -> None:
    transition = ROUTER.PARENT_COMMIT
    epoch, manifest = _successor_manifest(registry(), transition)
    manifest["pathOwnership"]["allowed"] = None
    monkeypatch.setattr(ROUTER, "load_json", lambda _path: manifest)

    errors = ROUTER._v2_route_errors(ROOT, epoch, transition)

    assert "v2 pathOwnership.allowed is not a list" in errors


def test_every_active_marker_routes_exactly_once(tmp_path: Path) -> None:
    value = registry()
    all_changes = ROUTER.V1_CHANGE_IDS + ROUTER.V2_CHANGE_IDS
    _markers(tmp_path, all_changes)

    routes, errors = ROUTER.route_markers(tmp_path, value)
    assert errors == []
    assert routes == {
        ROUTER.V1_EPOCH_ID: list(ROUTER.V1_CHANGE_IDS),
        ROUTER.V2_EPOCH_ID: list(ROUTER.V2_CHANGE_IDS),
    }


def test_router_rejects_unknown_duplicate_and_missing_required_successor(
    tmp_path: Path,
) -> None:
    value = registry()
    _markers(tmp_path, ROUTER.V1_CHANGE_IDS + ROUTER.V2_CHANGE_IDS)

    unknown = tmp_path / "openspec" / "changes" / "unregistered-v3"
    unknown.mkdir()
    (unknown / ".openspec.yaml").write_text(
        "schema: scientific-change\n", encoding="utf-8"
    )
    _, errors = ROUTER.route_markers(tmp_path, value)
    assert any("no root-owned route" in error for error in errors)
    (unknown / ".openspec.yaml").unlink()

    duplicate = copy.deepcopy(value)
    duplicate["epochs"][0]["changeIds"].append(ROUTER.V2_CHANGE_IDS[0])
    _, errors = ROUTER.route_markers(tmp_path, duplicate)
    assert any("exactly once" in error for error in errors)

    (tmp_path / "openspec" / "changes" / ROUTER.V2_CHANGE_IDS[0] / ".openspec.yaml").unlink()
    _, errors = ROUTER.route_markers(tmp_path, value)
    assert any("required epoch" in error for error in errors)


def test_root_transition_commit_is_derived_and_its_delivery_is_exact() -> None:
    transition, errors = ROUTER.derive_transition_commit(ROOT, registry())
    if (ROOT / "tools/validate_science_epochs_v3.py").is_file():
        # v3 replays this exact v2 transition from bb29cf.  In the current tree
        # the v2 root-owned wrapper/test bytes are intentionally superseded by
        # the separately committed v3 router, so the old current-tree derivation
        # must no longer pretend it is authoritative.
        assert transition is None
        assert any("not introduced by one transition commit" in item for item in errors)
        return
    assert errors == []
    assert transition is not None and transition != ROUTER.PARENT_COMMIT


def _write_findings(root: Path, reviewer: str, status: str) -> None:
    findings = root / "findings" / f"{CONSTRUCTION.CHANGE_ID}.csv"
    findings.parent.mkdir(parents=True, exist_ok=True)
    artifact = root / "artifact.txt"
    artifact.write_text("reviewed\n", encoding="utf-8")
    with findings.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(CONSTRUCTION.FINDINGS_HEADER)
        writer.writerow(
            (
                "F-ROUTER-001",
                CONSTRUCTION.CHANGE_ID,
                reviewer,
                "DECISION",
                "major",
                status,
                "artifact.txt",
                "summary",
                "evidence",
                "disposition",
            )
        )


def test_root_owned_successor_findings_vocabulary_is_watched(tmp_path: Path) -> None:
    _write_findings(tmp_path, "fresh-subagent", "resolved")
    relative = f"findings/{CONSTRUCTION.CHANGE_ID}.csv"
    assert CONSTRUCTION.findings_errors(tmp_path, relative) == []

    _write_findings(tmp_path, "adversarial-subagent", "resolved")
    assert any(
        "reviewer_context" in error
        for error in CONSTRUCTION.findings_errors(tmp_path, relative)
    )
    _write_findings(tmp_path, "fresh-subagent", "accepted")
    assert any(
        "status" in error for error in CONSTRUCTION.findings_errors(tmp_path, relative)
    )


def test_construction_observation_checker_rejects_a_false_manifest_hash() -> None:
    clean = {
        "diagnosticObservations": copy.deepcopy(CONSTRUCTION.EXPECTED_OBSERVATIONS),
        "claimCeiling": "diagnostic-harness-adoption",
    }
    assert CONSTRUCTION.check_observations(ROOT, clean).status == "pass"
    clean["diagnosticObservations"][0]["manifestSha256"] = "0" * 64
    assert CONSTRUCTION.check_observations(ROOT, clean).status == "fail"


def test_protocol_module_mismatch_fails_before_any_child_import(
    tmp_path: Path, monkeypatch,
) -> None:
    module_path = tmp_path / "modules/teastore/execution/candidate_pilot.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text("raise RuntimeError('planted import side effect')\n", encoding="utf-8")
    invoked = False

    def watched(_root: Path):
        nonlocal invoked
        invoked = True
        raise AssertionError("child import was reached")

    monkeypatch.setattr(CONSTRUCTION, "_candidate_module", watched)
    result = CONSTRUCTION.check_protocol(tmp_path, {}, "0" * 64)
    assert result.status == "fail"
    assert any("root-owned pin" in error for error in result.errors)
    assert invoked is False


def test_router_passes_the_root_protocol_pin_to_construction(monkeypatch) -> None:
    epoch = next(
        item for item in registry()["epochs"] if item["id"] == ROUTER.V2_EPOCH_ID
    )
    captured = {}

    class Validator:
        @staticmethod
        def validate_repository(_root: Path, **kwargs):
            captured.update(kwargs)
            return {"status": "pass", "checks": []}

    monkeypatch.setattr(ROUTER, "_v2_route_errors", lambda *_: [])
    monkeypatch.setattr(ROUTER, "_load_fixed_module", lambda *_: Validator)
    report = ROUTER._run_v2_current(ROOT, epoch, "a" * 40)
    assert report["status"] == "pass"
    assert captured["protocol_module_sha256"] == epoch["protocolModule"]["sha256"]


def test_construction_git_queries_use_a_closed_environment(
    tmp_path: Path, monkeypatch,
) -> None:
    captured = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs["env"])
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(CONSTRUCTION.subprocess, "run", fake_run)
    CONSTRUCTION._git(tmp_path, "status")
    assert captured["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert captured["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert Path(captured["HOME"]) != Path.home()


def test_router_rejects_replace_refs_and_local_concealment(monkeypatch) -> None:
    def replaced(_root: Path, *args: str):
        stdout = b"a" * 40 + b"\n" if args[:2] == ("replace", "-l") else b""
        return subprocess.CompletedProcess(args, 0 if stdout else 1, stdout, b"")

    monkeypatch.setattr(ROUTER, "_git", replaced)
    assert any("replacement refs" in error for error in ROUTER.repository_control_errors(ROOT))

    def configured(_root: Path, *args: str):
        if args[:2] == ("replace", "-l"):
            return subprocess.CompletedProcess(args, 0, b"", b"")
        return subprocess.CompletedProcess(args, 0, b"core.fsmonitor true\n", b"")

    monkeypatch.setattr(ROUTER, "_git", configured)
    assert any("configuration" in error for error in ROUTER.repository_control_errors(ROOT))


def test_altered_root_registry_bytes_are_rejected_before_routing(monkeypatch) -> None:
    original = ROUTER.sha256_file

    def altered(path: Path) -> str:
        if path.name == "science-epoch-registry.json":
            return "0" * 64
        return original(path)

    monkeypatch.setattr(ROUTER, "sha256_file", altered)
    assert any(
        "registry bytes" in error
        for error in ROUTER.validate_registry(ROOT, registry())
    )


def test_aggregate_status_fails_closed() -> None:
    assert ROUTER.aggregate_status([{"status": "pass"}]) == "pass"
    assert ROUTER.aggregate_status([{"status": "pass"}, {"status": "fail"}]) == "fail"
    assert (
        ROUTER.aggregate_status([{"status": "pass"}, {"status": "cannot_run"}])
        == "cannot_run"
    )
    assert ROUTER.aggregate_status([{"status": "pass"}, {"status": "unknown"}]) == "cannot_run"
