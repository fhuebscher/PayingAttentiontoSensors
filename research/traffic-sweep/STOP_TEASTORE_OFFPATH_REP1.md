# TeaStore off-path replication 1: stopped by its budget (2026-10-14)

Budget `BUDGET_REPLICATION_20261014.md` (`0b70303`): at most 1 relaunch; declarations `256ae13` and `3760a6c`. Scope: instance (fb14srv5).
- Replication 1 (setup `887a7838…`, launched 06:54:22Z) stopped at cell 9 (`recommender-pause-effect/r10/b02`), 08:15Z, 8 valid; fetched
  `tmp/teastore-offpath-evidence/rep1-fetch`, 298/298 byte-verified.
- Relaunch 1 (setup `d61bfea7…`, launched 08:21:17Z) stopped at cell 18 (`recommender-pause-effect/r10/b03`), 10:20:37Z, 17 valid; fetched
  `tmp/teastore-offpath-evidence/rep1r1-fetch`, 496/496 byte-verified.
- Both: `RuntimeError: candidate queue was non-empty at the measurement barrier` (the Kieker queue held 1 message with 1 consumer at the barrier in the
  first stop's `queue-proof.json`). With TeaStore #19 (auth-freeze b01) this class has now occurred 3 times; both recent stops were recommender-pause
  cells at 10 req/s (relaunch 1 of the main off-path run had 30/30 valid with the same plan). No mechanism is claimed; ledger row.
- **Outcome (as declared):** no further relaunch; TeaStore keeps relaunch 1's result (`RESULT_TS_OFFPATH.md`) without replication. The 25 valid cells of
  the two stopped attempts are preserved and flagged, and are not read.
