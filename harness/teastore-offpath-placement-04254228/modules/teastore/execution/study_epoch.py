#!/usr/bin/env python3
"""Study-epoch selector for the TeaStore candidate harness (2026-10-03).

Six epochs live side by side in this module tree:

* ``teastore-candidate-pilot-sys-v1``: the frozen 27-cell pilot (``candidate_pilot.py`` and its descriptor are
  byte-identical to c1724b1).  It is the active epoch whenever no selector file exists.
* ``teastore-traffic-sweep-v1``: the traffic sweep compiled by ``candidate_sweep.py``.  It is active only when the
  committed file ``modules/teastore/execution/study-epoch.json`` contains exactly
  ``{"schemaVersion": 1, "studyEpoch": "teastore-traffic-sweep-v1"}``.
* ``teastore-quiet-calibration-v1`` (protocol decision 48, 2026-10-04): 40 no-fault cells, each the sweep's no-fault
  cell, compiled by ``candidate_quiet.py``.  It is active only when the selector contains exactly
  ``{"schemaVersion": 1, "studyEpoch": "teastore-quiet-calibration-v1"}``.  It runs the sweep's code paths
  (``"sweep": True``) with its own compiler, plan and constants; the sweep epoch's files and digests are unchanged.
* ``teastore-traffic-sweep-b-v1`` (protocol decision 49, 2026-10-09): campaign B, 3 more blocks of the sweep's 12
  (regime, rate) cells (36 cells) on the H10/H4 harness (probe window and freeze stamps, carried by the plan cell's
  ``timing.faultHarness``), compiled by ``candidate_sweep_b.py``.  It is active only when the selector contains exactly
  ``{"schemaVersion": 1, "studyEpoch": "teastore-traffic-sweep-b-v1"}``.  A sweep-mode epoch like the quiet one; the sweep
  and quiet epochs' files and digests are unchanged.
* ``teastore-traffic-sweep-c-v1`` (protocol decision 82, BUDGET_C.md, 2026-10-10): campaign C, campaign B's shape
  exactly (36 cells, H10 and H4 as in B) with new blocks, run IDs and draws, compiled by ``candidate_sweep_c.py`` from
  campaign B's compiler.  It is active only when the selector contains exactly
  ``{"schemaVersion": 1, "studyEpoch": "teastore-traffic-sweep-c-v1"}``.  The sweep, quiet and B epochs' files and
  digests are unchanged.
* ``teastore-offpath-v1`` (BUDGET_TEASTORE_OFFPATH.md, 2026-10-14): the off-path pause of ``recommender`` with the ``auth``
  freeze as the on-path control and no-fault cells, login-only at 10 and 1 journeys/s, 5 blocks (30 cells), campaign B's cell
  shape and H10/H4 harness, compiled by ``candidate_offpath_ts.py`` from campaign B's compiler.  It is active only when the
  selector contains exactly ``{"schemaVersion": 1, "studyEpoch": "teastore-offpath-v1"}``; committing the selector is a
  separate activation commit.  The sweep, quiet, B and C epochs' files and digests are unchanged.

Every epoch-dependent constant of the runtime adapter, transport, remote controller, installer, cell producer,
validators and readiness checker is read from ``active()``.  With no selector the values equal the literals those
files held at c1724b1, so the frozen epoch's behaviour is unchanged.  A selector naming anything else, or a selector
that is not a regular file, refuses to load: no file falls back silently.  Committing the selector is a framework
commit, so every gate sentence is re-derived.

Runs as ``python3 -I`` on CPython 3.9 on the target: standard library only, sibling files are loaded by path.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import stat
import sys
from pathlib import Path
from typing import Any, Dict


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
SELECTOR_RELATIVE = "modules/teastore/execution/study-epoch.json"
FROZEN_EPOCH = "teastore-candidate-pilot-sys-v1"
SWEEP_EPOCH = "teastore-traffic-sweep-v1"
SELECTOR_DOCUMENT = {"schemaVersion": 1, "studyEpoch": SWEEP_EPOCH}
QUIET_EPOCH = "teastore-quiet-calibration-v1"
B_EPOCH = "teastore-traffic-sweep-b-v1"
C_EPOCH = "teastore-traffic-sweep-c-v1"
OFFPATH_EPOCH = "teastore-offpath-v1"
# Every selector document that loads, and the compiler of each sweep-mode epoch it names.
SELECTOR_DOCUMENTS = (
    SELECTOR_DOCUMENT,
    {"schemaVersion": 1, "studyEpoch": QUIET_EPOCH},
    {"schemaVersion": 1, "studyEpoch": B_EPOCH},
    {"schemaVersion": 1, "studyEpoch": C_EPOCH},
    {"schemaVersion": 1, "studyEpoch": OFFPATH_EPOCH},
)
COMPILER_RELATIVE = {
    SWEEP_EPOCH: "modules/teastore/execution/candidate_sweep.py",
    QUIET_EPOCH: "modules/teastore/execution/candidate_quiet.py",
    B_EPOCH: "modules/teastore/execution/candidate_sweep_b.py",
    C_EPOCH: "modules/teastore/execution/candidate_sweep_c.py",
    OFFPATH_EPOCH: "modules/teastore/execution/candidate_offpath_ts.py",
}

# The literals the frozen files held at c1724b1.  Changing any of these changes the frozen epoch.
FROZEN = {
    "studyEpoch": FROZEN_EPOCH,
    "sweep": False,
    "runCount": 27,
    "minimumFirstMutationRemainingSeconds": 29_100,
    "descriptorRelative": "pipelines/campaigns/teastore-candidate-pilot-sys-v1.json",
    "compilerRelative": "modules/teastore/execution/candidate_pilot.py",
    "scheduleVersion": "schedule-v1",
    "outerLeaseScope": "entire-27-cell-one-shot",
    "regimes": ("no-fault-cost", "auth-freeze-effect", "persistence-crash-effect"),
    "scenarios": {
        "no-fault-cost": None,
        "auth-freeze-effect": "auth-freeze",
        "persistence-crash-effect": "persistence-crash",
    },
    "postures": ("none", "selected", "full"),
    "blocksPerRegime": 3,
    "maximumOrdinal": 3,
    "selectorRelative": None,
}


class SelectorError(ValueError):
    """The study-epoch selector is present but does not name a known epoch exactly."""


def _reject_constant(value: str) -> None:
    raise SelectorError("non-finite JSON value in the study-epoch selector: %s" % value)


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SelectorError("duplicate key in the study-epoch selector: %s" % key)
        result[key] = value
    return result


def selector_path(root: Path = ROOT) -> Path:
    return Path(root) / SELECTOR_RELATIVE


def selected_epoch(root: Path = ROOT) -> str:
    """The epoch named by the committed selector, or the frozen epoch when there is no selector."""
    path = selector_path(root)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return FROZEN_EPOCH
    except OSError as exc:
        raise SelectorError("cannot inspect the study-epoch selector: %s" % exc)
    if not stat.S_ISREG(metadata.st_mode):
        raise SelectorError("the study-epoch selector is not a regular file")
    try:
        document = json.loads(
            path.read_bytes().decode("utf-8", errors="strict"),
            object_pairs_hook=_no_duplicates, parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SelectorError("the study-epoch selector is not JSON: %s" % exc)
    if (type(document) is not dict or document not in SELECTOR_DOCUMENTS
            or type(document.get("schemaVersion")) is not int):
        raise SelectorError("the study-epoch selector does not name %s, %s, %s, %s or %s exactly" % (
            SWEEP_EPOCH, QUIET_EPOCH, B_EPOCH, C_EPOCH, OFFPATH_EPOCH))
    return document["studyEpoch"]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SelectorError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sweep_compiler(root: Path = ROOT):
    """The compiler of the tree's sweep-mode epoch: ``candidate_quiet.py`` when the selector names the quiet
    calibration, ``candidate_sweep_b.py`` for campaign B, ``candidate_sweep_c.py`` for campaign C,
    ``candidate_offpath_ts.py`` for the off-path epoch, else ``candidate_sweep.py`` (as before, also for a tree without a
    selector)."""
    relative = COMPILER_RELATIVE.get(selected_epoch(root), COMPILER_RELATIVE[SWEEP_EPOCH])
    path = Path(root) / relative
    return _load("teastore_study_epoch_sweep_compiler_" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16], path)


def active(root: Path = ROOT) -> Dict[str, Any]:
    """Every epoch-dependent constant, for the tree at ``root``."""
    epoch = selected_epoch(root)
    if epoch == FROZEN_EPOCH:
        return dict(FROZEN)
    compiler = sweep_compiler(root)
    if compiler.EPOCH != epoch:
        raise SelectorError("the compiler of %s compiles %s" % (epoch, compiler.EPOCH))
    run_count = int(compiler.TOTAL_RUNS)
    result = {
        "studyEpoch": compiler.EPOCH,
        "sweep": True,
        "runCount": run_count,
        "minimumFirstMutationRemainingSeconds": int(compiler.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS),
        "descriptorRelative": compiler.DESCRIPTOR_RELATIVE,
        "compilerRelative": COMPILER_RELATIVE[epoch],
        "scheduleVersion": compiler.SCHEDULE_CONTEXT,
        "outerLeaseScope": "entire-%d-cell-one-shot" % run_count,
        "regimes": tuple(compiler.REGIMES),
        "scenarios": dict(compiler.FAULTS),
        "postures": tuple(compiler.POSTURES),
        "blocksPerRegime": int(compiler.EPISODES),
        "maximumOrdinal": int(compiler.CELLS_PER_BLOCK),
        "selectorRelative": SELECTOR_RELATIVE,
        "runWindowHours": int(compiler.RUN_WINDOW_HOURS),
        "maximumWallSeconds": int(compiler.MAXIMUM_WALL_SECONDS),
    }
    # Inputs of the compiler beyond its own file and descriptor (the quiet and B epochs read the sweep compiler and the
    # sweep descriptor; C and the off-path epoch read those and campaign B's compiler and descriptor); the runtime adapter
    # digest-binds them.  The sweep compiler declares none, so its dict is unchanged.
    additional = getattr(compiler, "ADDITIONAL_CONTROLLER_PATHS", None)
    if additional:
        result["additionalControllerPaths"] = dict(additional)
    return result


def flatten_plan_cells(plan: Any) -> list:
    """Cells in execution order: the sweep's ``blocks`` (seeded order), else the frozen ``regimeRoots``."""
    cells = []
    if isinstance(plan, dict) and isinstance(plan.get("blocks"), list):
        for block in plan["blocks"]:
            cells.extend(block.get("cells", []) if isinstance(block, dict) else [])
        return cells
    for regime in (plan.get("regimeRoots", []) if isinstance(plan, dict) else []):
        for block in regime.get("blocks", []):
            cells.extend(block.get("cells", []))
    return cells


def drain_allowance(receipt: Any) -> Any:
    """Seconds of the post-readiness drain allowance a sweep fault receipt carries, else None.

    Traffic sweep only (user decision 2026-10-03, "Q3 17 s"): the plan sets it to the client timeout + 2 s.
    A frozen or no-fault receipt has none, so its zero-failure rule is unchanged.
    """
    timing = receipt.get("timing") if isinstance(receipt, dict) else None
    value = timing.get("drainAllowanceSeconds") if isinstance(timing, dict) else None
    return float(value) if finite_positive(value) else None


def drain_excused(start: Any, readiness: Any, outcome: Any, allowance: Any) -> bool:
    """True for a journey that STARTED in [readiness, readiness + allowance) and did not succeed.

    Such a journey may fail without invalidating the cell (it meets the backlog released at the revert); it is
    recorded and excluded from the zero-failure rule and from the scored population.  No allowance: False.
    """
    if allowance is None or outcome == "succeeded":
        return False
    try:
        start, readiness = float(start), float(readiness)
    except (TypeError, ValueError):
        return False
    return readiness <= start < readiness + float(allowance)


def finite_positive(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and float(value) > 0)


def main() -> int:
    print(json.dumps(active(), indent=2, sort_keys=True, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
