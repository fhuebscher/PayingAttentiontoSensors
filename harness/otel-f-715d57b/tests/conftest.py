"""Test-tree switch for the OTel study-epoch selector (2026-10-03).

With `modules/otel-demo/execution/study-epoch.json` committed, this tree runs a selector-activated epoch
(otel-traffic-sweep-v1 from 2026-10-03, otel-quiet-calibration-v1 from 2026-10-04), so the tests below, which pin the frozen epoch (otel-demo-offpath-v1: 36 cells, the checkout journey, four postures, the
selected-literal path check) on the real tree, describe an epoch this tree no longer runs. They are skipped there,
not deleted: with the selector absent all of them run (and pass). The list is the exact set that failed under a
local trial activation on 2026-10-03 (selector + tombstone tuple + ledger entry, reverted after); the sweep's own
tests exercise the sweep in tree copies with their own selector. Without the selector this hook does nothing.
"""
from pathlib import Path

import pytest

SELECTOR = Path(__file__).resolve().parents[1] / "modules/otel-demo/execution/study-epoch.json"
FROZEN_EPOCH_ONLY = {
    # Pins "the active epoch has spent no attempt", true of offpath; the sweep's attempt 1 ran (2026-10-03). The same
    # driver behaviour for the sweep (refuse attempt 1, take attempt 2) is tested in test_otel_traffic_sweep.py.
    "tests/test_otel_run2_fixes.py::test_driver_path_refuses_the_spent_attempt_and_takes_the_launcher_attempt",
    "tests/test_otel_adapter_contract_is_complete.py::test_no_unclassified_dynamic_key_site_appeared",
    "tests/test_otel_candidate_runtime.py::test_a_failed_path_check_stops_the_campaign_before_any_fault_cell",
    "tests/test_otel_candidate_runtime.py::test_a_gate_plan_typed_for_attempt_one_does_not_authorize_attempt_two",
    "tests/test_otel_candidate_runtime.py::test_attempt_two_flows_from_the_plan_into_every_gate_sentence_and_cell",
    "tests/test_otel_candidate_runtime.py::test_candidate_cell_refuses_before_any_fault_or_artifact_mutation",
    "tests/test_otel_candidate_runtime.py::test_capture_readiness_invokes_exact_installed_zero_cell_producer",
    "tests/test_otel_candidate_runtime.py::test_cell_contract_and_setup_package_carry_the_study_epoch",
    "tests/test_otel_candidate_runtime.py::test_cell_contracts_keep_cost_and_fault_windows_separate",
    "tests/test_otel_candidate_runtime.py::test_execution_package_preserves_order_target_lease_ports_and_no_retry",
    "tests/test_otel_candidate_runtime.py::test_fetch_retains_abort_or_partial_without_false_terminal_validation",
    "tests/test_otel_candidate_runtime.py::test_gate_run_defects_fail_before_transport",
    "tests/test_otel_candidate_runtime.py::test_gate_setup_checker_is_watched_failing",
    "tests/test_otel_candidate_runtime.py::test_install_side_compose_environment_is_the_full_posture_environment",
    "tests/test_otel_candidate_runtime.py::test_launch_uses_isolated_pinned_python_on_target",
    "tests/test_otel_candidate_runtime.py::test_missing_or_invalid_gate_never_calls_transport_runner",
    "tests/test_otel_candidate_runtime.py::test_plan_consumes_exact_24_cell_compiler_and_keeps_authority_separate",
    "tests/test_otel_candidate_runtime.py::test_plan_inspection_enforces_the_real_entrypoint_proof",
    "tests/test_otel_candidate_runtime.py::test_posture_config_digest_is_shared_between_producer_and_validator",
    "tests/test_otel_candidate_runtime.py::test_read_only_replay_survives_expired_run_gate_but_cannot_reauthorize_execution",
    "tests/test_otel_candidate_runtime.py::test_readiness_freshness_and_gate_run_order_are_watched",
    "tests/test_otel_candidate_runtime.py::test_readiness_replays_every_positive_and_planted_defect_witness",
    "tests/test_otel_candidate_runtime.py::test_readiness_witness_defects_fail_closed",
    "tests/test_otel_candidate_runtime.py::test_refusal_is_two_independent_facts_descriptor_then_tombstone",
    "tests/test_otel_candidate_runtime.py::test_remote_controller_rechecks_full_budget_at_actual_start",
    "tests/test_otel_candidate_runtime.py::test_remote_posture_proof_v2_records_per_service_load_states",
    "tests/test_otel_candidate_runtime.py::test_remote_refuses_an_execution_package_without_one_positive_attempt",
    "tests/test_otel_candidate_runtime.py::test_remote_replay_rejects_tampered_execution_package",
    "tests/test_otel_candidate_runtime.py::test_remote_setup_package_is_exact_and_watches_authority_tamper",
    "tests/test_otel_candidate_runtime.py::test_repository_tombstones_agree_and_name_at_most_the_current_study_epoch",
    "tests/test_otel_candidate_runtime.py::test_reviewed_target_projection_tamper_fails_gate_plan",
    "tests/test_otel_candidate_runtime.py::test_root_transport_and_stig_execution_are_separate_and_exact",
    "tests/test_otel_candidate_runtime.py::test_setup_consumption_timestamp_defect_fails",
    "tests/test_otel_candidate_runtime.py::test_setup_gate_freshness_is_consumed_once_then_runtime_uses_fresh_readiness",
    "tests/test_otel_candidate_runtime.py::test_setup_receipt_checker_is_watched_failing",
    "tests/test_otel_candidate_runtime.py::test_status_discovers_retained_completion_after_collected_unit_vanishes",
    "tests/test_otel_candidate_runtime.py::test_target_producer_denial_precedes_planted_post_setup_result",
    "tests/test_otel_candidate_runtime.py::test_target_producer_refuses_before_observer_or_target_access",
    "tests/test_otel_candidate_runtime.py::test_target_refuses_a_package_whose_path_check_does_not_precede_every_fault",
    "tests/test_otel_candidate_terminal.py::test_cross_module_offpath_constants_agree",
    "tests/test_otel_candidate_terminal.py::test_frontend_pause_at_a_short_hold_may_leave_every_journey_traced",
    "tests/test_otel_candidate_terminal.py::test_off_path_fault_cell_with_every_journey_traced_is_valid",
    "tests/test_otel_candidate_terminal.py::test_offpath_fault_and_journey_defects_fail_closed",
    "tests/test_otel_candidate_terminal.py::test_run2_fix_plants",
    "tests/test_otel_candidate_terminal.py::test_terminal_accepts_a_complete_exact_lattice_nested_campaign",
    "tests/test_otel_candidate_terminal.py::test_terminal_checker_is_watched_failing_on_planted_cell_defects",
    "tests/test_otel_candidate_terminal.py::test_terminal_refuses_a_campaign_whose_path_check_failed_or_does_not_replay",
    "tests/test_otel_candidate_terminal.py::test_terminal_refuses_a_descriptor_shape_with_unrealized_postures",
    "tests/test_otel_candidate_terminal.py::test_terminal_refuses_while_the_v2_epoch_is_not_admitted_by_the_target_controllers",
    "tests/test_otel_candidate_terminal.py::test_terminal_rejects_a_partial_retained_tree",
    "tests/test_otel_candidate_terminal.py::test_terminal_rejects_campaign_level_defects",
    "tests/test_otel_candidate_terminal.py::test_workload_path_check_is_watched_passing_and_failing",
    "tests/test_otel_candidate_unsupported.py::test_v1_ledger_is_scoped_to_v1_and_names_v2_as_its_successor",
    "tests/test_otel_gate_driver_shims.py::test_compose_project_keeps_the_underscore_spelling_the_target_guards_expect",
    "tests/test_otel_gate_driver_shims.py::test_driver_identity_equals_the_runtime_and_compiler_constants",
    "tests/test_otel_gate_driver_shims.py::test_inspect_campaign_replays_the_thirty_six_cell_plan_offline",
    "tests/test_otel_gate_driver_shims.py::test_propose_then_authorize_then_status_works_with_no_target",
    "tests/test_otel_traffic_sweep.py::test_frozen_epoch_digests_and_runtime_shape_are_unchanged_without_a_selector",
    "tests/test_otel_traffic_sweep.py::test_frozen_execution_package_and_posture_proof_equal_the_base_codes",
}


def pytest_collection_modifyitems(config, items):
    if not SELECTOR.exists():
        return
    skip = pytest.mark.skip(reason="pins the frozen epoch; this tree's selector activates a non-frozen epoch")
    for item in items:
        if item.nodeid.split("[", 1)[0] in FROZEN_EPOCH_ONLY:
            item.add_marker(skip)
