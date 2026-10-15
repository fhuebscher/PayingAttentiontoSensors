"""The admit-otel-demo-candidate-pilot-v2 change: governance shape, bound bytes,
protocol replay and artifact completeness, checked locally without the v3
router (which cannot route a second otel-demo child in this lineage; see the
change's authority.md). Also pins that the admission blocker in governance
tracks the real tombstone, so the file is exact before and after the governed
edit."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CHANGE_ID = "admit-otel-demo-candidate-pilot-v2"
CHANGE_ROOT = ROOT / "openspec" / "changes" / CHANGE_ID
SCHEMA = ROOT / "contracts" / "multisut-construction-control.schema.json"
TOMBSTONE_BLOCKER = "study-epoch-not-admitted-by-target-controllers"


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pilot = _load("otel_v2_epoch_pilot", "modules/otel-demo/execution/candidate_pilot.py")
setup = _load("otel_v2_epoch_setup", "modules/otel-demo/execution/candidate_setup.py")
remote = _load("otel_v2_epoch_remote", "modules/otel-demo/execution/candidate_remote.py")


def governance() -> dict:
    return json.loads((CHANGE_ROOT / "governance.json").read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_show(commit: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{relative}"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout


def test_governance_has_the_closed_v3_construction_shape():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(governance()), key=lambda e: list(e.absolute_path))
    assert errors == [], [f"{'.'.join(map(str, e.absolute_path))}: {e.message}" for e in errors]
    value = governance()
    assert value["id"] == CHANGE_ID
    assert value["module"] == {
        "id": "otel-demo", "applicationFamily": "otel-demo",
        "channel": "compose-otel-collector", "replicationContribution": "application-family",
    }
    assert set(value["permissions"].values()) == {False}
    assert [row["status"] for row in value["humanCheckpoints"]] == ["pending", "not-requested", "not-requested"]


def test_every_source_binding_names_bytes_that_exist_at_its_commit_and_now():
    drifted = []
    for binding in governance()["sourceBindings"]:
        at_commit = hashlib.sha256(_git_show(binding["sourceCommit"], binding["path"])).hexdigest()
        now = _sha(ROOT / binding["path"])
        if not (at_commit == now == binding["sha256"]):
            drifted.append((binding["path"], at_commit[:12], now[:12], binding["sha256"][:12]))
    assert drifted == []


def test_adopted_source_commit_and_tree_are_reproducible():
    source = governance()["adoptedSource"]
    tree = subprocess.run(
        ["git", "-C", str(ROOT), "show", "-s", "--format=%T", source["commit"]],
        check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    assert tree == source["tree"]


def test_protocol_bindings_replay_the_v2_design_and_leave_v1_untouched():
    protocol = governance()["protocolBindings"]
    descriptor_path = ROOT / protocol["descriptor"]["path"]
    # v2 is no longer the compiler's default epoch (v3 is, main repo
    # research/otel-postures/DECLARATION.md); it is still compiled and replayed.
    assert protocol["studyEpoch"] == pilot.PREVIOUS_EPOCH == "otel-demo-candidate-pilot-v2"
    assert pilot.EPOCH == "otel-demo-offpath-v1"
    assert _sha(descriptor_path) == protocol["descriptor"]["byteSha256"]
    document = pilot.load_descriptor(descriptor_path)
    assert (
        pilot.canonical_sha256(document) == protocol["descriptor"]["canonicalSha256"]
        == pilot.EPOCHS["otel-demo-candidate-pilot-v2"]["expectedDescriptorSha256"]
    )
    plan = pilot.compile_plan(document)
    assert pilot.canonical_sha256(plan) == protocol["compiledPlan"]["canonicalSha256"]
    assert plan["runCount"] == protocol["compiledPlan"]["runCount"] == 18
    assert _sha(ROOT / protocol["compiler"]["path"]) == protocol["compiler"]["sha256"]
    assert protocol["canonical"] is False
    # v1: bytes, canonical digest and plan digest as adopted at e3623ed.
    v1 = pilot.EPOCHS["otel-demo-candidate-pilot-v1"]
    assert _sha(v1["descriptor"]) == "fb43212b38ce0cd53538ee654b825574ee415dc4624fc2cc32bcc6d82504cbaa"
    assert _sha(v1["descriptor"]) == hashlib.sha256(
        _git_show("e3623ed6d2dc98d967d6be312fb93ad1e1685f46", "pipelines/campaigns/otel-demo-candidate-pilot-v1.json")
    ).hexdigest()
    v1_plan = pilot.compile_plan(pilot.load_descriptor(v1["descriptor"]))
    assert pilot.canonical_sha256(v1_plan) == "53b0ac1b6a43c3070dfe8148ec391ef0cc278eca38250f4f926bb14862597e67"


def test_artifacts_marker_findings_and_owned_paths_are_complete():
    value = governance()
    for key, relative in value["artifacts"].items():
        for item in (relative if isinstance(relative, list) else [relative]):
            assert (ROOT / item).is_file(), (key, item)
    assert (CHANGE_ROOT / ".openspec.yaml").read_text(encoding="utf-8") == "schema: scientific-change\n"
    with (ROOT / value["artifacts"]["findings"]).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows == [[
        "finding_id", "change_id", "reviewer_context", "kind", "severity", "status",
        "artifact", "summary", "evidence", "disposition",
    ]], "findings ledger must be header-only until an independent review appends rows"
    tracked = set(subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"], check=True, stdout=subprocess.PIPE,
    ).stdout.decode().split("\0"))
    ownership = value["pathOwnership"]
    assert ownership["baseCommit"] == "4f5575f5f46bddcd528433f8828e69597458eb98"
    assert {".local/", "upstream/"} <= set(ownership["forbidden"])
    missing = [path for path in ownership["allowed"] if not (ROOT / path).is_file()]
    assert missing == []
    untracked = [path for path in ownership["allowed"] if path not in tracked]
    assert untracked == [], "every owned path must be tracked delivery, never an untracked file"
    assert "pipelines/campaigns/otel-demo-candidate-pilot-v1.json" not in ownership["allowed"], "v1 is not owned: its bytes do not move"
    spec_text = (ROOT / value["artifacts"]["specs"][0]).read_text(encoding="utf-8")
    assert spec_text.count("### Requirement:") >= 5 and spec_text.count("#### Scenario:") >= 5


def test_tombstone_blocker_tracks_the_real_tombstone_and_the_rest_are_gate_or_lineage_resolved():
    blockers = governance()["workflow"]["blockers"]
    admitted = tuple(setup.ADMITTED_STUDY_EPOCHS)
    assert admitted == tuple(remote.ADMITTED_STUDY_EPOCHS)
    assert (TOMBSTONE_BLOCKER in blockers) == ("otel-demo-candidate-pilot-v2" not in admitted), (
        "governance must drop the tombstone blocker in the same diff that admits the epoch, and keep it until then"
        " (and restore it in the diff that un-admits it: v3 replaced v2 in the tombstone)"
    )
    assert {"gate-plan-pending", "gate-run-not-requested",
            "v3-router-registration-underivable-in-this-lineage-pending-d19"} <= set(blockers)
    # KNOWN is package-shape knowledge, not admission.
    assert setup.KNOWN_STUDY_EPOCHS == remote.KNOWN_STUDY_EPOCHS == ("otel-demo-offpath-v1",)
    assert setup.UNSUPPORTED_STUDY_EPOCHS == remote.UNSUPPORTED_STUDY_EPOCHS == ("otel-demo-candidate-pilot-v1",)


@pytest.mark.parametrize("plant", ("permission", "checkpoint", "parent", "compiler-digest"))
def test_planted_governance_defects_are_rejected(plant):
    value = governance()
    if plant == "permission":
        value["permissions"]["runtimeAllowed"] = True
    elif plant == "checkpoint":
        value["humanCheckpoints"][1]["status"] = "pending"
    elif plant == "parent":
        value["parentEpoch"]["changeId"] = "adopt-hotel-reservation-candidate-harness"
    else:
        value["protocolBindings"]["compiler"]["sha256"] = "0" * 64
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    schema_errors = list(Draft202012Validator(schema).iter_errors(value))
    if plant == "compiler-digest":
        assert schema_errors == []
        assert _sha(ROOT / value["protocolBindings"]["compiler"]["path"]) != value["protocolBindings"]["compiler"]["sha256"]
    else:
        assert schema_errors
