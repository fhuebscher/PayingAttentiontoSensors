# OTel Demo gate drivers (fb14srv6, execution user `stig`/1016)

Same five-gate chain as TeaStore and Hotel; all governance lives in
`obsplacement.gate_driver`. `PYTHONPATH=<worktree>/src` is mandatory.

## Blocked before any of this runs -- one governed edit, not a bug

`propose-campaign`, `authorize-campaign --typed`, `record-probe`, `status`,
`record-plan` and `archive-run` work **today, offline**. `auto`, `install`,
`readiness`, `dryrun` and `oneshot` all stop at the epoch tombstone, by design:

| refusal | where |
|---|---|
| `ADMITTED_STUDY_EPOCHS = ()` (must name `otel-demo-candidate-pilot-v2`) | `candidate_setup.py` and `candidate_remote.py`, read live by `candidate_runtime.admitted_study_epochs` so every local transport method refuses too |
| no posture-probe receipt | `campaign_setup.py auto` (`require_probe_receipt`) |

The **v2 study epoch** (`pipelines/campaigns/otel-demo-candidate-pilot-v2.json`,
OpenSpec change `admit-otel-demo-candidate-pilot-v2`) realizes `none` and
`selected` under D13's no-telemetry-emitted reading, so
`candidate_runtime.refuse_unsupported` no longer refuses on the descriptor; the
v1 descriptor's bytes are unchanged and its 18-cell UNSUPPORTED ledger is
scoped to v1. What remains is the governed edit of both tombstones (the same
tuple in both files); the exact diff is prepared as `ADMISSION_PATCH.diff` in
the admission worktree. No driver may make that edit.

## First real attempt, in order

```sh
cd <runtime worktree>; export PYTHONPATH=$PWD/src
D=modules/otel-demo/drivers
bash modules/otel-demo/tools/posture_connection_probe.sh <materialized> <commit> | tee probe.log  # must print PROBE OK
python3.13 $D/campaign_setup.py record-probe --transcript probe.log --materialized-root <materialized>
python3.13 $D/campaign_setup.py propose-campaign                    # prints the sentence
python3.13 $D/campaign_setup.py authorize-campaign --typed '<sentence>'   # human, 168 h (D22)
python3.13 $D/campaign_setup.py auto                                # prepare+install+readiness
python3.13 $D/gate_run.py oneshot                                   # refresh -> dryrun -> launch
nohup bash -c 'while :; do python3.13 '$D'/campaign_status.py || break; sleep 300; done' \
  >> campaign-progress.log 2>&1 &                                   # exit 3 = terminal
```

After an abort: `python3.13 $D/gate_run.py archive-run`, fix, then
`gate_run.py oneshot --reuse-install` (the remote install is one-shot).

## Host preconditions (read-only checks, measured 2026-09-12)

1. **`docker ps -q` must be empty.** `assert_no_active_foreign` refuses *any*
   running container. srv6 currently runs the 7-container `teastore-demo`
   project (ports 8080, 3306 — no overlap with 18080–18084). It must be
   stopped, by its owner, and it is **not** ours to touch.
2. `docker version` = `29.6.1`, `getent group docker` gid = `998`,
   `stig` = uid/gid 1016 and in docker. All three matched today.
3. Ports 18080–18084 free; `/home/stig/observability-placement-candidate-v4-*`
   and `.srv6-runtime.lock` absent; no `otel-candidate-v4-*` systemd unit.
4. Disk: `/` was 89 % used, **66 G free**. Eight local amd64 image builds plus
   18 cells of artefacts is the tightest precondition on this host.
5. Two `monpoly` processes (user `lsakizloglou`) have pinned cores 13 and 22 at
   100 % for ~470 and ~560 days. Host is confounded; within-host deltas only.

## Expected first-failure classes

1. `foreign active containers or Compose projects are present` — precondition 1.
2. `projected frozen source digest differs from GATE-PLAN` — the digest is
   computed by materializing on the **arm64 workstation** and compared on
   **amd64 Debian 11**. This is the one GATE-PLAN field that is a prediction.
3. The amd64 build of the five source-guarded services (never built on srv6).
4. `runtime readiness is not fresh` — 900 s; capture immediately before typing.
5. A readiness seam calibrated on a healthy host: 18 seams, none ever run.
