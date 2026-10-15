"""Second quiet calibration run A2 (protocol decision 68, 2026-10-10): the quiet epoch re-activated on the B harness.

Quiet run A ran at 91c4967 (campaign results id cedad730...).  A2 repeats its 40 no-fault cells with a new setup ID, so a
new results root, on this tree.  The compiler has no attempt, campaign or seed input (``attempt`` is the literal 1, the
run-ID regexes end in ``a01``), so the plan, descriptor and run IDs are A's, byte for byte; what changes is the tree they
run in.  This file pins that statement:

* the committed selector names the quiet epoch, and ``study_epoch.active`` gives the 40-cell, 7 h epoch of A;
* the quiet descriptor and plan digests are A's and the plan compiles to them in this tree;
* campaign B's and the sweep's descriptor and plan digests are unchanged by the re-activation;
* since bbb6b11 (campaign B's last commit) only the selector and the extension ledger differ under modules/teastore and
  pipelines/campaigns (every other harness file is byte-identical, including B's H10/H4 files whose sweep and quiet
  behaviour tests/test_teastore_sweep_b.py pins against 91c4967).

Since campaign C (teastore-traffic-sweep-c-v1, 2026-10-10) the worktree's selector names C, so the statements about A2's
tree are pinned on A2's commit bb3717e itself (git objects), not on the working tree; the quiet epoch's own files stay
byte-identical in the working tree (checked) and its runtime under the quiet selector is checked in tree copies.

Like the other epoch tests, the behavioural checks (runtime under the quiet selector equals the 91c4967 runtime) run in
tree copies with their own selector in tests/test_teastore_sweep_b.py and tests/test_teastore_quiet_calibration.py.
"""
from __future__ import annotations

import json
import subprocess

import test_teastore_traffic_sweep as sw


ROOT = sw.ROOT
MODULE = sw.MODULE
QUIET = "teastore-quiet-calibration-v1"
B = "teastore-traffic-sweep-b-v1"
A_HARNESS_COMMIT = "91c4967f2d9c12a25eeeaf097f998856c377ca7f"      # quiet run A's harness
B_HARNESS_COMMIT = "bbb6b1165410be5bd4eb304b56c4eac9490310d1"      # campaign B's harness, A2's base
A2_HARNESS_COMMIT = "bb3717e8adeeaa05a45fd8e587cee481da206ac7"     # A2's harness (the re-activation commit)
QUIET_DESCRIPTOR_SHA256 = "338226d05f8e9d3557918ef9120727094bd71532f4eba72cc9191070f102315b"
QUIET_PLAN_SHA256 = "879a81ab0c3f2e960ee11a282c8200e58b98e97bc8a541cbcc5704654f858266"
B_DESCRIPTOR_SHA256 = "d4d846337263f57bfe2b9a0d8de8f0f9cde319157ad8e7611b62faecfe99b7c7"
B_PLAN_SHA256 = "aa3469708cc7f27f3262e12a6293a4a77bc6af1ec9e06cc4156f8bdd123101db"
# What A2's re-activation may change relative to bbb6b11, under the harness directories.
A2_CHANGED = {"modules/teastore/execution/study-epoch.json", "modules/teastore/extension-ledger.yaml"}

quiet = sw.load("teastore_quiet_a2_quiet_compiler", MODULE / "execution/candidate_quiet.py")
campaign_b = sw.load("teastore_quiet_a2_b_compiler", MODULE / "execution/candidate_sweep_b.py")
epoch = sw.load("teastore_quiet_a2_study_epoch", MODULE / "execution/study_epoch.py")


def test_the_committed_selector_names_the_quiet_epoch_and_the_epoch_is_a_s(tmp_path):
    selector = "modules/teastore/execution/study-epoch.json"
    assert json.loads(_blob(A2_HARNESS_COMMIT, selector)) == {"schemaVersion": 1, "studyEpoch": QUIET}
    root = sw._copy_tree(tmp_path, {"schemaVersion": 1, "studyEpoch": QUIET})
    active = sw.load("teastore_quiet_a2_copy_epoch", root / "modules/teastore/execution/study_epoch.py").active(root)
    assert active["studyEpoch"] == QUIET and active["sweep"] is True
    assert active["runCount"] == 40 and active["runWindowHours"] == 7
    assert active["minimumFirstMutationRemainingSeconds"] == 21_300
    assert active["compilerRelative"] == "modules/teastore/execution/candidate_quiet.py"
    assert active["outerLeaseScope"] == "entire-40-cell-one-shot"
    # No fault regime: the controller's regime set is the sweep's no-fault regime only.
    assert tuple(active["regimes"]) == ("no-fault-cost",)


def test_the_quiet_plan_and_descriptor_are_a_s_and_compile_in_this_tree():
    assert quiet.EXPECTED_DESCRIPTOR_SHA256 == QUIET_DESCRIPTOR_SHA256
    assert quiet.EXPECTED_PLAN_SHA256 == QUIET_PLAN_SHA256
    descriptor = quiet.load_descriptor()
    assert quiet.canonical_sha256(descriptor) == QUIET_DESCRIPTOR_SHA256
    plan = quiet.compile_plan(descriptor)
    assert quiet.canonical_sha256(plan) == QUIET_PLAN_SHA256
    run_ids = [run_id for block in plan["blocks"] for run_id in block["order"]]
    assert plan["runCount"] == len(run_ids) == len(set(run_ids)) == 40
    # Run IDs are A's by construction (no attempt input): the same strings, told apart only by the results root.
    assert all(run_id.startswith(QUIET + "/no-fault-cost/") and run_id.endswith("/full/a01") for run_id in run_ids)


def test_campaign_b_and_the_sweep_are_unchanged_by_the_reactivation():
    assert campaign_b.EXPECTED_DESCRIPTOR_SHA256 == B_DESCRIPTOR_SHA256
    assert campaign_b.EXPECTED_PLAN_SHA256 == B_PLAN_SHA256
    assert campaign_b.canonical_sha256(campaign_b.compile_plan(campaign_b.load_descriptor())) == B_PLAN_SHA256
    assert sw.sweep.EXPECTED_PLAN_SHA256 == "88a3017a781233a4848f7ea638b4763f82f63bc902d848514cd8ae5089529355"


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True, text=True).stdout


def _blob(commit: str, relative: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{relative}"], capture_output=True, check=True).stdout


def test_since_campaign_b_only_the_selector_and_the_ledger_differ_in_the_harness():
    changed = set(_git("diff", "--name-only", B_HARNESS_COMMIT, A2_HARNESS_COMMIT, "--", "modules/teastore",
                       "pipelines/campaigns").split())
    assert changed <= A2_CHANGED, changed - A2_CHANGED
    assert "modules/teastore/execution/study-epoch.json" in changed       # the activation itself
    # ... and the selector is the only functional line: B's own files are the files of bbb6b11.
    for relative in ("modules/teastore/execution/candidate_sweep_b.py", "pipelines/campaigns/teastore-traffic-sweep-b-v1.json",
                     "modules/teastore/execution/candidate_quiet.py", "pipelines/campaigns/teastore-quiet-calibration-v1.json",
                     "modules/teastore/execution/performance_campaign.py", "modules/teastore/validation/candidate_pilot.py"):
        assert _blob(A2_HARNESS_COMMIT, relative) == _blob(B_HARNESS_COMMIT, relative), relative


def test_the_quiet_files_are_the_ones_run_a_ran():
    """Quiet's own compiler and descriptor are byte-identical to 91c4967 (A's harness); only the shared files B moved
    (performance_campaign.py, candidate_pilot.py, study_epoch.py) differ from A's tree, and the equality of the runtime's
    behaviour on them is pinned in tests/test_teastore_sweep_b.py."""
    for relative in ("modules/teastore/execution/candidate_quiet.py", "pipelines/campaigns/teastore-quiet-calibration-v1.json",
                     "modules/teastore/execution/candidate_sweep.py", "pipelines/campaigns/teastore-traffic-sweep-v1.json"):
        assert (ROOT / relative).read_bytes() == subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{A_HARNESS_COMMIT}:{relative}"], capture_output=True, check=True).stdout, relative
    moved = set(_git("diff", "--name-only", A_HARNESS_COMMIT, A2_HARNESS_COMMIT, "--", "modules/teastore",
                     "pipelines/campaigns").split())
    assert moved == {
        "modules/teastore/execution/candidate_sweep_b.py",
        "modules/teastore/execution/performance_campaign.py",
        "modules/teastore/execution/study_epoch.py",
        "modules/teastore/extension-ledger.yaml",
        "modules/teastore/validation/candidate_pilot.py",
        "pipelines/campaigns/teastore-traffic-sweep-b-v1.json",
    }, moved
