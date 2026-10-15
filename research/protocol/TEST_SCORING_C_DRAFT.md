# Campaign C test scoring: draft (2026-10-11, not adopted)

Written after the placements were frozen (378e598) and before any campaign C cell is read (BUDGET_C rule 4). Decision 82:
C's fault cells are scored only by the frozen placement. Neither the design nor a decision says how, or what counts as
the placement passing, so this needs the user's approval before C is read. Scope: instance (TeaStore on srv5, OTel on
srv6). Hotel and Online Boutique are not in C.

## Procedure (engineering; reuses frozen code only, plus one small scorer reviewed and frozen before C is read)
1. **Detectors on C:** frozen v3.1 on each SUT's training campaigns (as in its primary readout) **plus a fault-only view
   of C** (its no-fault cells removed), `--validation` = C's full campaign, so C's no-fault cells are the second fresh
   false-alarm check and never enter a fit. C's fault cells contribute their pre-onset segments to the pooled fit, as
   every scored episode does under H1 (the detector's definition). A new readout, committed unedited before reading.
2. **Scorer** `research/placement/score_test_v3.py`: imports the frozen `celf_v3` objective (same BC, own and miss rules,
   decisions 72, 79, 84) and computes, per rate and on **C's episodes only**, the mean penalised time to detection D of
   each frozen set (primary arm at 0, 3/T_r, 6/h and unlimited; the declared comparators; the modality-arm sets), with
   per-episode values. Synthetic tests with a planted defect, independent review, digest freeze, then the run.
3. **Fresh false alarms of the frozen sets on C's no-fault cells:** the frozen v3.1 validation accepts only P4-shaped
   sets; the scorer reports `—` unless a validated path exists (stated, not hidden).

## The test quantity and the predictions (frozen from the training held-out results, 378e598)
Test quantity per (SUT, rate): g_C = D_C(ledger alone) - D_C(S_6/h), seconds, over C's episodes (6 per rate: 3 blocks x
2 fault classes), with per-episode differences. Training held-out gain at 6/h (fold mean), the prediction:
| SUT | r10 | r1 | r0.2 | r0.05 |
|---|---|---|---|---|
| OTel | 0.0 (set: frontend GetProduct span) | 0.0 (frontendproxy log) | **19.4** (span:frontend:GET) | 0.6 (frontendproxy log) |
| TeaStore | 0.0 | 0.0 | 0.0 | 0.0 |
So the one non-trivial prediction is **OTel at r0.2**: the frozen 6/h set improves on the ledger through the CPU-throttle
class (training: the set detects 7 of 8 episodes vs the ledger's 4; the ledger misses all 4 throttle episodes, the set
catches 3; held-out gain 25-27 s in each B fold, 0 in the sweep fold, whose harness differs). Everything else predicts no gain, which a test can contradict only by a large g_C.

## Decision for the user: what counts as passing
- (a) **Sign rule (recommended):** at OTel r0.2, g_C > 0 with the frozen set improving at least 2 of C's 3 throttle
  episodes; elsewhere report g_C and per-episode values, no verdict.
- (b) Magnitude rule: g_C within the training held-out range (fold minimum to maximum) at every (SUT, rate).
- (c) Descriptive only: report g_C everywhere, no verdict (n = 3 episodes per class and rate).
