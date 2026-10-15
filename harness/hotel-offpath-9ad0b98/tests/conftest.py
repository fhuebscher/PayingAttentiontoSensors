"""Test-tree switch for the study-epoch selector (2026-10-03).

With `modules/hotel-reservation/execution/study-epoch.json` committed, this tree runs the epoch it names
(hotel-traffic-sweep-v1 from 2026-10-03, hotel-quiet-calibration-v1 from 2026-10-04, hotel-offpath-v1 from 2026-10-15),
so the tests below, which pin
the frozen epoch (hotel-reservation-selected-v1) on the real tree, describe an epoch this tree no longer runs. They are skipped here, not deleted: with the selector absent all of them pass (verified 2026-10-03,
404 passed / 1 needing ssh to fb14srv4), and the frozen epoch keeps its own branch (selected-20260929, e4fd4c7).
The sweep, quiet-calibration and off-path tests exercise their epochs in tree copies with their own selector.
"""
import json
from pathlib import Path

import pytest

SELECTOR = Path(__file__).resolve().parents[1] / "modules/hotel-reservation/execution/study-epoch.json"
FROZEN_EPOCH_ONLY = {
    "tests/test_hotel_blocked_evidence.py::test_terminal_replay_also_enforces_the_claim_ceiling",
    "tests/test_hotel_candidate_runtime.py::test_always_on_system_artifacts_are_required_in_every_posture",
    "tests/test_hotel_candidate_runtime.py::test_cell_manifest_watches_post_validation_tamper",
    "tests/test_hotel_candidate_runtime.py::test_detached_launch_independently_consumes_freshness_and_full_budget",
    "tests/test_hotel_candidate_runtime.py::test_detached_launch_receipt_is_fully_admission_bound",
    "tests/test_hotel_candidate_runtime.py::test_empty_capture_terminal_proves_empty_acquisition_without_source_claim",
    "tests/test_hotel_candidate_runtime.py::test_every_hotel_extension_is_classified",
    "tests/test_hotel_candidate_runtime.py::test_gate_run_watches_stale_and_short_deadline",
    "tests/test_hotel_candidate_runtime.py::test_remote_launcher_retains_abort_for_planted_pre_popen_failure",
    "tests/test_hotel_candidate_runtime.py::test_remote_setup_launch_and_status_programs_are_syntax_checked_and_fixed",
    "tests/test_hotel_candidate_runtime.py::test_runtime_policy_and_exact_cell_contracts",
    "tests/test_hotel_candidate_runtime.py::test_sampler_off_posture_that_retains_docker_stats_cpu_is_rejected",
    "tests/test_hotel_candidate_runtime.py::test_sampler_on_posture_without_docker_stats_cpu_is_missing_an_artifact",
    "tests/test_hotel_candidate_runtime.py::test_target_supervisor_rechecks_full_budget_at_child_start",
    "tests/test_hotel_candidate_runtime.py::test_target_supervisor_retains_and_validates_preexecute_or_abrupt_abort",
    "tests/test_hotel_candidate_runtime.py::test_terminal_watchers_reject_semantic_defects_after_a_fresh_seal",
    "tests/test_hotel_gate_driver_shims.py::test_declared_gate_run_envelope_produces_a_document_the_orchestrator_accepts",
    "tests/test_hotel_traffic_sweep.py::test_driver_config_follows_the_selector_of_the_tree_it_reads",
    "tests/test_hotel_traffic_sweep.py::test_frozen_epoch_digests_files_and_runtime_shape_are_unchanged",
    "tests/test_hotel_traffic_sweep.py::test_run_cell_passes_the_frozen_epochs_literals_unchanged",
}


def pytest_collection_modifyitems(config, items):
    if not SELECTOR.exists():
        return
    epoch = json.loads(SELECTOR.read_text())["studyEpoch"]
    skip = pytest.mark.skip(reason="pins the frozen epoch; this tree's selector activates " + epoch)
    for item in items:
        if item.nodeid.split("[", 1)[0] in FROZEN_EPOCH_ONLY:
            item.add_marker(skip)
