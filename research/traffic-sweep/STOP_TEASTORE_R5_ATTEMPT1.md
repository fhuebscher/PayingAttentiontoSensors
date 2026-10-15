# R5 stop note: first launch stopped at cell 5 (2026-10-15 14:53Z), committed alone before the relaunch

Declaration `DECLARATION_TEASTORE_R5.md` (`c61cde6`), budget `BUDGET_OVERNIGHT_20261015.md` (`bfc9417`). Stopped attempt: setup ID
`b4bdd8e0df7bfc1eb7562462df181b64` (GATE-RUN release line of `scratchpad/gate-drivers/teastore-r5-launch.log`), harness `04254228`, plan `5a8e385e…`,
launched 14:24:40Z (unit `teastore-candidate-v4-4956c25a1e1ca6ce62bd287d810bc9bb`).

- Host record (srv5, read 14:58Z): `teastore-offpath-v1/campaign-abort.json`: stage `cell-execution`, `validCells` 4, `journalRows` 5, `retryAllowed` false,
  recorded 14:53:31Z. The fifth cell, `teastore-offpath-v1/auth-freeze-effect/r10/b01/full/a01`, is preserved as blocked evidence
  (`b01-05-full.blocked-evidence/blocked-evidence-manifest.json`: `RuntimeError: TeaStore readiness failed`); controller log: `ControllerError: candidate cell
  executor failed: RuntimeError: TeaStore readiness failed`. systemd: exit status 2.
- **Classification:** infrastructure (the SUT did not reach readiness at a cell start); the cause is not established. No cell content was read: only the abort
  record, the blocked manifest's error fields and the controller log's last line.
- **Relaunch (the budget's one, within 1 h of the stop; declaration: by 17:00Z):** same harness `04254228`, same plan, label `r5r1`, after DRY_RUN `r5r1dry`. The
  stopped attempt's 4 valid cells and its blocked cell stay on the host and are never read. The fetch reads only the relaunch's setup ID (from the GATE-RUN line of
  `teastore-r5r1-launch.log`); `fetch_r5.sh` gains `b4bdd8e0df7bfc1eb7562462df181b64` in its refuse list and reads the relaunch log, in a commit before the fetch.
  A second stop ends R5 with a stop note.
