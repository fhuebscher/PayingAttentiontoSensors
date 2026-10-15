# R4: price check of F's frozen sensors on fresh no-fault time (F's plan, attempt 6): declaration (2026-10-15)

**Status: committed alone, before the launch below, after one same-provider review (13:15-13:30Z: NO-GO on three points B1-B3, each fixed below; launch side confirmed).** Budget amendment 2 (`a0e50a3`). `DECLARATION_F_OTEL.md`
(`8845721`) stays binding for the design. Scope: instance (OTel Demo 1.12.0, fb14srv6, 25 req/s). Post hoc to every placement it checks.
## Shape (the budget's fallback) and why
The preferred all-no-fault variant is not built: F's compiler pins its parameters fail-closed (`ALLOWED_KEPT_FAULTS`, `ALLOWED_NO_FAULT_CELLS_PER_BLOCK =
(2,)`, the descriptor digest per variant), and the block-order and verify logic (`regimes != [NO_FAULT_REGIME] * NO_FAULT_CELLS_PER_BLOCK + off_path + tail`),
the run key's `replicate` (1 or 2), the runtime's stop rule on the first cells and the reader's epoch profile (two no-fault cells per block) all encode
F's mix; changing them, with tests and a review, would not fit the 15:00Z gate. So R4 runs **F's unchanged plan** on F's harness `715d57b` (worktree
`observability-placement-runtime-otel-protocol`, clean) at **attempt 6**: descriptor `6164052d…` (F's), plan
`0c7a9cdb10a62fac64567d54a54a36ab4ab50e5ed7dce074871bc6b711dc8f3c`, 25 cells, F's seed, order and onsets. Its 25 run IDs collide with none of F attempts
1-3 (checked against the executed packages of `f1-fetch`, `f2-fetch2` (13 cells, a subset of attempt 2) and `f3-fetch2`, which the compiled plans reproduce), F attempts 4, 5, 7, or R2's attempts 4 and 5
(`fseed` worktree): attempt 5 would reuse R2-attempt-5's run IDs (25/25), so it is skipped. Run IDs do not depend on the seed, so the binding of a fetched package to this plan rests on the launch log (the package carries no plan digest). Relaunch, if any: attempt 7 (no collision).
**Only its 10 no-fault cells are read**; its 15 fault cells are not read for any purpose. Fault-free time read: 10 cells x 0.05 h = 0.50 h (zero-alarm
95 % upper bound 5.99/h; F's held-out check had 0.20 h, 14.98/h).
## Analysis (declared before launch; `research/placement/test-f-nofault/price_check.py` and `sets.json`, wrapper commit `8fca1da`; tests `tests/test_price_check_nofault.py`, 8 passed, the refit and the absent-stream checks each seen failing with their guard removed)
The fetch is byte-verified (shasum rc 0, every host file OK) before the wrapper reads it. For each set in `sets.json` the frozen v3.3 reader runs on the
set's calibration campaign exactly as `fresh_fa_f.py` does (`--blocks 1 2 3 4 5 --test-blocks 4 5 --split split_f_otel.json --validation <farm of R4's
10 no-fault cells>`); the readout's calibration must be byte-equal to the set's committed training readout (never refitted, else refused). Sets: F's
`kafka.consumer_group.lag` (training price 15.81/h) and `kafka.request.count` (9.99/h; F's @3/T_r set and the ablation's frozen sensor) with F's
calibration; F rerun's `kafka.purgatory.size` (9.99/h) with the rerun's calibration; the ledger's 7 route streams (unpriced, per-rule counts only; the
reader gives no ledger union). `request.count` is priced with F's calibration because R4 runs F's deployment; R4 therefore does not test the ablation's
own price (15.81/h, from a no-lag deployment). **R2's frozen set is not priced** (recorded deviation from the budget's "the R2 set once frozen"): it is a
two-sensor set {lag, `flagd.impression`} and the wrapper prices single sensors; lag is priced above. **Presence check (B3):** a metric sensor with 0 raw
samples (`hand_check.raw_series`, an independent parser of `otelcol.log`) in any of the 10 cells gets `—` on every row, never a count; this is coarse (whole
log, not the reader's window) and does not catch a stream that stops part-way. Rule per sensor (k = its union row): **contradicted** iff the fresh one-sided
95 % lower bound exceeds the training price; **bounded below the price** iff the fresh one-sided 95 % upper bound is below it; else **consistent, not
bounded**. Together the two bounds are a 90 % interval. Not an equivalence test.
**Attempts and partial runs (B2):** the wrapper reads attempt 6, or attempt 7 if the one relaunch is spent (`ATTEMPTS = (6, 7)`; never both, never another).
It refuses unless exactly 10 valid no-fault cells of the read attempt are present. A run that stops after all 10 no-fault cells are valid is read; otherwise
it is a relaunch case (harness or infrastructure only, by 16:00Z); a second stop is recorded in a stop note and R4 has no result.
**Harness tests:** the `715d57b` worktree record is 29 failed / 2441 passed / 145 skipped / 1 collection error, accepted for F because the failures match
its baseline (`DECLARATION_F_OTEL.md:86`); R4 uses the same commit unchanged.
## Predictions (committed here, before launch; informed by F's and the rerun's 0.2 h held-out checks: lag 0 and 0, request.count 2 and 0, purgatory 1; k = the sensor's union row; a `—` row decides its prediction as undecided, not as a hit)
| id | prediction |
|---|---|
| NF-LAG | `consumer_group.lag`: not contradicted; k <= 2 |
| NF-REQ | `request.count`: not contradicted; k >= 1 (it alarmed 2 times in F's 0.2 h) |
| NF-PUR | `purgatory.size`: not contradicted; k <= 3 |
| NF-ANY | at least one of the three (lag, request.count, purgatory) is "bounded below the price" (k = 0 gives 5.99/h < 9.99/h) |
| NF-LED | ledger: at least one rule on at least one route stream has k >= 2 (per-rule rows; informed by the wrapper's dry run on R2's 10 no-fault cells, where checkout run3 and recommendations median reached 6) |
## Host preparation and DRY_RUN (2026-10-15)
R2's fetch `tmp/otel-f-evidence/fs1-fetch2` verified 437/437 (shasum rc 0); the first DRY_RUN `nfdry` (13:12:28Z) stopped on 3 guarded one-shot paths;
the host's execution package carries the same 25 run IDs as `fs1-fetch2` (sha256 of the sorted list `b3206544…` on both, attempt 4); the paths were then
moved, not deleted, into `archive-f-attempt4-20261015/` (stig, mode 700; the exact `mv` commands were not retained, only this description): `otel-offpath-f-v1` and `.setup-otel-offpath-f-v1` from the runs root (4.6 GB),
`otel-offpath-f-v1-f08ba1d5313b` from the release root (72 MB). DRY_RUN `nfdry2` passed 13:13:44Z (all guards; srv6 0 units, 0 containers, no lease
holders, 211 GB free, 0 F paths).
## Launch (after the review GO; srv6 idle by the host)
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=6 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_offpath_f.py EXPECTED_PLAN=0c7a9cdb10a62fac64567d54a54a36ab4ab50e5ed7dce074871bc6b711dc8f3c \
  RUN_COUNT=25 CAMPAIGN=otel-offpath-f-v1 LOG_PREFIX=otel-offpath-f-v1 \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh nf1 715d57b5f06ea32d47466acccae927da8e350a2c > scratchpad/gate-drivers/otel-offpath-f-v1-nf1.out 2>&1 &
```
Logged with `uv run python tools/wandb_campaign.py follow nf1 scratchpad/gate-drivers/otel-offpath-f-v1-nf1-launch.log`. Fetch case `otelNF1` -> `tmp/otel-f-evidence/nf1-fetch` (added to `fetch_overnight.sh` only
when no fetch is running). At most 1 relaunch (attempt 7), harness or infrastructure only, starting by 16:00Z.
