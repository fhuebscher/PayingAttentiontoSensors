# Cross-provider review of the BenchSOC draft (2026-10-15, append-only)

Reviewer: `llm_as_judge` CLI, single judge `gpt-6.1-sol` (panel_n 1), on the text extracted from `papers/current/benchsoc/paper.pdf` at `3b79c11`.
Requests and responses kept in the session scratchpad; evaluation ids below are in the judge's history (project path = this repo).

| eval id | check | result | action |
|---|---|---|---|
| `eval_fcbd250b…` | full paper, 7 criteria | 5/7; failed: artifact not available; 60 s vs 60.06 s miss charge | hold wording fixed (60 s nominal, measured hold ~60.06 s); artifact open (author) |
| `eval_be82c43e…` | adversarial: coordinator timing | survives | none |
| `eval_a81a7d33…` | adversarial: TeaStore replication 2 | survives | none |
| `eval_e5b3c8f2…` | adversarial: F pass held on rerun "same seed and onsets" | refuted (evidence not supplied) | checked: identical, `test-f-rep1/onsets_f1_vs_f3.json`; cited in the paper |
| `eval_0658bdba…` | adversarial: E FAIL cause with zero-alarm counterfactual 2/2 vs 0/2 | refuted | the paper makes no counterfactual count claim; none added |
| `eval_08103423…` | adversarial: own lane falls with rate, Spearman rho across systems | refuted | the paper states only the Hotel median example; no rho claim added |
| `eval_845c2629…` | triage of remaining weaknesses and the last run | 3/6; missing: full-posture-only scoring, sibling calibration, 0.2 h fresh false-alarm time (all disclosed in threats/sections, not in the triage); artifact first | reported to the author |
| `eval_c64868fa…` | adversarial: "R1 (TeaStore off-path placement test) is the best use of the last run" | refuted: defensible, not shown best; artifact first; R4 credible | decision left to the author |
| `eval_b10c8b2b…` | adversarial, panel_n 3: abstract, R1/R2 paragraphs and threats at `5ba2e45` vs RESULT notes R1-R3 (13:55Z) | refuted 2/2 (gpt-6.1-sol, correctness and reproducibility lenses; the third member, Claude Haiku on Bedrock, failed 403, so the panel was single-provider); supported: R1 rate split, R2 two-member set and 1 alarm, R3 FAIL | review bullet "every result note reviewed" false while R2's review was pending (to be restated when it lands); abstract "no placement improved on the request path" narrowed to "where scored"; "freezes the analysis before any test data is read" restated as "commits the analysis before any test readout is produced" (readout frameworkCommit after the pin); E/F claims were outside the supplied notes (sourced in RESULT_E/RESULT_F) |
| `eval_5e4bf61b…` | adversarial, panel_n 3: abstract, OTel (R2, R6) and TeaStore (R1, R5) paragraphs, threats at `7b328b8` vs RESULT notes R1-R6 (~20:40Z) | refuted 2/2 (gpt-6.1-sol, correctness and reproducibility lenses; Claude Haiku on Bedrock failed 403, so single-provider again); instance counts confirmed | auth-span price in the R5 sentence corrected to 1,336.66/h at 10 req/s (324.50/h was its 1 req/s price); abstract "where the baseline was blind" -> "where the baseline missed most test episodes" (F's ledger caught 1 of 4); E/F comparison sourced in RESULT_E/RESULT_F, outside the supplied notes, kept |
