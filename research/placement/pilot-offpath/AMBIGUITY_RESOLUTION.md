# Off-path pilot criteria: how ambiguities are resolved (2026-10-12, before any pilot cell is read)

The criteria script `research/placement/manifestation_offpath_pilot.py` (`ef94c6d`) listed 11 places where the frozen
declaration (`64854c2`) is ambiguous. Rule (coordinator, engineering default): where the declaration's text is silent or
ambiguous, the harness reference functions it names as the computation of the criteria (`statistics_of`, `verdict` in
`tests/test_otel_offpath_pilot.py` at harness `8c53cb2`) decide, because they were fixed with the declaration before launch.
The script mirrors them and a test requires identical statistics and verdicts on 16 synthetic campaigns. Specifically:
1. Frontend-pause window = hold minus the request timeout (45 s; the script refuses a plan whose timeout is not 15 s).
2. A zero pre-onset median gives `—`.
3. The 20-item minimum applies wherever the reference applies it (fault and no-fault pre-onset consumer counts, hold
   checkout rows, frontend-pause rows and sent checkouts, S2 rows).
4. The S2 no-fault precondition gates every fault at that rate (60 s pseudo hold by scheduled time); the frontend-pause
   no-fault comparison uses the 45 s window.
5. E-rate rule: a `—` counts as not manifesting; the frontend-pause control counts as a kept fault if it manifests;
   BUDGET_E stop rule 5 (no off-path fault manifests -> no E) is applied by the coordinator from the per-fault result.
6. Under `--terminal-valid` a cell counts if its receipt is `valid` and the offline terminal replay passed for the campaign.
7. Invalid or blocked cells are not read (no statistics, no N3).
8. N3 (reported, not part of any verdict): ledger status vs witness `response_code`; a timeout (status None) disagrees.
9. An unparsable span timestamp aborts the run (no silent skip).
10. Rate and fault identity come from the compiled plan (`timing.requestsPerSecond`, `fault.scenario`).
11. Span `Start time` fraction width varies (0-9 digits, trailing zeros trimmed); not a criterion.
