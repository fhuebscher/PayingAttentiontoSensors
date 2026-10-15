# TeaStore traffic sweep, relaunch 1: stop record (2026-10-03)

Campaign `teastore-traffic-sweep-v1`, relaunch 1 of 2 (`AMENDMENT_TEASTORE_1.md`), harness `e6d6600`, plan `c7df47ab…`,
setup `31fa62489708392dfbfae6a1304a88a6`, fb14srv5, 13:52-14:58Z. Scope: instance.

## What happened
- `campaign-abort.json` (recorded 14:54:25Z): `ABSTAINED`, `validCells: 10`, `journalRows: 11`, error
  `ControllerError: candidate cell executor failed: WitnessError: persistence log contains secret-bearing raw text`.
- The blocked cell is cell 11, `persistence-cpu-throttle-effect` at 10/s. Cell 12 did not run. Cells 1-10 sealed valid.
- It is the same cell that stopped attempt 1, but the cause is different. Attempt 1's cause was trace completeness, now
  handled by decision 25.

## Diagnosis (read-only on srv5, ~15 min; counts only, no log text printed)
The harness's own scanner (`modules/teastore/validation/secret_scan.py`) was run line by line on cell 11's
`b01-11-full.blocked-evidence/persistence.log`. The script is in the session scratchpad, `teastore-r1/scan_remote*.py`.

| file | lines | JVM stack-frame lines | lines flagged | flagged lines that are not frames | whole file flagged | whole file flagged, frames removed |
|---|---|---|---|---|---|---|
| relaunch 1, cell 11 | 4,500 | 1,344 | 112 | 0 | yes | no |
| attempt 1, cell 11 (`.operational/persistence.log`) | 3,257 | 0 | — | — | no | no |
| relaunch 1, cells 9 and 10 (throttle at other rates) | 38 / 9 | — | 0 / 0 | — | no / no | — |

- **The flagged lines.** All 112 are frames of the shape `at org.eclipse.persistence.internal.sessions.<Class>.<method>(<File>.java:<n>)`.
- **Why the scanner fires.** Its unquoted key-assignment rule reads the text up to the `:` as a key. The normalized key
  embeds `session`, which is one of the embedded secret names.
- **Where the frames come from.** They belong to `org.eclipse.persistence.exceptions.ConcurrencyException` (48) and
  `jakarta.persistence.PersistenceException` (16), thrown under the 0.1-CPU throttle at 10/s. That makes them a fault
  effect.
- **They are nondeterministic.** Attempt 1's cell 11 had the same plan and onsets and contains no frames.

**Conclusion.** This is a false positive of the privacy gate on Java stack traces. It is not a secret, the fault, or the
design.

## Budget
- This is TeaStore's **2nd critical-path harness defect** under `BUDGET_REPLICATION.md` (stop rule: 3). The 1st was
  attempt 1's all-or-nothing completeness rule.
- One relaunch is left.
- The 10 valid cells are not pooled with a relaunch; they stay as evidence of the stop.

## Next
- A fix is being built and will not be launched: the scanner treats a JVM source location `(<File>.java:<digits>)` as not
  an assignment, and everything else stays fail-closed.
- It comes with tests, an offline replay of cell 11, a re-pin, a DRY_RUN and `AMENDMENT_TEASTORE_2_DRAFT.md`.
- **Relaunch 2 waits for the user.** The fix narrows a privacy gate, so it changes what the harness may retain (stack
  traces in retained logs). Under `CLAUDE.md` that makes it a preregistration decision, not an engineering default.
- Evidence fetched read-only to `tmp/teastore-sweep-evidence/` (relaunch 1, new path; attempt 1's archive untouched).
