# Budget and stop rule: placement step (CELF over the frozen v3.1 readouts), 2026-10-10

Committed alone, before any placement is computed. Design `research/protocol/PLACEMENT_V3_DESIGN.md` rev. 2 (9bd881e),
decisions 72-80 (round 21) and 81 (round 22, ablations). Training readouts: `readout-{hotel,otel,teastore}-primary-v3.1/`
(3d6bf3b, 0a8517a, 19bd343). OTel is training (decision 74). Test: campaign C and Online Boutique (decision 82,
`research/traffic-sweep/BUDGET_C.md`).

## Order
1. **Design freeze** (a commit alone): sha256 of `PLACEMENT_V3_DESIGN.md` and of protocol rounds 21-22 as committed.
   No placement number exists before it.
2. **Code** under `research/placement/` (never `src/obsplacement`: a framework commit invalidates GATE-PLANs): lazy
   CELF with the best of unit-cost and cost-benefit greedy and the online bound; costs per decision 73; ledger held fixed
   with decision 72's BC rule; own sensors out (79); per rate (75); a read-only per-episode failed-request schedule
   emitter on the frozen v3.1 loaders (77). Tests on synthetic instances, each rule with a planted defect.
3. **Independent review** of the code (Fable `adversarial-review`), then the code is frozen by digest (a commit alone).
4. **Training placements**: per SUT and rate, the Pareto sweep (76) with 6/h named, comparators (78), the literal-cost and
   BC arms (72, 73), held-out by (harness, block). Each output committed unedited before it is read.
5. **Ablations** (81): modality arms on the same readouts; quiet-time curve readouts (frozen v3.1 on block-selected
   subsets, each a new readout committed unedited), then the same placement.
6. The chosen placements are frozen (a commit alone) **before any campaign C or Online Boutique cell is read**.

## Budget
- Design freeze: 2026-10-10 20:00Z. Code + tests: 2026-10-11 12:00Z. Review + code freeze: 2026-10-11 18:00Z.
- Training placements + ablations + placement freeze: **2026-10-12 06:00Z**.

## Stop rules
1. A step that misses its deadline stops and is reported; no extension without the user.
2. A critical-path defect gets 30 minutes; 3 critical-path defects in the code: stop and ask.
3. A review finding that refutes a claim of the design (not a number) returns to the user before step 4.
4. No placement output is edited after it is generated; a correction is a new output path.
