"""Test-tree switch for the TeaStore study-epoch selector (2026-10-03).

With `modules/teastore/execution/study-epoch.json` committed, this tree runs the epoch it names
(teastore-traffic-sweep-v1; teastore-quiet-calibration-v1 since 2026-10-04; teastore-traffic-sweep-b-v1 since 2026-10-09,
which has the sweep's fault regimes, so the effect-cell skip below does not apply to it; teastore-quiet-calibration-v1 again since 2026-10-10 for the second quiet run A2, so the skip below applies again; teastore-traffic-sweep-c-v1 since 2026-10-11 for campaign C, which has the sweep's fault regimes, so the effect-cell skip does not apply to it; teastore-offpath-v1 since 2026-10-14 for the off-path pause, whose fault regimes are the recommender pause and the auth freeze, so the effect-cell skip does not apply to it either), so the tests below, which pin the
frozen epoch (teastore-candidate-pilot-sys-v1: 27 cells, the 0.15/s login-browse journey, the persistence-crash regime, regime-major plan order), describe an epoch the tree no longer runs. They are skipped here,
not deleted: with the selector absent all of them pass (commit 9e75010), and the frozen epoch keeps its base commit
c1724b1. The list is the exact set that failed in a copy of 9e75010 with the selector committed (2026-10-03,
77 node ids), plus the one frozen-only test added with the Q3 drain allowance (59634c5, probed the same way) and the
frozen zero-tolerance correlation tests that decision 25 relaxes for sweep cells (each passes without the selector); the sweep tests (tests/test_teastore_traffic_sweep.py) exercise the sweep in tree copies with
their own selector. Without a selector this file changes nothing.
"""
import json
from pathlib import Path

import pytest

SELECTOR = Path(__file__).resolve().parents[1] / "modules/teastore/execution/study-epoch.json"
FROZEN_EPOCH_ONLY = {
    "tests/test_candidate_orchestrator.py::test_campaign_population_mutations_cannot_be_used_for_simulation",
    "tests/test_candidate_orchestrator.py::test_clean_pause_resumes_only_unsimulated_cells_without_rerandomizing",
    "tests/test_candidate_orchestrator.py::test_exact_compiled_27_cell_simulation_is_explicitly_non_evidentiary",
    "tests/test_candidate_orchestrator.py::test_materialized_campaign_rejects_boolean_schema_version",
    "tests/test_candidate_orchestrator.py::test_materialized_manifest_crosses_schedule_but_not_evidence_gates",
    "tests/test_candidate_orchestrator.py::test_preexisting_run_root_stops_simulation_without_creating_another",
    "tests/test_candidate_orchestrator.py::test_public_path_materializes_and_replays_without_run_artifacts",
    "tests/test_candidate_orchestrator.py::test_public_replay_never_appends_simulation_rows",
    "tests/test_candidate_orchestrator.py::test_rehashed_attempt_two_simulation_injection_is_rejected",
    "tests/test_candidate_orchestrator.py::test_rehashed_boolean_integer_simulation_injection_is_rejected",
    "tests/test_candidate_orchestrator.py::test_rehashed_fixture_digest_substitution_is_rejected",
    "tests/test_candidate_orchestrator.py::test_rehashed_simulation_population_defects_fail_closed",
    "tests/test_candidate_orchestrator.py::test_retained_descriptor_plan_and_campaign_bytes_are_immutable",
    "tests/test_candidate_orchestrator.py::test_simulation_journal_hash_chain_tamper_is_rejected",
    "tests/test_candidate_orchestrator.py::test_simulation_journal_strict_parser_rejects_concealment",
    "tests/test_candidate_pilot_evidence.py::test_actual_fault_generator_schema_crosses_candidate_validator",
    "tests/test_candidate_pilot_evidence.py::test_actual_witness_extractor_output_crosses_candidate_validator",
    "tests/test_candidate_pilot_evidence.py::test_campaign_all_run_gate_watches_one_corrupt_scheduled_cell",
    "tests/test_candidate_pilot_evidence.py::test_campaign_exact_frozen_population_passes",
    "tests/test_candidate_pilot_evidence.py::test_campaign_gates_watch_planted_manifest_defects",
    "tests/test_candidate_pilot_evidence.py::test_cell_blocks_when_system_samples_are_missing",
    "tests/test_candidate_pilot_evidence.py::test_cli_exit_status_and_machine_readable_validation_table",
    "tests/test_candidate_pilot_evidence.py::test_crash_arm_restart_banner_is_accepted_only_for_the_killed_container",
    "tests/test_candidate_pilot_evidence.py::test_crash_cell_allows_null_rows_but_not_at_the_first_sample",
    "tests/test_candidate_pilot_evidence.py::test_cross_trace_assembly_is_unsupported_not_counted_as_an_edge",
    "tests/test_candidate_pilot_evidence.py::test_each_artifact_parser_watches_malformed_bytes",
    "tests/test_candidate_pilot_evidence.py::test_each_effect_gate_watches_a_planted_defect",
    "tests/test_candidate_pilot_evidence.py::test_effect_barrier_onset_wall_tolerates_epoch_float_rounding",
    "tests/test_candidate_pilot_evidence.py::test_effect_cell_supports_claim_when_diagnostic_resources_are_unreadable",
    "tests/test_candidate_pilot_evidence.py::test_effect_cell_supports_claim_without_resource_artifact",
    "tests/test_candidate_pilot_evidence.py::test_full_posture_proof_binds_rendered_full_aop",
    "tests/test_candidate_pilot_evidence.py::test_ledger_rows_written_in_completion_order_still_bind_by_opportunity_id",
    "tests/test_candidate_pilot_evidence.py::test_mapping_outside_independently_eligible_denominator_is_unsupported",
    "tests/test_candidate_pilot_evidence.py::test_missing_token_correlation_is_unsupported_not_observed_failure",
    "tests/test_candidate_pilot_evidence.py::test_missing_witness_is_unsupported_and_never_zero",
    "tests/test_candidate_pilot_evidence.py::test_no_fault_cell_blocks_a_null_required_service_even_when_rehashed",
    "tests/test_candidate_pilot_evidence.py::test_none_posture_proof_binds_empty_rendering",
    "tests/test_candidate_pilot_evidence.py::test_none_scores_zero_only_with_independent_denominator_and_terminal_empty_capture",
    "tests/test_candidate_pilot_evidence.py::test_plan_gate_accepts_producer_truncated_schedule_microseconds",
    "tests/test_candidate_pilot_evidence.py::test_plan_gate_still_blocks_schedule_beyond_one_microsecond",
    "tests/test_candidate_pilot_evidence.py::test_probe_orphan_root_is_excused_and_counted_under_a_woven_entry_point",
    "tests/test_candidate_pilot_evidence.py::test_raw_application_log_replay_rejects_non_marker_secret_text",
    "tests/test_candidate_pilot_evidence.py::test_raw_application_log_replay_rejects_quoted_json_secret_text",
    "tests/test_candidate_pilot_evidence.py::test_raw_application_log_replay_watches_hash_consistent_fabrication",
    "tests/test_candidate_pilot_evidence.py::test_raw_application_replay_rejects_encoded_or_multiline_secret_text",
    "tests/test_candidate_pilot_evidence.py::test_selected_run_releases_separate_raw_signature_and_path_views",
    "tests/test_candidate_pilot_evidence.py::test_selected_thread_traces_release_trace_level_coverage",
    "tests/test_candidate_pilot_evidence.py::test_shared_window_retains_setup_gap_and_watches_overlap",
    "tests/test_candidate_pilot_evidence.py::test_token_allocation_clock_slack_mirrors_the_driver",
    "tests/test_candidate_pilot_evidence.py::test_unhashable_native_mapping_identity_is_structured_unsupported",
    "tests/test_candidate_pilot_evidence.py::test_valid_effect_run_uses_actual_phase_starts",
    "tests/test_candidate_runtime_adapter.py::test_campaign_manifest_float_run_count_does_not_equal_integer_scope",
    "tests/test_candidate_runtime_adapter.py::test_cell_contracts_preserve_all_27_cells_and_separate_claim_windows",
    "tests/test_candidate_runtime_adapter.py::test_diagnostic_240_30_fault_timing_cannot_enter_a_candidate_cell_contract",
    "tests/test_candidate_runtime_adapter.py::test_even_fully_reconciled_local_outcome_requires_terminal_validator",
    "tests/test_candidate_runtime_adapter.py::test_exact_plan_replays_but_self_declared_readiness_is_semantically_rejected",
    "tests/test_candidate_runtime_adapter.py::test_numeric_timing_scope_requires_exact_integer_type",
    "tests/test_candidate_runtime_adapter.py::test_planted_gate_run_defects_fail_independent_of_unimplemented_readiness",
    "tests/test_teastore_app_witness.py::test_effect_omits_partial_during_path_without_guessing_negative",
    "tests/test_teastore_candidate_runtime_successor.py::test_all_retained_readiness_pairs_are_replayed_positive_and_watched_failing",
    "tests/test_teastore_candidate_runtime_successor.py::test_bounded_transport_rechecks_full_window_before_first_remote_write",
    "tests/test_teastore_candidate_runtime_successor.py::test_cell_entry_accepts_only_the_frozen_campaign_output_path",
    "tests/test_teastore_candidate_runtime_successor.py::test_cell_producer_watches_nested_contract_drift_before_runtime",
    "tests/test_teastore_candidate_runtime_successor.py::test_disconnect_reports_running_then_refetches_without_second_launch",
    "tests/test_teastore_candidate_runtime_successor.py::test_installed_preflight_preserves_stopped_foreign_but_rejects_conflicts",
    "tests/test_teastore_candidate_runtime_successor.py::test_installed_readiness_admission_is_remote_then_locally_replayed",
    "tests/test_teastore_candidate_runtime_successor.py::test_readiness_enclosing_digests_watch_every_nesting_layer",
    "tests/test_teastore_candidate_runtime_successor.py::test_readiness_rejects_ingress_and_generated_tree_digest_alias",
    "tests/test_teastore_candidate_runtime_successor.py::test_readiness_watches_image_map_substituted_after_target_build",
    "tests/test_teastore_candidate_runtime_successor.py::test_remote_controller_consumes_exact_order_once_under_terminal_gate",
    "tests/test_teastore_candidate_runtime_successor.py::test_remote_controller_retains_pre_output_lease_abort_as_abstained",
    "tests/test_teastore_candidate_runtime_successor.py::test_remote_controller_stops_after_cell_failure_and_watches_cleanup",
    "tests/test_teastore_candidate_runtime_successor.py::test_runtime_package_consumes_all_27_contracts_without_reordering",
    "tests/test_teastore_candidate_runtime_successor.py::test_runtime_package_planted_defects_fail_before_transport",
    "tests/test_teastore_candidate_runtime_successor.py::test_successful_detached_start_returns_before_terminal_fetch",
    "tests/test_teastore_traffic_sweep.py::test_frozen_compiler_and_descriptor_are_byte_identical_to_the_base",
    "tests/test_teastore_traffic_sweep.py::test_frozen_runtime_constants_without_a_selector",
    "tests/test_teastore_traffic_sweep.py::test_the_frozen_epoch_has_no_drain_allowance",
    "tests/test_candidate_pilot_evidence.py::test_deeper_or_mixed_correlation_errors_block_even_when_entry_is_unwoven",  # zero-tolerance correlation rules; sweep uses decision 25
    "tests/test_candidate_pilot_evidence.py::test_each_run_gate_watches_a_planted_defect",  # zero-tolerance correlation rules; sweep uses decision 25
    "tests/test_candidate_pilot_evidence.py::test_probe_orphan_outside_its_status_caller_window_still_blocks",  # zero-tolerance correlation rules; sweep uses decision 25
    "tests/test_candidate_pilot_evidence.py::test_repeated_identities_outside_a_proven_exposure_window_still_block",  # zero-tolerance correlation rules; sweep uses decision 25
    "tests/test_candidate_pilot_evidence.py::test_thread_traces_under_full_closure_still_block_both_gates",  # zero-tolerance correlation rules; sweep uses decision 25
}

# Quiet calibration (teastore-quiet-calibration-v1, protocol decision 48, 2026-10-04): that epoch has no fault regime,
# so these tests, which build effect cells (auth-freeze-effect) against the tree's active epoch, describe regimes it
# does not run. Each passes under the sweep selector (3c8cc03). The list is the exact set that failed with the quiet
# selector written into the worktree before the activation commit (2026-10-04, 18 node ids = these 14 tests with
# their parameters). The sweep's effect cells stay covered by tests/test_teastore_traffic_sweep.py in tree copies.
# Two of them test generic rules with an effect-cell fixture (ledger row drift, system-samples shape); their twins on
# sealed quiet cells run in tests/test_teastore_quiet_calibration.py (review finding A1, 2026-10-04).
QUIET_EPOCH = "teastore-quiet-calibration-v1"
EFFECT_REGIME_ONLY = {
    "tests/test_candidate_pilot_evidence.py::test_effect_cell_blocks_cost_projection_leaked_into_receipt",
    "tests/test_candidate_pilot_evidence.py::test_intervention_artifact_gate_watches_missing_separate_receipt",
    "tests/test_candidate_pilot_evidence.py::test_ledger_row_drifting_from_its_opportunity_still_blocks_after_reorder",
    "tests/test_candidate_pilot_evidence.py::test_system_samples_shape_defects_block",
    "tests/test_candidate_pilot_evidence.py::test_thaw_replay_identities_inside_the_exposure_window_are_counted_not_blocked",
    "tests/test_native_token_correlation.py::test_effect_mapping_excludes_the_unscored_fault_window",
    "tests/test_teastore_app_witness.py::test_a_journey_ending_exactly_at_onset_is_still_baseline",
    "tests/test_teastore_app_witness.py::test_a_journey_straddling_onset_is_exposure_not_baseline",
    "tests/test_teastore_app_witness.py::test_effect_allows_no_during_pair_but_requires_before_and_after",
    "tests/test_teastore_app_witness.py::test_effect_excludes_an_unscored_pair_observed_after_the_journey_ended",
    "tests/test_teastore_app_witness.py::test_effect_excludes_unscored_thaw_replay_instead_of_blocking",
    "tests/test_teastore_app_witness.py::test_effect_still_blocks_a_duplicate_on_a_scored_journey",
    "tests/test_teastore_app_witness.py::test_effect_still_blocks_a_scored_pair_observed_after_the_journey_ended",
    "tests/test_teastore_app_witness.py::test_old_intervention_monotonic_key_names_are_rejected",
}


def pytest_collection_modifyitems(config, items):
    if not SELECTOR.exists():
        return
    try:
        epoch = json.loads(SELECTOR.read_text()).get("studyEpoch")
    except (OSError, ValueError, AttributeError):
        epoch = "an unreadable selector"
    skip = pytest.mark.skip(reason=f"pins the frozen epoch; this tree's selector activates {epoch}")
    skip_effect = pytest.mark.skip(reason=f"builds effect cells; this tree's selector activates {epoch}, which has none")
    for item in items:
        node = item.nodeid.split("[", 1)[0]
        if node in FROZEN_EPOCH_ONLY:
            item.add_marker(skip)
        elif epoch == QUIET_EPOCH and node in EFFECT_REGIME_ONLY:
            item.add_marker(skip_effect)
