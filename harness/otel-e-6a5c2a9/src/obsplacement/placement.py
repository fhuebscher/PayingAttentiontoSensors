"""Pure logical-placement objectives and bounded greedy compatibility.

This module is the backend-neutral extraction of the retained TeaStore
coverage kernel.  It deliberately stops at *logical* sensor sets: source
activation closure, runtime feasibility, and heterogeneous cost measurements
belong to later contracts.  Consequently, a result from this module is not a
deployable observability configuration and is not evidence of optimality.

The cardinality solver preserves the pinned legacy queue behavior while
removing file I/O, plotting dependencies, and TeaStore defaults.  The
cost-aware solver is an intentional deterministic successor: the legacy loop
iterated a set, so equal gain/cost ratios could choose different sensors (and
even different later utility) under different hash seeds.  Here equal ratios
choose the canonical sensor id.  Neither solver supplies an optimality
certificate; an exact catalog-admissible structural-enumeration oracle is a separate migration
step.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Iterable, Literal, Mapping


CoverageObjective = Literal["any", "all", "partial"]
PartialCredit = Literal["sqrt", "linear", "log1p"]
StopReason = Literal["budget-exhausted", "no-positive-gain", "universe-exhausted"]


@dataclass(frozen=True)
class LogicalPath:
    """One scenario path and the logical evidence needed to reconstruct it."""

    id: str
    required_sensors: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("path id must be a non-empty string")
        if any(not isinstance(sensor, str) or not sensor for sensor in self.required_sensors):
            raise ValueError(f"path {self.id!r} has an invalid sensor id")


@dataclass(frozen=True)
class LogicalPlacementProblem:
    """Canonical in-memory logical placement instance.

    The canonical order is part of the contract so equal-gain choices have the
    same result across processes and Python hash seeds.
    """

    sensor_universe: tuple[str, ...]
    paths: tuple[LogicalPath, ...]

    def __post_init__(self) -> None:
        if self.sensor_universe != tuple(sorted(set(self.sensor_universe))):
            raise ValueError("sensor_universe must contain unique ids in canonical order")
        if any(not isinstance(sensor, str) or not sensor for sensor in self.sensor_universe):
            raise ValueError("sensor_universe contains an invalid sensor id")
        path_ids = tuple(path.id for path in self.paths)
        if path_ids != tuple(sorted(set(path_ids))):
            raise ValueError("paths must have unique ids in canonical order")
        universe = set(self.sensor_universe)
        for path in self.paths:
            unknown = sorted(path.required_sensors - universe)
            if unknown:
                raise ValueError(f"path {path.id!r} requires unknown sensors: {unknown}")


@dataclass(frozen=True)
class GreedySolution:
    """Deterministic greedy result; not an exact-optimality certificate."""

    objective: CoverageObjective
    partial_credit: PartialCredit
    selected_order: tuple[str, ...]
    objective_value: float
    history: tuple[float, ...]
    spent: float
    stopped: StopReason


def build_logical_problem(
    sensor_universe: Iterable[str],
    path_to_sensors: Mapping[str, Iterable[str]],
) -> LogicalPlacementProblem:
    """Build and strictly validate a canonical problem from in-memory values."""

    raw_universe = tuple(sensor_universe)
    if len(raw_universe) != len(set(raw_universe)):
        raise ValueError("sensor_universe contains duplicate ids")
    canonical_universe = tuple(sorted(raw_universe))
    paths: list[LogicalPath] = []
    for path_id, required in path_to_sensors.items():
        if not isinstance(path_id, str):
            raise ValueError("path ids must remain strings; implicit integer coercion is forbidden")
        raw_required = tuple(required)
        if len(raw_required) != len(set(raw_required)):
            raise ValueError(f"path {path_id!r} contains duplicate sensor ids")
        paths.append(LogicalPath(path_id, frozenset(raw_required)))
    return LogicalPlacementProblem(canonical_universe, tuple(sorted(paths, key=lambda path: path.id)))


def _selected(problem: LogicalPlacementProblem, selected: Iterable[str]) -> frozenset[str]:
    values = frozenset(selected)
    unknown = sorted(values - set(problem.sensor_universe))
    if unknown:
        raise ValueError(f"selection contains unknown sensors: {unknown}")
    return values


def _partial_credit(kind: PartialCredit, selected_count: int, required_count: int) -> float:
    if required_count <= 0:
        return 0.0
    ratio = min(1.0, selected_count / required_count)
    if kind == "sqrt":
        return math.sqrt(ratio)
    if kind == "linear":
        return ratio
    if kind == "log1p":
        return math.log1p(selected_count) / math.log1p(required_count)
    raise ValueError(f"unknown partial-credit function: {kind!r}")


def objective_value(
    problem: LogicalPlacementProblem,
    selected: Iterable[str],
    *,
    objective: CoverageObjective,
    partial_credit: PartialCredit = "sqrt",
) -> float:
    """Evaluate the retained unweighted logical coverage semantics.

    Empty path requirements contribute zero.  ``partial`` is a selection
    surrogate; ``all`` remains the strict downstream reconstructability
    measure.  The distinction is retained explicitly rather than hidden in a
    single generic "coverage" number.
    """

    if partial_credit not in ("sqrt", "linear", "log1p"):
        raise ValueError(f"unknown partial-credit function: {partial_credit!r}")
    chosen = _selected(problem, selected)
    if objective == "any":
        return float(sum(bool(path.required_sensors & chosen) for path in problem.paths))
    if objective == "all":
        return float(sum(
            bool(path.required_sensors) and path.required_sensors <= chosen
            for path in problem.paths
        ))
    if objective == "partial":
        return float(sum(
            _partial_credit(
                partial_credit,
                len(path.required_sensors & chosen),
                len(path.required_sensors),
            )
            for path in problem.paths
        ))
    raise ValueError(f"unknown coverage objective: {objective!r}")


def objective_summary(
    problem: LogicalPlacementProblem,
    selected: Iterable[str],
    *,
    partial_credit: PartialCredit = "sqrt",
) -> dict[str, float | int]:
    """Return the three normalized legacy views without choosing ground truth."""

    chosen = _selected(problem, selected)
    return {
        "any": objective_value(problem, chosen, objective="any"),
        "all": objective_value(problem, chosen, objective="all"),
        "partial": objective_value(
            problem, chosen, objective="partial", partial_credit=partial_credit),
        "numSelected": len(chosen),
    }


def _best_positive_gain(
    problem: LogicalPlacementProblem,
    selected: frozenset[str],
    candidates: Iterable[str],
    *,
    objective: CoverageObjective,
    partial_credit: PartialCredit,
    costs: Mapping[str, float] | None = None,
) -> tuple[str | None, float]:
    base = objective_value(
        problem, selected, objective=objective, partial_credit=partial_credit)
    best_sensor: str | None = None
    best_rank = 0.0
    for sensor in sorted(candidates):
        gain = (
            objective_value(
                problem,
                selected | {sensor},
                objective=objective,
                partial_credit=partial_credit,
            )
            - base
        )
        rank = gain if costs is None else gain / costs[sensor]
        # Sorted iteration is the explicit equal-gain/equal-ratio tie rule.
        if gain > 0.0 and (best_sensor is None or rank > best_rank):
            best_sensor, best_rank = sensor, rank
    return best_sensor, base


def greedy_cardinality(
    problem: LogicalPlacementProblem,
    budget: int,
    *,
    objective: CoverageObjective,
    partial_credit: PartialCredit = "sqrt",
) -> GreedySolution:
    """Legacy-compatible deterministic greedy selection under ``|S| <= k``."""

    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
        raise ValueError("cardinality budget must be a non-negative integer")
    selected: frozenset[str] = frozenset()
    order: list[str] = []
    history: list[float] = []
    stopped: StopReason = "budget-exhausted"
    discarded_nonpositive = False
    initial = objective_value(
        problem, selected, objective=objective, partial_credit=partial_credit)
    queue: list[tuple[float, str]] = []
    for sensor in problem.sensor_universe:
        gain = (
            objective_value(
                problem,
                {sensor},
                objective=objective,
                partial_credit=partial_credit,
            )
            - initial
        )
        heapq.heappush(queue, (-gain, sensor))

    # Retain the legacy lazy-greedy queue semantics.  The queue's sensor-id
    # secondary key is the explicit deterministic tie rule.  Replacing this
    # with a full rescan can choose a different member of an equal-gain class,
    # even though it reaches the same objective value.
    while len(order) < budget and queue:
        _, sensor = heapq.heappop(queue)
        if sensor in selected:
            continue
        base = objective_value(
            problem, selected, objective=objective, partial_credit=partial_credit)
        actual_gain = (
            objective_value(
                problem,
                selected | {sensor},
                objective=objective,
                partial_credit=partial_credit,
            )
            - base
        )
        next_best = -queue[0][0] if queue else 0.0
        if actual_gain >= next_best:
            if actual_gain <= 0.0:
                discarded_nonpositive = True
                # The pinned any/all implementation discarded this candidate
                # and continued scanning.  That distinction matters for the
                # non-submodular strict-all objective: a later candidate may
                # have acquired positive complementary gain.  The dedicated
                # partial implementation did stop at zero and retains that
                # behavior here.
                if objective == "partial":
                    stopped = "no-positive-gain"
                    break
                continue
            selected = selected | {sensor}
            order.append(sensor)
            history.append(base + actual_gain)
        else:
            heapq.heappush(queue, (-actual_gain, sensor))
    if len(order) < budget and not queue and stopped == "budget-exhausted":
        stopped = (
            "no-positive-gain" if discarded_nonpositive else "universe-exhausted"
        )
    return GreedySolution(
        objective=objective,
        partial_credit=partial_credit,
        selected_order=tuple(order),
        objective_value=objective_value(
            problem, selected, objective=objective, partial_credit=partial_credit),
        history=tuple(history),
        spent=float(len(order)),
        stopped=stopped,
    )


def greedy_cost_budget(
    problem: LogicalPlacementProblem,
    budget: float,
    costs: Mapping[str, float],
    *,
    objective: CoverageObjective,
    partial_credit: PartialCredit = "sqrt",
) -> GreedySolution:
    """Canonical gain/cost greedy with mandatory explicit positive costs.

    This is a deterministic successor to, not tie-for-tie equivalence with,
    the pinned legacy cost solver.  The legacy candidate set had no stable
    equal-ratio order; this implementation chooses the smallest canonical
    sensor id and exposes that choice through ``selected_order``.
    """

    if isinstance(budget, bool) or not isinstance(budget, (int, float)):
        raise ValueError("cost budget must be a finite non-negative number")
    budget = float(budget)
    if not math.isfinite(budget) or budget < 0:
        raise ValueError("cost budget must be a finite non-negative number")
    if set(costs) != set(problem.sensor_universe):
        missing = sorted(set(problem.sensor_universe) - set(costs))
        extra = sorted(set(costs) - set(problem.sensor_universe))
        raise ValueError(f"cost ids must exactly match the universe; missing={missing}, extra={extra}")
    normalized_costs: dict[str, float] = {}
    for sensor, raw_cost in costs.items():
        if isinstance(raw_cost, bool) or not isinstance(raw_cost, (int, float)):
            raise ValueError(f"cost for {sensor!r} must be a finite positive number")
        cost = float(raw_cost)
        if not math.isfinite(cost) or cost <= 0:
            raise ValueError(f"cost for {sensor!r} must be a finite positive number")
        normalized_costs[sensor] = cost

    selected: frozenset[str] = frozenset()
    order: list[str] = []
    history: list[float] = []
    spent = 0.0
    stopped: StopReason = "budget-exhausted"
    while True:
        affordable = {
            sensor for sensor in problem.sensor_universe
            if sensor not in selected and spent + normalized_costs[sensor] <= budget
        }
        if not affordable:
            stopped = (
                "universe-exhausted"
                if len(selected) == len(problem.sensor_universe)
                else "budget-exhausted"
            )
            break
        sensor, _ = _best_positive_gain(
            problem,
            selected,
            affordable,
            objective=objective,
            partial_credit=partial_credit,
            costs=normalized_costs,
        )
        if sensor is None:
            stopped = "no-positive-gain"
            break
        selected = selected | {sensor}
        order.append(sensor)
        spent += normalized_costs[sensor]
        history.append(objective_value(
            problem, selected, objective=objective, partial_credit=partial_credit))
    return GreedySolution(
        objective=objective,
        partial_credit=partial_credit,
        selected_order=tuple(order),
        objective_value=objective_value(
            problem, selected, objective=objective, partial_credit=partial_credit),
        history=tuple(history),
        spent=spent,
        stopped=stopped,
    )
