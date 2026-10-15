# Online Boutique held-out campaign: readiness inventory, 2026-10-10

Phase 1 of the Online Boutique (OB) task under `research/traffic-sweep/BUDGET_C.md` (d5b9af0). This file is the
inventory and its verdict. Nothing was launched, nothing on a host was changed, and no code, declaration or
analysis file was edited. Inventory written 2026-10-10, 17:43Z to about 19:00Z. Scope of every statement: instance
(one worktree at one commit, one read-only look at one host).

**Verdict: not launch-ready by 2026-10-11 18:00Z, and not realistic to make it so.**

- **Hours.** Engineering on the sweep's launch path is about 21 to 37 h, plus 4 to 12 h of first-contact defects, so
  about 25 to 49 h of work against 24 h of wall clock. The low end misses by only about one hour, so the hours alone
  are a weak basis for the verdict. The quiet epoch (P7, 2 to 4 h) comes on top, before the second campaign.
- **What decides it.** Four to six user decisions sit on the launch path: U-d (predecessor rule), O6/U-e (gates), U-a
  (governance registration), the declaration's mapping choices, U-c unless it is deferred, and the host. On srv4 there
  is also a host-provisioning step that needs its own yes: `/home/stig` is root-owned with mode 0700, and Compose is
  unusable as stig (P19, re-observed today).
- **The score.** Separately, no OB score is possible without a change to frozen code, because the v2.4/v3.1 reader has
  no OB system (P15).
- **Defect risk.** The defect prior is about 5 (range 3 to 8) from one SUT. That makes stop rule 2 (three
  critical-path harness defects) a real risk, not a certainty.

Phase 2 (DRY_RUN and draft declarations) was therefore **not** started. The options are in §6.

**Scope limit (O3 (a)).** The harness measures the Compose homepage subpath. Its goal is the one-hop
`frontend -> productcatalogservice` edge (`OB_HARNESS_LEDGER_20260923.md:118-124`). Any OB placement test on it is
labelled "Compose homepage subpath, instance".

## 1. What was checked, and how

| Check | Command or source | Result |
|---|---|---|
| OB worktree state | `git -C ../observability-placement-ob-successor log/status` | HEAD `0741d4a` (2026-09-23), clean tree, branch `codex/runtime-online-boutique-srv6-successor`. Nothing new since the ledger. |
| Analysis reader support | `/usr/bin/grep -n SYSTEMS research/detection-time/sweep_analysis_v2.py` | `:284 SYSTEMS = ("hotel", "teastore", "otel")`. `system_io()` (`:3431-3434`) maps only those three. v3.1 imports v2.4's `SYSTEMS` and `system_io` (`sweep_analysis_v3.py:1519,2406`). **No OB reader.** |
| Reader schema pinning | `sweep_analysis_v2.py:1485-1500`, `:1507-1512` | Each system's receipt and ledger key sets are pinned, and the `studyEpoch` is checked against `SYSTEM_<SUT>` in the registry. An unknown key set raises `UnknownSchema`, which is fail-closed. OB cells cannot be read as `--system otel` without a registry entry and a reader: OTel's epoch, entry service (`frontendproxy`) and ledger schema would all reject or mislabel them. |
| Host literals in the OB lineage | `/usr/bin/grep -cE "srv6\|fb14srv\|stig\|1016"` over 9 files | **184 lines in 9 files**: `candidate_runtime.py` 36, `candidate_srv6_transport.py` 32, `candidate_srv6_setup.py` 27, `candidate_runtime_selftest.py` 7, `candidate-target-srv6.json` 7, `candidate-runtime-contract.json` 3, `extension-ledger.yaml` 6, `README.md` 3, `tests/test_online_boutique_candidate_runtime.py` 63. Some of these are file names with "srv6" in them. TeaStore's host rebind cost 293 lines in 8 files (`TEASTORE_SRV6_REPLICATION_LAUNCH.md`). |
| fb14srv4, read-only | `ssh -o BatchMode=yes -o IdentitiesOnly=yes fb14srv4 'id stig; id fhuebscher; command -v runuser; docker version; docker compose version; getent group docker; docker ps; docker compose ls; df -h; nproc; python3 --version'`, 2026-10-10 17:45Z | Idle: no containers and no Compose projects. `stig` **exists**, as uid/gid **1008** with groups `{1008, 998}`. The OB code pins **1016** (srv6's stig). `docker` gid 998, the same as srv6. Docker server **29.6.1**, API 1.55, minimum API 1.40, so the `/v1.41` sampler works. Compose v5.3.1. runuser is at `/usr/sbin/runuser`, which `0741d4a` resolves on the target. 12 threads. Python 3.9.2. `/var` has 218 GB free, above the 40 GB guard. A second read-only look: `/home/stig` is **root 0700**, holds only a root-owned `observability-placement-runs`, and stig has no Compose plugin (`~/.docker/cli-plugins` is absent). This matches `research/prep-20260925/SRV4_PREP.md:15-16` (2026-09-26), whose fixes M1 (chown) and M5 (user Compose plugin) still wait for a yes (`NEXT_STEPS_20260925.md:265`). The `docker compose` above ran as root, not as stig. |

## 2. Readiness inventory

Each sweep requirement comes from BUDGET_C and from the OTel and Hotel sweep and quiet declarations: rates 10, 1, 0.2
and 0.05/s; a 180 s window; a 60 s hold at a seeded onset; posture `full`; one pause/freeze and one CPU throttle; three
blocks for a held-out-by-block score; and 40 quiet cells. "Exists" means present in code at `0741d4a`. The OB **candidate
runtime** has never executed on a host (`research/five-module-readiness.json`: `candidate: absent`). Only the
module's earlier smoke ran: on srv5 on 2026-08-09, and in Compose p0c (`:111-124`).

| # | Piece | State at `0741d4a` | Missing | Est. h |
|---|---|---|---|---|
| P1 | **Traffic driver at the four rates** | Partly. `workload/candidate_home.py:274` `run(rate=, duration=, concurrency=, timeout=)` schedules open-loop offsets from a shared barrier, which is the right shape. | The regime set is hard-coded to the pilot's two (`:280`). The terminal requires exactly 150 rows (`validation/candidate_terminal.py:483`). The 30 s warm-up at 10/s, the seeded onset (60 s plus one inter-arrival) and per-rate offered counts (1800, 180, 36, 9) do not exist. The 18-cell plan is a literal (`candidate_runtime.py:43 RUN_COUNT = 18`, `:211`, `:240`, `:288`, `:744`). | part of P6 |
| P2 | **Pause/freeze actuator** | Exists: `inject_fault` (`candidate_runtime.py:946-1005`) runs `compose pause productcatalogservice` with a receipt and readiness after revert. | Retiming to the sweep's onset and hold. The F1 receipt fields the vendored gates read. Probe windows in the receipt's `probes` form, as Hotel and OTel have. | 1–2 |
| P3 | **CPU-throttle actuator** | **Absent.** No `docker update --cpus` anywhere in OB (`/usr/bin/grep -n "cpus\|docker update\|throttle"`: 0 hits). | A new OB actuator: a quota, a revert to the original quota or a lift to `nproc` (12 on srv4, because `--cpus 0` is a no-op), a readback and a receipt. Ports exist to copy from: OTel and TeaStore `candidate_sweep.py`, and Hotel `lmt_faults.py` (including the `hotel-srv4` worktree). | 1.5–2.5 |
| P4 | **Request ledger and correlation** | Exists: per-request token, frontend echo patch (`candidate_materialize.py:40-108`), token-to-root join in the terminal (`candidate_terminal.py:183-230`). | A ledger schema the reader can pin. The H4/H10 records campaign B added. A trace-completeness record (decision 25). | 1–2 |
| P5 | **Protocol gates F1/G1/G2/G4 on the target, replayed by the terminal** | **Absent.** No `protocol_gates.py` in OB (`ls modules/online-boutique/validation`). | The gate source already exists (`src/obsplacement/protocol_gates.py`, byte-identical to the three vendored copies). Vendoring is a copy. The new work is the wiring, per cell on the target and in the terminal replay. | 2–3 |
| P6 | **Sweep study epoch** (descriptor, compiled plan, Fisher-Yates schedule, 3 blocks × 3 regimes × 4 rates = 36 cells, receipts, tombstone and selector, terminal) | **Absent.** The only epoch is `online-boutique-compose-candidate-pilot-v1` (18 cells, three postures, 30 s + 150 s at 1 rps). | The whole epoch. OTel's equivalent (`2184ef0`) was +4,444 lines in 13 files. It took about 4 h from the budget commit `6a06818` (02:36Z) to the epoch commit `2184ef0` (06:34Z), and about 9 h to the frozen declaration `da95915`, on a harness that had already executed several campaigns (runs 1–3, v3, offpath). OB's runtime has the 18-cell shape as literals throughout (roadmap §3b), so most guards have to be re-costed. | 8–14 |
| P7 | **Quiet calibration epoch** (40 no-fault cells, 10 blocks × 4 rates) | **Absent.** | A second epoch after P6. OTel's (`36d2e15`) was +1,680 lines. | 2–4 |
| P8 | **Host rebind srv6 → srv4** | Bound to srv6 by literal: `TARGET_HOST`, `root@fb14srv6` in the transport argv (`:151,277,339,394,404,408,435`), uid 1016 (`setup:31-32`, `runtime:59,1385,1540,1543`, `transport:349,352`), the exact `getgroups == [998, 1016]`, and `.srv6-runtime.lock`. | 184 lines in 9 files, srv6 to srv4 and 1016 to 1008. Docker 29.6.1 and gid 998 already match srv4. The file names (`candidate_srv6_*`, `candidate-target-srv6.json`) are bound into the release manifest and governance, so renaming them or keeping them as stale labels is a choice in itself. | 3–5 |
| P9 | **Predecessor coupling** | `validate_predecessor_release` (`candidate_runtime.py:554-586`) requires an **OTel** `srv6-otel-host-release-v1` receipt written at most 30 min before readiness (`:568`, `:583`). | No OTel runs on srv4, so readiness cannot pass as written. It needs an OB-native idle-host release receipt (ledger U-d), which is a readiness validity predicate and therefore **a user decision**. | 1–2 after the decision |
| P10 | **Transport: readiness round trip and proof that the unit ran** | Ledger D3 (no transport step carries `preflight` or `runtime-readiness.json`) and D2 (`systemd-run` exit 0 does not prove the unit is running). Both still hold at `0741d4a`. | Bounded `preflight` and `fetch-readiness` transport steps. A `LoadState`/`ActiveState` poll plus a journal tail. Port OTel `b0ba8a7`. | 3–4 |
| P11 | **Launcher with DRY_RUN and wandb mirror** | **Absent.** There is no `launch_ob.sh`, unlike `launch_hotel.sh` and `launch_teastore.sh`. | A launcher, a DRY_RUN path, a wandb mirror (`tools/wandb_campaign.py`), and archiving of a stranded `gate-run.json` and the lease. | 1.5–2 |
| P12 | **Gates** | OB keeps its own **typed** chain (O6 (a)): GATE-PLAN, GATE-SETUP and GATE-RUN, each a typed sentence (`candidate_runtime.py:293-312,405-420,750-786`). `attempt: 1` is a literal (`:720,744`), and the release root is one-shot per commit (`candidate_srv6_setup.py:240-241`). | Under O6 (a) a human types GATE-RUN. The code does not check that a human typed it: the validators check byte-equality of the sentence and a non-empty `approvedBy` (`:302-308,763-767`). Moving to derived gates would therefore be a writer change in code, and it is a governance question for **the user**. Note that derived gates bring back the shared gate-driver seam, which caused at least 7 of OTel's 12 first-contact defects, if the shared library is used. An attempt parameter is needed (OTel `da9eca1`). | 1–2 |
| P13 | **Governance** | Ledger D4: the 10 runtime files are not owned by any OpenSpec change, which is the one red test (`test_science_epoch_router_v3`). D5: the stale construction blockers still sit in `compile_plan()` output. | Registration in an OpenSpec change (U-a, **user decision**), stale-blocker removal, and a re-pin after every commit, as OTel did after each change. | 2–3 |
| P14 | **Exporter self-telemetry as interference** (O4 (a)) | Post-window only, as a diagnostic (`validation/signal_channel.py:200-216`). | An in-window count per cell, a terminal replay and a reader row. The counting rule is U-c, **a user decision**. | 2–4 |
| P15 | **Analysis reader (v2.4/v3.1) OB system** | **Absent** (§1). | An OB registry profile (`SYSTEM_OB`, `EPISODES_OB`, `ACTUATOR_READBACK_OB`, `P3_TRAFFIC_INDEPENDENT_OB`, `AVAILABILITY_SOURCES_OB`, `P2_DOBS_S_OB`, `SCHEMAS["ob"]`, route services), an OB `find_cells`/`load_or_invalid`, tests, an independent review, and a new freeze digest. **This changes frozen code** (`sweep_analysis_v2.py` 075c43e5 / `parameters.json` 7447b492, frozen at 891a4c3, and `sweep_analysis_v3.py` 2e7ec5c3 / `parameters_v3.json` f6257b78, frozen at 990d501). **User decision; not touched.** It is not on the launch path, but it gates any OB score. | 4–8 |
| P16 | **Placement code reads OB** | `research/placement/` does not exist yet at `d9638e1` (`ls`). It is due 2026-10-11 12:00Z and frozen by 18:00Z, and it reads through the frozen v3.1 loaders (`BUDGET_PLACEMENT.md:14`, step 2). | Without P15 there is no OB loader for it to call. Adding OB after the placement code freeze **may** be a second frozen-code change, unless the placement code dispatches through v3.1's `SYSTEMS`/`system_io`. Not yet written (—). | — (depends on P15) |
| P19 | **srv4 host provisioning** | `/home/stig` is root 0700 and stig has no usable Compose (§1). OB setup writes under `/home/stig` (`candidate_srv6_setup.py:36-37,239-241`). | M1 (chown `/home/stig`) and M5 (Compose user plugin for stig) from `SRV4_PREP.md`. Each is a host mutation needing its own yes; scripts exist in `tmp/srv4-prep/mutations/`. Also whether OB is fine with Compose 2.32.4 (M5's pin) instead of 5.3.1. | — (blocked on a yes) |
| P17 | **Declarations** (sweep and quiet) | **Absent.** | Route, entry, client timeout, concurrency, fault targets and the two fault classes are mapping choices. The user accepted these per SUT for OTel (decision 23, "accept all"). They follow P6 and P7 because they cite descriptor and plan digests. | 1.5–2 |
| P18 | **First-contact defects** | The candidate runtime has never executed. OTel went from green-offline to 18/18 through 12 first-contact defects, at least 7 of them from the shared gate-driver seam, which O6 (a) avoids (`OB_HARNESS_LEDGER_20260923.md:143-148`). | The ledger's prior is about 5 defects (range 3 to 8) at 1 to 1.5 h each, from one SUT. That rate is an assumption (OTel's per-defect hours are not recorded: —). | 4–12 |

**Sum.**

- **Launch path.** P1–P6, P8–P14 and P17 come to about **27 to 48 h** of engineering on the sweep's launch path.
- **Reduced.** That falls to about **21 to 37 h** under two conditions: P14 is deferred by decision (counted as
  interference later, which saves 2–4 h), and an assumed 5–7 h of P8/P10/P13 work overlaps with P6. The overlap figure
  is a guess, not a measurement.
- **First contact.** Add P18, 4 to 12 h, which is serial on the host.
- **Off the launch path.** P7 (2–4 h) is needed before the quiet campaign. P15 (4–8 h) gates the score. P19 is blocked
  on a yes, with hours unknown (—).

## 3. Critical path

Decisions (U-d predecessor, gates, governance registration, mapping choices, P19 host mutations) → P8 rebind + P9 → P6 sweep epoch
(including P1, P2, P3, P4, P5) → P10 transport + P11 launcher → setup on srv4 (first host contact: the one-shot release
root, image builds for frontend/productcatalog/currency, never timed: —) → readiness → DRY_RUN → first-contact
defects (P18) → declaration committed alone → launch. P7 (quiet) and P17 run in parallel after P6.

Parallelism is limited. P1–P6, P8–P10 and P12 all edit `candidate_runtime.py` and the transport. Every commit forces
a governance re-pin, and first-contact iterations are serial on one host. Subagents help with P7, P15 (if approved)
and P17, not with the spine.

Host time after launch-ready: the 36-cell sweep is about 3.1 h, using OTel's measured cell period of about 310 s
(`DECLARATION_QUIET_OTEL.md:107`) as a proxy, since OB has no timing (—). The 40 quiet cells are about 3.4 h. The two
run back to back on srv4 (one campaign per host) for about 6.5 to 7 h, plus setup and builds. That fits the 18 h between
launch-ready and terminal **only with no relaunch**. The one-shot release root and `attempt=1` make each relaunch
cost a commit and a host-side archive.

## 4. Why "launch-ready by 2026-10-11 18:00Z" is not realistic

1. **Hours.** About 25 to 49 h of work (launch path plus first contact) against 24 h of wall clock from 17:45Z
   today. Most of it is serial (§3). The low end is close to the budget, so this reason alone is weak.
2. **Stop rule 2 is a real risk.** The ledger's prior is about 5 first-contact defects (range 3 to 8), taken from
   one SUT. OTel had 12, but at least 7 of them came from the gate-driver seam that O6 (a) avoids. Three
   critical-path harness defects stop the system. This is a prior, not a measurement.
3. **User decisions on the launch path, four to six of them:** U-d (predecessor rule; srv4 cannot satisfy the
   OTel-release predicate), O6/U-e (who types GATE-RUN, or move to derived gates), U-a (OpenSpec registration), the
   declaration's mapping choices, U-c (self-telemetry counting rule) unless it is deferred, and the host. On srv4
   there are also two host mutations, M1 and M5 (P19), each needing its own yes.
4. **Host.** BUDGET_C:14 says "fb14srv4 unless its harness binds another host", and this harness binds **fb14srv6**
   (O5 (a)). On srv6, P8 disappears and P9 is met as built: OTel's protocol harness still emits
   `srv6-otel-host-release-v1` with `successor: online-boutique` (`../observability-placement-runtime-otel-protocol`
   `candidate_remote.py:2576,2585`). srv6 is ruled out by scheduling, not by code. Campaign C's OTel run holds srv6
   until its own terminal deadline, 2026-10-12 12:00Z, which is also OB's terminal deadline. And OB must start within
   30 min of OTel's release (P9) and then needs about 6.5 h or more of host time. So srv4 is the only host that could
   meet BUDGET_C, at the cost of P8, P9 and P19.
5. **Separately, no OB score is possible without a change to frozen code** (P15; and P16 **may** need one). That is a
   preregistration matter regardless of the harness.

## 5. Facts that change the earlier ledger (2026-09-23)

- `stig` exists on fb14srv4 (uid 1008, groups 1008 and 998). This was already on record in `SRV4_PREP.md:15`
  (2026-09-26); the roadmap's "stig does not exist on srv4" predates it. The rebind changes the uid, not the user.
  But `/home/stig` is root 0700, and stig has no usable Compose (P19).
- Docker 29.6.1 and the docker gid 998 match srv4, so those pins survive the rebind. The system Compose is v5.3.1,
  but it is unusable as stig per `SRV4_PREP.md:16`. The `compose ls` JSON field names are still unverified under v5.
- `runuser` on srv4 is at `/usr/sbin/runuser`. `0741d4a` resolves it on the target, so no change is needed.
- The OB suite count (1625 passed, 1 failed) is the ledger's, recorded 2026-09-23. It was **not** re-run here.

## 6. Options for the user (no recommendation is binding; the stop rule says stop and ask)

- **(a) Stop OB under BUDGET_C stop rule 1 now and record it.** The placement test rests on campaign C (TeaStore,
  OTel). Decision 74 already allows the clean test to be "a campaign run after this design is frozen (or Online
  Boutique)". OB stays an unspent hold-out for a later round.
- **(b) Extend the OB deadline by about 3 to 4 working days**, with a new budget committed alone. Decide P15 (the reader
  extension as a new frozen version, for example v3.2, reviewed and frozen before any OB cell is read) and U-d, O6,
  U-a and the srv4 host mutations M1/M5 up front (or schedule OB on srv6 after campaign C has released it). Then run Phase 2 as specified.
- **(c) A reduced OB check inside a shorter extension:** the sweep only (36 cells, no quiet cells), with false alarms
  calibrated from its 12 no-fault cells alone. That is a departure from the procedure being tested, and so a
  preregistration decision. It saves P7 and about 3.4 h of host time, but not P6, P8–P13 or P18, which are the bulk.

Recommendation, in the protocol's own terms: (a) for this budget. (b) if OB as the held-out system is to be spent at
all, because (c) would test a different procedure.

## 7. Not done, by instruction or by verdict

- No DRY_RUN, no setup on srv4, no host writes. The only host contact was the two read-only `ssh` calls in §1.
- Independent review: a Fable `adversarial-review` subagent (read-only, same session, not cross-provider; the `judge`
  MCP server failed to connect). It confirmed every count and citation it checked and the verdict. Its should-fix
  findings were applied: the srv4 provisioning (P19), the srv6 option, the defect prior, the verdict wording, P16,
  the scope limit, P5, P3, P12 and the P6 timing. The revised text was not re-reviewed.
- No edit to `sweep_analysis_v2.py`, `sweep_analysis_v3.py`, `parameters*.json`, the OB worktree, or any declaration.
- Draft declarations `DECLARATION_OB_SWEEP_DRAFT.md` and `DECLARATION_OB_QUIET_DRAFT.md` were **not** written. Phase 2
  depends on a feasible Phase 1.
