# Freeze record: decision 92 (2026-10-12, before any campaign C result is read)

Amendment `fdbdb16`; C readouts `720957c` (committed unedited). Review: Fable adversarial-review subagent, same-provider
(the cross-provider judge server fails to connect). Verdict: nothing blocking; two should-fix items, both handled here.

## S1: parameters digest
- `research/protocol/parameters_v3.json` was `f6257b78fedfdcab9577f37cdba77a6fc6d785e4b0b34641cb18de6bb21ade9a` (v3.1 freeze
  record `990d501`). It is now `212830bec3e6669bc211d5cffa48d61fa3bf0f6d4dd5ceaf79d3e2bcc7c4d000`: f6257b78 plus decision 92's
  `STUDY_EPOCHS_B` hunk only (reviewer checked the diff).
- Checked before scoring (input fields only, no outcome read): both C readouts carry `parametersV3Sha256 = 212830be…`;
  their `parametersV3` dump differs from the training readout's only in `STUDY_EPOCHS_B`; `scriptSha256` and `v24Sha256`
  equal the training readout's. C's position: OTel campaign index 4 (`tmp/c-fault-copy/otel`), TeaStore index 5
  (`tmp/c-fault-copy/teastore`).
- The frozen scorer does not check this digest; this record is the check.

## S2: sections of the C readouts that must not be quoted
Pooling C as an extra campaign gives 7 episodes per (fault, rate) against `EPISODES` = 4, so P2/P3/P4 render `—` with
a wrong "(n < 4)" reason; `harness_breakdown` counts B and C together under "B" (B = harness shape); the readout's
"exploratory, not frozen" label is wrong. None of these feed the scorer. C-only H4 counts come from the `freezeStamps`
block keyed by campaign root. Do not run celf_v3's held-out folds on a C readout (FOLD_KEY merges B and C blocks, N1).

## Corrections and limitations
- N2: decision 92 cites `DECLARATION_C_OTEL.md:159` as evidence that no declaration named the reader change; that line is
  about host move-aside of B's paths. The claim holds by absence (no mention of `STUDY_EPOCHS_B` or the reader in either
  C declaration, `BUDGET_C.md`, or the scoring draft); the citation is wrong.
- N3: no test drives a C-epoch cell through `find_and_load3`; the reviewer checked `harness_of`/`admit_b_epochs` in memory.
- N5 (decision 88, declared): C's fault cells contribute pre-onset segments to the pooled fit, so the detectors that score
  C are partly fitted on C's pre-onset data. A limitation to state with the result.
