#!/usr/bin/env python3
"""Hotel Reservation gate-driver configuration -- the "thin per-SUT config"
plugged into obsplacement.gate_driver (candidate_common, plan node B1).

This is the ENTIRE Hotel-specific surface the four driver scripts in this
directory need: one `SutConfig` instance. Everything else -- sentence
derivation and byte-exact verification, freshness rules, fail-closed writes,
SETUP-CAMPAIGN drift/expiry checks, the oneshot launch route, terminal
detection -- comes from the shared library and is identical to what
TeaStore's campaign-proven drivers do.

CONTRACT STATUS (read this before touching anything else in this directory):

  CONTRACT-COMPLETE now:
    - This config object: all identity/host/user/posture fields below are
      final (target=fb14srv4, execution_user=fhuebscher/1007 -- NOT stig,
      postures={full, sample-zero}; none/selected are outside
      `supported_postures` and `SutConfig.validate_postures` refuses them).
      Scope of that refusal, stated precisely because the earlier wording
      overclaimed: these two are the only postures the orchestrator ever
      compiles, and no flow function in the shared library currently threads
      a caller-chosen posture list, so the module-level self-check below is
      a *drift guard* on this file, not a guard on a bypass that exists
      today. The moment any driver subcommand grows a `--posture`-shaped
      argument, that call site must call `CONFIG.validate_postures(...)` on
      the caller-supplied list before anything else -- see the TODO below.
    - The four driver scripts in this directory (gate_setup.py, gate_run.py,
      campaign_setup.py, campaign_status.py): argparse plumbing, printing,
      and wiring into obsplacement.gate_driver's flow layer are done and
      structurally mirror scratchpad/gate-drivers/*.py exactly.

  RESOLVED 2026-09-05 (both halves integrated on one branch):
    - `root`: the pinned runtime worktree, a detached checkout of the exact
      commit the GATE-PLAN binds (see the ROOT constant below for why it is
      not under /private/tmp). Rebinding it is a one-line edit, same as a
      TeaStore gate-rebinding event.
    - `plan_dir`: accepted and unused by Hotel's adapter -- `inspect_campaign`
      compiles the plan from the digest-frozen descriptor
      (pipelines/campaigns/hotel-reservation-candidate-pilot-v1.json) rather
      than from a materialized plan directory. Kept only because `SutConfig`
      requires the field.
    - `adapter_module` / `transport_module` / `installer_module`
      now name three real files that exist in the runtime worktree at `root`
      (branch `codex/runtime-hotel-srv4-reviewed`). Hotel's orchestrator is a
      single 4000-line `candidate_runtime.py`; rather than point all three
      constants at that one file, it grew three thin sibling shims beside it
      (`candidate_runtime_adapter.py`, `candidate_transport.py`,
      `candidate_release_installer.py`) that delegate into it. The
      orchestrator itself is untouched by them, so their existence does not
      move `controllerSha256` (`CONTROLLER_PATHS` in the orchestrator
      enumerates the thirteen files that do).
    - `transport_user`: D10 RESOLVED 2026-09-05 as **root**. The orchestrator's
      `TARGET` declares `transportUser=root, setupUser=root,
      executionUser=fhuebscher/1007`, every one of its ssh/scp invocations
      is a literal `root@fb14srv4`, and the GATE-RUN sentence it derives
      bakes `transportUser=root` in. `~/.ssh/config`'s `Host fb14srv4`
      block is `User root` with both keys pinned under `IdentitiesOnly yes`
      (measured 2026-09-05: `ssh fb14srv4 id -un` -> root). The earlier
      `fhuebscher` value here described a login that works but that the
      orchestrator never uses; a SETUP-CAMPAIGN sentence carrying it would
      have stated a transport that was not the one taken.
      `tests/test_hotel_gate_driver_config.py` pins this field to the
      orchestrator's own declaration so the two cannot drift apart again.

  With the shims in place, `check_adapter_contract` /
  `check_transport_contract` now pass against the real modules. The next
  fail-closed stop a subcommand hits is the orchestrator's own
  `_verify_git`, which refuses to inspect bindings while the runtime
  worktree is dirty (`--untracked-files=all`): nothing can be derived
  against an uncommitted tree, by design.
"""
from __future__ import annotations

from pathlib import Path

from obsplacement.gate_driver.contract import SutConfig

# The pinned runtime worktree the drivers inspect, hash and ship from. It is
# a *sibling* of the development checkout, deliberately not under
# /private/tmp: macOS reaps /private/tmp worktrees' .git files and old
# content every ~3 days, which is shorter than one Hotel campaign plus its
# terminal replay (see the "tmp worktrees get reaped" note and the damaged
# /private/tmp/observability-placement-runtime-hotel-srv4-reviewed). Rebind
# this one line on every gate-rebinding event, exactly like TeaStore's ROOT.
#
# 2026-09-18, read this before debugging any "the fix is in the file but the
# target disagrees" refusal: ROOT is the ONLY tree the drivers read. Editing
# a module in the development checkout -- this worktree included -- changes
# nothing the target ever sees until ROOT is advanced to the commit carrying
# the edit. Hotel #5 refused setup three times with "foreign dps_training_k
# nuisance identity or states differ" after the foreign-state pin had been
# corrected in five sites on this branch, because ROOT still sat at 8a28933
# and shipped the old {"created":1,"running":5} literal to fb14srv4. The
# guard was right, the file that was read was the wrong file. Two tells that
# would have cut the search short: the gates working set stamps every attempt
# directory with ROOT's commit (attempt-*-8a289339), and there are three
# Hotel candidate_runtime.py copies on this machine, only one of which is
# ROOT's -- the shell's `grep` wrapper hides two of them because they sit
# under gitignored paths. Enumerate with `find`, and check the commit, not
# the file you just edited.
ROOT = Path(
    "/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/"
    "observability-placement-runtime-hotel-protocol"
)
# 2026-10-03: rebound from -hotel-srv4 to this worktree for hotel-traffic-sweep-v1 (user-approved activation).

def _active_epoch(root: Path) -> tuple:
    """(study epoch, run-window hours) of the tree the drivers read.

    2026-10-03 (hotel-traffic-sweep-v1): no selector at ROOT means the frozen epoch, with the literals this
    file held at e4fd4c7. With `execution/study-epoch.json` committed at ROOT, the epoch and the window come
    from ROOT's own runtime, so the GATE-RUN deadline matches the budget that runtime enforces (the adapter
    refuses any campaign_id other than runtime.STUDY_EPOCH).
    """
    if not (root / "modules/hotel-reservation/execution/study-epoch.json").exists():
        return "hotel-reservation-selected-v1", 5
    import importlib.util
    import sys
    path = root / "modules/hotel-reservation/execution/candidate_runtime.py"
    spec = importlib.util.spec_from_file_location("hotel_gate_driver_config_active_runtime", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if module.MAXIMUM_WALL_SECONDS % 3600:
        raise ValueError("the active epoch's wall budget is not a whole number of hours")
    return module.STUDY_EPOCH, module.MAXIMUM_WALL_SECONDS // 3600


STUDY_EPOCH, RUN_WINDOW_HOURS = _active_epoch(ROOT)

CONFIG = SutConfig(
    slug="hotel-reservation",
    study=STUDY_EPOCH,
    change="admit-hotel-reservation-candidate-runtime",
    campaign_id=STUDY_EPOCH,

    root=ROOT,
    plan_dir=ROOT / ".local/candidate-v4/hotel-reservation/plan",
    gates_dir=ROOT / ".local/candidate-v4/hotel-reservation/gates",

    # Three thin shims beside the orchestrator, each delegating into
    # candidate_runtime.py -- see module docstring.
    adapter_module="modules/hotel-reservation/execution/candidate_runtime_adapter.py",
    transport_module="modules/hotel-reservation/execution/candidate_transport.py",
    installer_module="modules/hotel-reservation/execution/candidate_release_installer.py",

    target_host="fb14srv4",
    # D10: the orchestrator transports as root and executes as fhuebscher;
    # see the module docstring. Pinned equal to candidate_runtime.TARGET.
    transport_user="root",
    execution_user="fhuebscher",  # NOT stig -- fb14srv4's user is fhuebscher/1007.

    # Hotel's posture shape: none/selected are structurally unsupported (no
    # upstream service-level source guard), not merely untested -- see
    # 10k_footview.md section 3. Any attempt to run those postures must be
    # rejected before a sentence is even derived (CONFIG.validate_postures).
    # Hotel `selected` (branch selected-20260929): none, metrics, frontend-only tracing, full.
    supported_postures=frozenset({"none", "metrics", "selected", "full"}),

    # Hotel's own runtime policy, NOT the library default of 11 hours (which
    # is TeaStore's number, carried into the generic `SutConfig` default).
    # modules/hotel-reservation/execution/runtime-policy.json bounds a GATE-RUN
    # deadline to [minimumFirstMutationRemainingSeconds, maximumWallSeconds +
    # maximumClockSkewSeconds] = [17700, 18005] seconds, i.e. [4.9166h,
    # 5.0014h]; `candidate_runtime.validate_gate_run` refuses anything outside
    # that window. An 11-hour deadline would be refused by the orchestrator
    # every single time. Deriving GATE-RUN immediately before typing it is
    # what keeps the elapsed time inside the 300s of slack this leaves.
    run_window_hours=RUN_WINDOW_HOURS,
)

# Where the driver scripts write their command traces and dry-run probes.
# Deliberately under `.local/` (gitignored) and NOT beside the scripts: the
# drivers live inside the runtime worktree, and the orchestrator's
# `_verify_git` refuses to derive anything while the worktree status
# (untracked files included) reports a single entry -- a trace log written
# next to gate_run.py would block the very next derivation.
DRIVER_SCRATCH = CONFIG.gates_dir.parent / "driver-scratch"

# A self-check, not a bypass guard: it can only fail if a future edit leaves
# `supported_postures` and this call disagreeing. Kept because the two lines
# are the only place Hotel's posture vocabulary is written down, and a silent
# disagreement between them is exactly what `validate_postures` exists to
# make loud.
#
# TODO(posture-argument): if any Hotel driver subcommand ever accepts a
# caller-chosen posture list, call `CONFIG.validate_postures(that_list)` at
# that call site, before any sentence is derived. Until such an argument
# exists there is no caller-supplied list to validate.
CONFIG.validate_postures(CONFIG.supported_postures)
