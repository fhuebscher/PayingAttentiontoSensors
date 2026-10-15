#!/usr/bin/env python3
"""OTel Demo gate-driver configuration -- the thin per-SUT config object.

This is the ENTIRE OTel-specific surface the four driver scripts in this
directory need: one `SutConfig` instance. Everything else -- sentence
derivation and byte-exact verification, freshness rules, fail-closed writes,
SETUP-CAMPAIGN drift/expiry checks, the oneshot launch route, terminal
detection -- comes from `obsplacement.gate_driver` and is identical to what
TeaStore's campaign-proven drivers and Hotel's do.

DECISIONS RECORDED HERE (read before touching anything else in this directory)

* **target_host = fb14srv6.** From `candidate-target-allocation.json:host`,
  re-verified by `candidate_runtime.target_allocation()` against its own
  expected projection, and digested into every GATE-PLAN as
  `targetContractSha256`. srv6 shares its lease with Online Boutique Compose
  (`leaseScope: shared-srv6-host-exclusive-otel-then-online-boutique`), so
  the isolation rule serializes the two SUTs on this host.

* **transport_user = root.** `transportUsers: ["root"]` and
  `setupUsers: ["root"]` in the allocation; `ComposeSshAdapter` builds
  `f"root@{host}"` at all three of its transport sites; the GATE-PLAN,
  GATE-SETUP and GATE-RUN sentences all bake `transport=root@fb14srv6` into
  their text. Measured 2026-09-12: `ssh -o BatchMode=yes fb14srv6 id -un`
  answers `root`.

* **execution_user = stig -- NOT fhuebscher.** This is the one field a reader
  coming from Hotel will expect to be wrong, so it is stated at length.
  fb14srv6 carries BOTH accounts and both are in the docker group:
  `fhuebscher:1000` and `stig:1016`, `docker:x:998:...,fhuebscher,stig`
  (measured 2026-09-12). Hotel executes as `fhuebscher/1007` on fb14srv4 and
  TeaStore as `stig/1015` on fb14srv5; srv6's stig is `1016`, a third value.
  The choice is not free here: `stig`, `1016`, `1016` and `998` are baked
  into five places in the installed controllers --
  `candidate_setup.{EXECUTION_USER,EXECUTION_UID,EXECUTION_GID,DOCKER_GID}`,
  `candidate_remote.EXPECTED_TARGET`, the literal
  `runuser --user stig --group 1016 --supp-group 998` in
  `candidate_runtime.ComposeSshAdapter.launch`, the `chown 1016:1016` beside
  it, and the string `execution=stig:1016:1016+998` inside all three typed
  sentences. Configuring anything else would produce a sentence that states
  a transport nobody takes. `candidate_runtime_adapter.setup_authorization`
  refuses if this field and the allocation disagree.

* **supported_postures = {none, selected, async, full}.** The 36-cell offpath
  design (main repo `research/otel-offpath/DECLARATION.md`, 8194d74; errata
  24d3b5f, ff65eea) is 4 postures x 3 regimes (no-fault, fraud-pause,
  frontend-pause) x 3 blocks; `selected` = the synchronous checkout path,
  `async` = selected + kafka, frauddetectionservice, accountingservice. It
  succeeds the 24-cell v3 design (`/api/recommendations` workload). The
  offpath study epoch (`otel-demo-offpath-v1`) realizes all four under D13's
  no-telemetry-emitted reading, so `candidate_runtime.refuse_unsupported` no
  longer refuses on the descriptor. It still refuses on the *tombstone*:
  `ADMITTED_STUDY_EPOCHS = ()` in both `candidate_setup` and
  `candidate_remote` must name this epoch before any transport method may
  touch fb14srv6, and the runtime reads that tuple live
  (`candidate_runtime.admitted_study_epochs`). Admitting it is the governed
  edit described in drivers/README.md; nothing in this directory lifts it.

* **study / campaign_id name the offpath epoch; change stays the v2 admission
  change** (v3 and offpath have no OpenSpec change of their own; their authority is the
  declaration, see candidate_runtime.CHANGE_ID). `study` must equal
  `candidate_runtime.STUDY_EPOCH` and `candidate_pilot.EPOCH`, `change` must
  equal `candidate_runtime.CHANGE_ID` (the OpenSpec change
  `admit-otel-demo-candidate-pilot-v2`), and `campaign_id` must equal
  `candidate_runtime_adapter.CAMPAIGN_ID` **exactly** -- both hyphenated. All
  three appear literally in the typed sentences.

  Until 2026-09-18 the adapter derived an underscore form of this id
  ("dashes become underscores so the Compose project stays SAFE_NAME") and
  every derived path and the Compose project were named after that. That
  collided head-on with the shared library: `gate_run_flow._SAFE_CAMPAIGN_SLUG`
  is `[a-z0-9][a-z0-9-]{0,63}` and rejects an underscore, so the dry run
  refused with "campaignId 'otel_demo_candidate_pilot_v2' is not a safe slug".
  Widening that regex was not available -- it is shared with TeaStore and
  Hotel, 177 valid cells between them. The campaign id is therefore hyphenated
  end to end and the underscore derivation moved to the single place that
  wanted it, `candidate_runtime.compose_project_for`, which still produces
  `otel_candidate_v4_otel_demo_candidate_pilot_v2` unchanged. The derived
  target-side paths follow the ID, not the Compose name, because
  `candidate_remote` binds the artifact root's basename to `campaignId`.

* **A posture-probe receipt is a GATE-SETUP precondition.** The v2 descriptor
  declares `posture_connection_probe.sh` must print `PROBE OK` before any
  GATE-SETUP and after every upstream re-pin; `campaign_setup.py auto`
  refuses unless `record-probe` has stored a receipt bound to the pinned
  upstream commit and the probe script's bytes (see campaign_setup.py).

* **setup_campaign_window_hours stays the library default of 168** (D22, one
  typed sentence per SUT per week). Not restated below, deliberately: the
  window is a governance constant and belongs in one place.

* **run_window_hours = 11** (5 for 18 cells, 7 for v3's 24). `candidate_runtime.
  MINIMUM_REMAINING_SECONDS` is 36 000 (10 h) and `validate_gate_run` refuses
  a deadline that leaves less than that at first mutation. v3r1 took 5.32 h
  for 24 cells (13.3 min per cell: 120 s warm-up + 600 s window + cold start),
  so 36 cells are ~8.0 h of work plus a 15 s settle and a checkout readiness
  journey per cell; the 10 h floor leaves ~2 h margin, and 11 h (the library
  default) leaves 1 h between approval and first mutation and covers the
  target's per-cell 900 s deadline reserve (`candidate_remote.run_cell`).

WHAT IS NOT DONE HERE, and is not this file's to do: admitting a study epoch.
See drivers/README.md.
"""
from __future__ import annotations

from pathlib import Path

from obsplacement.gate_driver.contract import SutConfig

# The runtime worktree the drivers inspect, hash and ship from. Deliberately
# NOT under /private/tmp: macOS reaps /private/tmp worktrees' .git files and
# old content every ~3 days, which is shorter than one OTel campaign plus its
# terminal replay, and it struck TeaStore mid-chain once (10k_footview.md
# 2.8). Rebind this one line on every gate-rebinding event.
ROOT = Path(__file__).resolve().parents[3]

# 2026-10-03: study, campaign id and run window follow ROOT's committed study-epoch selector
# (modules/otel-demo/execution/study-epoch.json).  No selector: the offpath literals below, unchanged.  With one:
# the selected epoch's id and the window its compiler derives (candidate_sweep.RUN_WINDOW_HOURS), read from ROOT's
# own runtime module, so the drivers and the tree they ship cannot disagree.  ROOT itself is not rebound here.
SELECTOR = ROOT / "modules/otel-demo/execution/study-epoch.json"
STUDY = "otel-demo-offpath-v1"
CAMPAIGN_ID = "otel-demo-offpath-v1"
RUN_WINDOW_HOURS = 11
if SELECTOR.exists() or SELECTOR.is_symlink():
    import importlib.util as _importlib_util
    import sys as _sys

    _spec = _importlib_util.spec_from_file_location(
        "otel_gate_driver_config_runtime", ROOT / "modules/otel-demo/execution/candidate_runtime.py",
    )
    _runtime = _importlib_util.module_from_spec(_spec)
    _sys.modules.update({_spec.name: _runtime})     # its dataclasses resolve their module through sys.modules
    _spec.loader.exec_module(_runtime)
    STUDY = CAMPAIGN_ID = _runtime.STUDY_EPOCH
    RUN_WINDOW_HOURS = _runtime.RUN_WINDOW_HOURS
    del _spec, _runtime, _importlib_util, _sys

CONFIG = SutConfig(
    slug="otel-demo",
    study=STUDY,
    change="admit-otel-demo-candidate-pilot-v2",
    campaign_id=CAMPAIGN_ID,

    root=ROOT,
    # Unlike Hotel (whose plan_dir is accepted and unused), OTel's
    # `inspect_compiled_plan` genuinely reads `campaign-descriptor.json` and
    # `compiled-plan.json` out of this directory. The adapter materializes it
    # on demand with `candidate_pilot.materialize`, which is
    # exclusive-create-or-byte-compare: on an existing directory it is a
    # verification that raises on drift, not a regeneration.
    plan_dir=ROOT / ".local/candidate-v4/otel-demo/plan",
    gates_dir=ROOT / ".local/candidate-v4/otel-demo/gates",

    adapter_module="modules/otel-demo/execution/candidate_runtime_adapter.py",
    transport_module="modules/otel-demo/execution/candidate_transport.py",
    installer_module="modules/otel-demo/execution/candidate_release_installer.py",

    target_host="fb14srv6",
    transport_user="root",
    execution_user="stig",

    supported_postures=frozenset({"none", "selected", "async", "full"}),

    run_window_hours=RUN_WINDOW_HOURS,
)

# Where the driver scripts write their command traces and dry-run probes.
# Under `.local/` (gitignored) and NOT beside the scripts: a trace log written
# next to gate_run.py would make the worktree dirty.
DRIVER_SCRATCH = CONFIG.gates_dir.parent / "driver-scratch"

# A self-check, not a bypass guard: it can only fail if a future edit leaves
# `supported_postures` and this call disagreeing.
#
# TODO(posture-argument): if any OTel driver subcommand ever accepts a
# caller-chosen posture list, call `CONFIG.validate_postures(that_list)` at
# that call site, before any sentence is derived.
CONFIG.validate_postures(CONFIG.supported_postures)
