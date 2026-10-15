import json
from pathlib import Path

import pytest

from obsplacement.placement import (
    build_logical_problem,
    greedy_cardinality,
    greedy_cost_budget,
    objective_summary,
    objective_value,
)


FIXTURE = (
    Path(__file__).parent / "fixtures" / "placement" / "legacy-logical-small.json"
)


def _fixture_problem():
    fixture = json.loads(FIXTURE.read_text())
    legacy = fixture["legacyInput"]
    return fixture, build_logical_problem(
        legacy["sensor_universe"], legacy["path_to_sensors"])


def test_frozen_legacy_objectives_and_greedy_outputs_are_compatible():
    fixture, problem = _fixture_problem()
    golden = fixture["legacyGolden"]
    for objective, expected in golden["greedy"].items():
        result = greedy_cardinality(
            problem, golden["cardinalityBudget"], objective=objective)
        assert sorted(result.selected_order) == expected["selectedSet"]
        assert result.history == pytest.approx(expected["history"])
        assert objective_summary(problem, result.selected_order) == pytest.approx(
            expected["summary"])


def test_frozen_legacy_explicit_cost_greedy_output_is_compatible():
    fixture, problem = _fixture_problem()
    expected = fixture["legacyGolden"]["explicitCostGreedy"]
    result = greedy_cost_budget(
        problem,
        expected["budget"],
        expected["costs"],
        objective=expected["objective"],
    )
    assert sorted(result.selected_order) == expected["selectedSet"]
    assert result.history == pytest.approx(expected["history"])
    assert result.spent == expected["spent"]
    assert objective_summary(problem, result.selected_order) == pytest.approx(
        expected["summary"])


def test_canonical_tie_break_is_stable_across_input_order():
    paths = {
        "p2": ["sensor:b"],
        "p1": ["sensor:a"],
    }
    forward = build_logical_problem(["sensor:a", "sensor:b"], paths)
    reverse = build_logical_problem(
        ["sensor:b", "sensor:a"], dict(reversed(tuple(paths.items()))))
    assert greedy_cardinality(forward, 1, objective="any").selected_order == ("sensor:a",)
    assert greedy_cardinality(reverse, 1, objective="any").selected_order == ("sensor:a",)


def test_strict_all_greedy_preserves_the_zero_singleton_stall():
    problem = build_logical_problem(
        ["sensor:a", "sensor:b"], {"path": ["sensor:a", "sensor:b"]})
    result = greedy_cardinality(problem, 2, objective="all")
    assert result.selected_order == ()
    assert result.objective_value == 0.0
    assert result.stopped == "no-positive-gain"


def test_strict_all_preserves_legacy_scan_past_zero_gain_candidate():
    problem = build_logical_problem(
        ["sensor:a", "sensor:b", "sensor:c"],
        {
            "p0": ["sensor:a"],
            "p1": ["sensor:a", "sensor:b", "sensor:c"],
            "p2": ["sensor:a", "sensor:c"],
            "p3": ["sensor:a"],
        },
    )
    result = greedy_cardinality(problem, 2, objective="all")
    # After selecting a, b still has zero gain but c completes p2.  The pinned
    # legacy queue discards b and continues to c rather than stopping early.
    assert result.selected_order == ("sensor:a", "sensor:c")
    assert result.history == (2.0, 3.0)
    assert result.objective_value == 3.0


def test_partial_credit_variants_are_explicit_not_silent_defaults():
    problem = build_logical_problem(
        ["sensor:a", "sensor:b"], {"path": ["sensor:a", "sensor:b"]})
    sqrt_value = objective_value(
        problem, ["sensor:a"], objective="partial", partial_credit="sqrt")
    linear_value = objective_value(
        problem, ["sensor:a"], objective="partial", partial_credit="linear")
    log_value = objective_value(
        problem, ["sensor:a"], objective="partial", partial_credit="log1p")
    assert sqrt_value == pytest.approx(2 ** -0.5)
    assert linear_value == 0.5
    assert log_value == pytest.approx(0.6309297535714574)


def test_partial_credit_validation_is_eager_for_empty_problems():
    problem = build_logical_problem([], {})
    with pytest.raises(ValueError, match="unknown partial-credit"):
        objective_value(
            problem, [], objective="partial", partial_credit="unsupported")


def test_cost_solver_equal_ratio_tie_uses_canonical_successor_rule():
    paths = {
        "p3": ["sensor:c"],
        "p2": ["sensor:b"],
        "p1": ["sensor:a"],
        "p0": ["sensor:a"],
    }
    costs = {"sensor:c": 2, "sensor:b": 1, "sensor:a": 2}
    forward = build_logical_problem(
        ["sensor:a", "sensor:b", "sensor:c"], paths)
    reverse = build_logical_problem(
        ["sensor:c", "sensor:b", "sensor:a"],
        dict(reversed(tuple(paths.items()))),
    )
    # a and b have the same initial ratio (1.0).  The legacy set iteration had
    # no stable winner; the successor contract deliberately chooses canonical
    # a, while c has a lower ratio.
    for problem in (forward, reverse):
        result = greedy_cost_budget(
            problem, 2, costs, objective="any")
        assert result.selected_order == ("sensor:a",)
        assert result.objective_value == 2.0
        assert result.spent == 2.0


@pytest.mark.parametrize(
    "universe,paths,match",
    [
        (["sensor:a", "sensor:a"], {"p": ["sensor:a"]}, "duplicate"),
        (["sensor:a"], {"p": ["sensor:b"]}, "unknown sensors"),
        (["sensor:a"], {"p": ["sensor:a", "sensor:a"]}, "duplicate"),
        (["sensor:a"], {1: ["sensor:a"]}, "remain strings"),
    ],
)
def test_problem_contract_fails_closed(universe, paths, match):
    with pytest.raises(ValueError, match=match):
        build_logical_problem(universe, paths)


def test_cost_solver_rejects_implicit_mock_costs_and_invalid_units():
    problem = build_logical_problem(
        ["sensor:a", "sensor:b"], {"path": ["sensor:a", "sensor:b"]})
    with pytest.raises(ValueError, match="exactly match"):
        greedy_cost_budget(problem, 2, {"sensor:a": 1}, objective="partial")
    with pytest.raises(ValueError, match="finite positive"):
        greedy_cost_budget(
            problem, 2, {"sensor:a": 1, "sensor:b": 0}, objective="partial")


def test_unknown_selection_and_objective_fail_closed():
    _, problem = _fixture_problem()
    with pytest.raises(ValueError, match="unknown sensors"):
        objective_value(problem, ["sensor:not-real"], objective="any")
    with pytest.raises(ValueError, match="unknown coverage objective"):
        objective_value(problem, [], objective="unsupported")
