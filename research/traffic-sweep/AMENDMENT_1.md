# Traffic-sweep pilot, amendment 1 (2026-10-03, committed alone, before the relaunch)

Amends `research/traffic-sweep/DECLARATION.md` (a795fc9). Design, descriptor (`788ff28c…`) and plan (`766063c5…`) are
**unchanged**; only the harness commit the declaration binds changes.

## What happened
- Attempt 1 (04:54Z): failed in setup before any cell (uninitialised `upstream/deathstarbench` submodule in the
  worktree); fixed by initialising it. Nothing ran.
- Attempt 2 (`hotel-v1-20261003t050738z-29661565`, 05:08-06:56Z): **25 of 64 cells sealed, 25 valid**. Cell 26
  (`cpu-throttle-effect-r10-b02-full-a01`) raised `'utf-8' codec can't decode byte 0xbf` while capturing
  `docker compose logs`; the controller aborted the campaign (`ABSTAINED`, `retryAllowed: false`).
  Cause: the cell runner decoded container logs as strict UTF-8; a single non-UTF-8 byte in a container's output killed
  the cell. Same class as TeaStore's review finding (worktree 9181964). Not caused by the fault or the design.

## Amendment
- Harness binding: `9ed8863` → **`7a1d97b`** (application.log kept as raw bytes; parsed with U+FFFD replacement by the
  emission and witness parsers and the terminal validator). Regression test fails on `9ed8863`'s modules.
- The relaunch runs **all 64 cells** (relaunch 2 of 2 under `BUDGET.md` rule 4; attempt 1 counted as relaunch 1).
- Attempt 2's 25 valid cells are archived (`tmp/hotel6-evidence/hotel-v1-20261003t050738z-29661565.tgz`) and **not
  pooled** with the relaunch. They are kept as a same-plan repeat of the relaunch's first 25 cells (same run IDs, same
  seeded onsets), usable later as a test-retest check; any such use is exploratory.
- Analysis stays blind: no detection result of attempt 2 has been looked at.
