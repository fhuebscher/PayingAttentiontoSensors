# Budget and stop rule: analysis v3.2 and campaign D (fresh placement test), 2026-10-12

Committed alone, before any v3.2 or campaign D work. Authority: user, 2026-10-12 ("v3.2 + fresh campaign D"), after
campaign C's decision 89 verdict FAIL (`research/placement/test-c/RESULT_C.md`, c4418dd). C's FAIL stays reported as
the preregistered result; nothing below re-scores or relabels it. Scope of every number: instance.

## Sequence and deadlines (UTC)
1. **Diagnosis** of C's missing OTel throttle fires, exploratory, on retained B/C/training evidence only:
   **2026-10-12 12:00Z**.
2. **v3.2**: every change proposed as a hyperparameter-group decision for the user (with the v2 -> v3 deviation record,
   `research/protocol/DEVIATIONS_V2_TO_V3.md`), synthetic tests with a planted defect per change, independent review,
   digest freeze. Whether C's cells enter v3.2's training is decided with v3.2. Frozen by **2026-10-13 06:00Z**.
3. **Placements re-solved** under v3.2 on the declared training set only, frozen with D's pass rule (committed before D
   launches): **2026-10-13 09:00Z**.
4. **Campaign D**: C's shape (3 blocks x 3 regimes x 4 rates), a new study epoch, new seed, new blocks and run IDs.
   OTel on fb14srv6 is required (the only system with a declared verdict); TeaStore on fb14srv5 optional. Harness ready
   and DRY_RUN passed: **2026-10-13 12:00Z**. Terminal and fetched: **2026-10-14 06:00Z**. At most 1 relaunch per system.
5. **Scoring**: frozen scorer (re-pinned only for v3.2's digests), readouts and scores committed unedited before reading;
   result reviewed by **2026-10-14 18:00Z** to enter the ASOCA paper (deadline 2026-10-15).

## Stop rules
1. v3.2 not frozen by 2026-10-13 12:00Z: D is not launched; the paper reports C's FAIL and v3.2 as future work.
2. A missed deadline stops that step; the reason is recorded and the user is asked. No extension without the user.
3. A critical-path defect gets 30 minutes; 3 critical-path harness defects in one system stop that system.
4. Launch only from a declaration committed alone plus a passing DRY_RUN on the host, mirrored to wandb; one campaign
   per host.
5. No D cell is read (validity fields only) before v3.2, the placements and D's pass rule are frozen.
6. The frozen reader must admit D's epoch before launch (the decision-92 failure is not repeated): a synthetic D-epoch
   cell is driven through `find_and_load3` in the v3.2 tests.

## Amendment 1 (user, 2026-10-12, committed alone before the pilot work)
Diagnosis (`aa461f8`): OTel's 0.1-core productcatalog throttle never took effect at 0.05-10 req/s (about 1.07 ms CPU per
request, so on average it starts to bind near 93 req/s). The user chose **higher traffic** (no new fault code) and a
**load pilot at 100 and 200 req/s** first.
- **Pilot** (OTel, fb14srv6): new epoch, the same throttle, rates 100 and 200 req/s, fault cells plus one no-fault cell per
  rate; a manifestation criterion declared before launch. Harness ready and DRY_RUN passed: **2026-10-12 18:00Z**;
  terminal and fetched: **2026-10-12 22:00Z**. At most 1 relaunch. If no rate shows the declared effect, D is not
  launched and the paper reports C's FAIL with the diagnosis.
- **D's shape changes** from step 4 above: rates chosen from the pilot (r10 kept as an anchor), and **training blocks and
  test blocks in one declaration**, the split fixed before launch; the placement is solved on the training blocks,
  frozen with the pass rule, then scored once on the test blocks. No frozen placement exists at a new rate, so this
  replaces "placements re-solved on the declared training set" (step 3) for the new rates. Steps 2 and 4-5 keep their
  deadlines.
