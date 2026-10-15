# OTel campaign F, no-lag ablation (`otel-offpath-f-nolag-v1`): declaration (2026-10-15)

**Status: committed alone, before the launch below.** Budget `BUDGET_OVERNIGHT_20261014.md` (`cf50078`, item 2). Predictions committed before launch:
`research/protocol/PREDICTIONS_OVERNIGHT_20261014.md` (`8b89d43`, ids FNL-*). Analysis frozen before launch: `research/protocol/FREEZE_V35_20261015.md`
(`0be6dc2`; reader v3.5 = v3.3 plus admission of this epoch with F's profile byte for byte) and `research/placement/test-f-nolag/RUN_ORDER.md` (`a6b9cc8`).
Scope: instance (fb14srv6).
## What it is
F's design (`DECLARATION_F_OTEL.md`, `8845721`) with exactly one change: the collector's `kafkametrics` receiver, its `resource/kafka` processor, its
`metrics/kafka` pipeline and otelcol's `depends_on kafka` are **not rendered**. Kept: 5 s SDK metric export, spanmetrics flush 5 s, 2 no-fault cells per
block, 25 cells at 25 req/s, regimes, split 1-3 / 4-5, sizing. Harness: the separate worktree `observability-placement-runtime-otel-ablation`, branch
`otel-ablation-20261014`, from F's `715d57b`; commits `9339eed`, `d908129`, `884ed17`, `3716a05`, activation `4ab4433` (= the launch commit). Descriptor
`a65f4e33…`, plan (attempt 1) `858bbcd3634a48c30af55546308d181ebed6daf9af29161f1b5cf760e263026e`. The rendered collector config validates with the official
0.108.1 build (with no `kafka` string in it); F's and E's materialised trees are byte-identical between the two worktrees; nolag differs from F by exactly
the four pieces. Seed 20261015 (F: 20261014), so block orders and onset strata are new draws of the same rules: an F-vs-ablation difference mixes the
receiver with the draw (stated).
## Question and rule
Does F's pass hold without the lag receiver? The pass rule is F's (`V32_PASS_RULE`, frontier any/any @6/T_r, per off-path class, strict improvement on >= 2 of
2 test episodes), scored by `score_nolag.py` with a recorded separate pin; decision 73 unchanged. Predictions FNL-* (8b89d43) expect a non-lag Kafka broker
metric (`kafka.request.count`) in the set and both classes to pass, and flag that its fresh false alarms may exceed its training price (F: 2 in 0.2 h).
If the training readout shows a `kafka.consumer_group.lag*` sensor (`v35.ablationHolds` false), the analysis stops and is reported (RUN_ORDER).
## Launch (after a passing DRY_RUN; F's replication must be terminal; one campaign per host)
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
LAUNCH_APPROVED=1 OTEL_WORKTREE=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-otel-ablation \
  COMPILER=candidate_offpath_f_nolag.py EXPECTED_PLAN=858bbcd3634a48c30af55546308d181ebed6daf9af29161f1b5cf760e263026e \
  RUN_COUNT=25 CAMPAIGN=otel-offpath-f-nolag-v1 LOG_PREFIX=otel-offpath-f-nolag \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh nl1 4ab4433352e17818d19851434b8ffe73a1b26700 > scratchpad/gate-drivers/otel-offpath-f-nolag-nl1.out 2>&1 &
```
DRY_RUN `nl1dry` passed 2026-10-15 01:53:11Z (all guards; srv6 0 units, 0 containers, 221 GB free, 0 ablation paths).
At most 1 relaunch, harness or infrastructure defects only. Fetch case `otelNL1` (`tmp/otel-f-evidence/nolag1-fetch`).
