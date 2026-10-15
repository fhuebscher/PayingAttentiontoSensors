# Why OTel C has no throttle fires at r0.2 (exploratory, 2026-10-12; under no protocol decision)

Method: a general-purpose subagent recomputed the v3.1 median rule with the script's own functions over all 35 r0.2
cells, read-only; the B fire instants reproduce (5.82 / 10.24 / 8.68 s). Not an independent review. The CPU figure below
was re-checked by the coordinator (`resources.json`, C r0p2-b01: 388,306,000 -> 489,021,000 ns).

## Findings (instance: OTel on fb14srv6, r0.2)
1. **The throttle does not bind.** productcatalogservice uses 0.094-0.107 CPU-s per cell (~185 s) in all 7 r0.2 throttle
   cells (sweep, B, C): about 0.5 % of the 0.1-core cap. Its GetProduct server spans post-onset have median 0.14-0.15 ms
   vs 0.13-0.16 ms pre-onset; the frontend->productcatalog gRPC client span is unchanged (2.6-3.1 ms). The throttle was
   applied to the right container (read back at 1e8 nanoCPUs, restored to 24e9) and `manifested` is true, but the
   recorded effect on the target is nil. No CFS throttling counters were retained.
2. **B's three "detections" are within noise.** The median rule restarts at onset and needs 3 samples; a periodic
   untokened `GET /` (every 60 s, at 10.5 / 70.4 / 130.4 s from the barrier, 34-74 ms) is always the 2nd or 3rd sample
   after onset, so the median is the larger of the first one or two API samples. Against the training threshold
   9.528 ms: B 9.73 / 15.99 / 9.79 ms (+0.21 / +6.46 / +0.26), C 8.92 / 5.71 / 7.77 ms. The same statistic on the 21 r0.2
   no-fault cells at a pseudo onset (62 s) exceeds the threshold in 2/21 (0-2/21 for pseudo onsets 58-120 s). B's fire
   times are the arrival times of `GET /`.
3. Timing, load and harness do not separate B from C: onsets 60-65 s, hold 60.04-60.06 s, 36/36 requests ok on one
   route in every cell; `git diff c4aa313 8018a19` touches only epoch admission and bookkeeping. 8 locally built images
   have different IDs between B and C (no build provenance retained).

## Consequence
The training gain at OTel r0.2 (19.4 s held-out) rests on three marginal median exceedances in a cell where the fault
has no measured effect on its target. C's FAIL is consistent with there being nothing to detect. An analysis
subversion cannot make a non-binding fault detectable; the fault design (throttle depth relative to the target's CPU
demand at each rate) is the open question, and that is a preregistration decision.

## Open
- What sends the 60 s `GET /` (likely a healthcheck; unchecked).
- `span:frontend:GET/run3` at r0.2 has K 4 in the training readout and K 3.5 in the C readout with the same 21
  calibration cells and script hash; not investigated (does not affect the median fire).
- Whether TeaStore's persistence throttle binds at low rates (its C gain at r0.2 is one throttle episode) is unchecked.
