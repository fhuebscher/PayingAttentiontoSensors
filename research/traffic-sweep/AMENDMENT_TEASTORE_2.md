# TeaStore traffic-sweep initial test, amendment 2 (FROZEN 2026-10-04, committed alone before relaunch 2)

Approved by the user on 2026-10-04 as decision j (`research/PROTOCOL_DRAFT_20261002.md` round 9, item 42): the narrowed
JVM-frame scanner at `0588a41` and relaunch 2 of all 12 cells. Relaunch 1's 10 valid cells are not pooled.

Amends `research/traffic-sweep/DECLARATION_TEASTORE.md` (c9f072b) after `AMENDMENT_TEASTORE_1.md` (bbbd80b). It proposes
a harness fix for the defect that stopped relaunch 1, and relaunch 2 of all 12 cells. Under `BUDGET_REPLICATION.md`
this is **relaunch 2 of 2**, and the defect is TeaStore's **2nd critical-path harness defect** (rule 2: stop and ask
at 3). The budget's launch-ready deadline is 2026-10-04 12:00Z. This draft is ready at 2026-10-03 ~15:50Z. Scope of
every number: **instance**.

## What happened
- Relaunch 1 ran on fb14srv5 at harness `e6d6600`, plan `c7df47ab…`, setup `31fa62489708392dfbfae6a1304a88a6`, results
  root `…/candidate-v4/teastore/results/31fa62489708392dfbfae6a1304a88a6/teastore-traffic-sweep-v1`. It started at
  13:52Z and aborted at 14:54Z. **11 cells were attempted and 10 were valid.** Cell 11
  (`persistence-cpu-throttle-effect/r10/b01/full/a01`) was blocked by the cell executor with
  `WitnessError: persistence log contains secret-bearing raw text`
  (`modules/teastore/witness/extract_app_witness.py:227`, scanner `modules/teastore/validation/secret_scan.py`). The
  controller wrote `campaign-abort.json` (`ABSTAINED`, `validCells: 10`), and cell 12 did not run. The producer's own
  canonicality blockers for cell 11 were empty, so decision 25 had held.
- Diagnosis, counts only, from the retained `b01-11-full.blocked-evidence` on a byte-identical copy (see Replay). No log
  line was printed or copied.
  - `persistence.log` has 4,500 lines, of which 1,344 are JVM stack-frame lines. **112 lines are flagged, and all 112
    are frames.** Every flag comes from `UNQUOTED_KEY_ASSIGNMENT`. That rule reads `<class>.<method>(<File>.java` as a
    key and the `:` before the line number as an assignment.
  - There are 4 distinct normalized keys, and each embeds `session` from the package `…internal.sessions`. Keys and
    counts:
    - `orgeclipsepersistenceinternalsessionsabstractsessionexecutequeryabstractsessionjava` ×48;
    - `…identitymapaccessoracquirelockidentitymapaccessorjava` ×32;
    - `…abstractsessionretrievecachekeyabstractsessionjava` ×16;
    - `…unitofworkimplinternalexecutequeryunitofworkimpljava` ×16.
  - The scanner returns False on the same file with the frame lines removed.
  - In the same cell, `auth.log` has 88,320 lines, of which 81,176 are frames, and 0 are flagged (no secret name in
    those packages).
  - Attempt 1's cell 11 (same plan and onsets) had 3,257 persistence lines and **0** frames. The exceptions under the
    0.1-CPU throttle at 10/s are therefore not deterministic.
- This is a false positive of the fail-closed privacy gate on a JVM source location. It is not a disclosed field, and
  it is not a fault or design problem.

## Fix (harness `0588a41` = `1a3ca07` + review fixes; worktree `observability-placement-runtime-teastore-protocol`)
- **Rule** (`secret_scan.py:35-53`, `_is_jvm_source_location` `:78`, applied at `:104-107`). With
  `jvm_source_locations=True`, the scanner skips one unquoted-assignment match only when **all** of the following
  hold:
  - the key is at most 256 characters. An overlong key blocks *before* the frame test, as it always did;
  - the matched text is the key immediately followed by `:` (no whitespace, never `=`);
  - the key is `<text>(<file>.java|kt|scala|groovy`, with exactly one `(` (`JVM_SOURCE_KEY`);
  - the text right after the `:` is ASCII digits, then `)`, then whitespace or the end of the text
    (`JVM_SOURCE_LINE = [0-9]+\)(?=\s|\Z)`).

  The scan then continues past the skipped match, so every other assignment on the same line, or on any later line,
  still blocks. The bearer rule and the quoted-key path are unchanged. The switch is threaded through
  `_secret_in_layer` and `_walk_json` and must be a `bool`.
- **Ceiling**, recorded in the comment at `:48-51`. The rule accepts a digits-only value after a `(<File>.java:` key,
  closed by `)` and whitespace. A JVM frame cannot carry a secret there, because the JVM prints the class file's line
  number. Application text that writes a digits-only secret into exactly that shape (for example
  `password(x.java:1234)`) would not be flagged. A test pins this ceiling.

  A frame *inside* a JSON string is followed by a quote or an escape at the raw layer, so it still blocks. That is
  fail-closed, and TeaStore's witness logs are plain text.
- **Callers**. All of them load the same file, `modules/teastore/validation/secret_scan.py`, by path:
  - `extract_app_witness.py:227` passes `jvm_source_locations=SWEEP_EPOCH_ACTIVE`;
  - `extract_native_token_correlation.py:291` passes `SWEEP_EPOCH_ACTIVE`;
  - `validation/candidate_pilot.py:522` (`_application_source_observations`) passes `SWEEP`;
  - `candidate_pilot.py:259` passes `SWEEP`. This is the recorded, non-blocking `secretBearingTextDetected` flag of the
    all-service `application.log`.

  `/usr/bin/grep` finds no other caller in `modules/`. The adapter digest-binds the file as `secret-scanner`
  (`candidate_runtime_adapter.py:136`), so the new controller digests come with the new commit, and `auto` rebuilds the
  readiness binding.
- **Scoped to the sweep epoch.** The scanner is shared by both epochs: the same file, the same callers, and no epoch
  branch before this change. So a shared change would alter the frozen epoch's verdict on any frame-bearing log. Each
  caller now passes its module's sweep flag (`study_epoch.active(...)["sweep"] is True`). The frozen epoch takes the
  default `False` path, which applies the same two conditions as before, split in two, plus a type check. Its
  behaviour is therefore unchanged by construction. This follows decision 25 and Q3, which also left the frozen epoch
  unchanged.

  A shared change would have cost no retained frozen evidence. Of **312** distinct retained `auth.log` /
  `persistence.log` files (frozen #10–#19, epoch-3 rungs, sweep attempt 1, relaunch 1; `.operational` staging copies
  excluded), the old and new verdicts differ for exactly **1**: relaunch 1 cell 11's `persistence.log`. **0 of 312**
  are flagged in sweep mode. This was rerun on `0588a41` with the same result.
- **Descriptor**. `collection.witnessLogSecretScan` states the rule (`candidate_sweep.py:525`). The descriptor was
  regenerated with `--write-descriptor`, not hand-edited.
- **Commits**:
  - `1a3ca07` is the rule, the scope, the descriptor and the tests.
  - `0588a41` makes three changes after the independent review (see Review):
    - nothing may be glued to the `)` (A1);
    - an overlong key blocks before the frame test (A2);
    - a test now reaches the JSON walk (B1).

## Tests
- Worktree suite (`uv run pytest -q -p no:cacheprovider --ignore tests/test_mlflow_manifest.py`):
  - **before** (`e6d6600`): 20 failed, 1767 passed, 162 skipped;
  - `1a3ca07`: 20 failed, 1813 passed, 162 skipped;
  - **after** (`0588a41`): 20 failed, **1822 passed**, 162 skipped.

  The failures are identical by name at all three commits (`comm` on the sorted FAILED lines): Hotel materialize ×4,
  OB-LGTM ×12, OB ×1, openspec ×1, OTel materialize ×1 and the science-epoch router ×1, the same set as amendment 1.

  The +55 passing tests are attributed as follows. 46 come from `1a3ca07` (`--co` diff against `e6d6600`, with no
  other node added or removed). The other 9 come from `0588a41`: 8 new negatives and 1 JSON-walk test.

  | file | test | count |
  |---|---|---|
  | `test_teastore_secret_scan.py` | frames pass in sweep mode | 1 |
  | | frames block with the frozen default | 1 |
  | | the rule is narrow | 27 + 8 |
  | | the switch reaches the JSON walk | 1 |
  | | the ceiling | 1 |
  | | the switch must be a bool | 3 |
  | `test_teastore_traffic_sweep.py` | a sweep cell with synthesized frames in both witness logs seals valid (throttle r10, no-fault r1) | 2 |
  | | the three callers share one scanner and scope the rule (sweep tree: pass; frozen tree copy: each raises) | 1 |
  | | 8 non-frame secrets still block every caller | 8 |
  | | a non-digit frame refuses a throttle r10 cell | 1 |
  | | `secret_scan.py` added to the 3.9-floor grammar list | 1 |

  The negatives cover:
  - frame-shaped locations with a non-digit value (`abc`, `12x`, empty, `-1`, ` 12`, Arabic-Indic digits);
  - a missing `)`, `=`, or a space before `:`;
  - text glued to the `)`, e.g. `password(Store.java:1)=…` or `…:12)x`;
  - `.txt` or `.javascript`, `(.java`, no `(`, two `(`, no method before `(`;
  - an overlong key, both with a secret name and as a frame;
  - frames inside JSON strings;
  - `password=…`, `session: x`, `"password": 1`, `Authorization: Bearer …`, `bearer …`;
  - `db_password=…`, `sessionToken: …`, and an exception header with `sessions` in its class name;
  - a frame followed by `password=…` on the same line and `session:` on the next;
  - JSON with a frame and a `password` field, and a quoted frame key.

  All frames are synthesized (`org.example.*`); no retained log text is used.
- Measurement repo `uv run pytest -q` at `0588a41`: **955 passed, 1 skipped, 3 xfailed**. This equals amendment 1's
  count; no module was added, so `test_unbound_names` is unchanged.
- **The positive tests fail on `e6d6600`.** I ran the final test files in a `git archive e6d6600` copy. These fail:
  - both frames-in-a-cell tests, with `WitnessError: auth log contains secret-bearing raw text`;
  - the caller-scope test, with `persistence log contains secret-bearing raw text`;
  - the scanner positives and the JSON-walk test, because the switch does not exist there (`TypeError`).

  The last group shows little: the switch is simply absent. The cell-level failures are the discriminating ones. The
  bool-switch test also fails there, for the same non-discriminating reason.
- **Planted defects: 8 of 8 were caught**, one at a time in a scratch copy of `0588a41`, each restored after
  (`-x`, first failing test):

  | planted defect | first failing test |
  |---|---|
  | **digits requirement dropped** (`[0-9]+` → `[^)\n]*`) | `test_the_jvm_frame_rule_is_narrow[…(Store.java:abc)]` |
  | `(` not required in the key | `…[…(.java:12)]` |
  | `=` accepted as separator | `…[…(Store.java=12)]` |
  | `return False` instead of `continue` after a frame | `…[…(Store.java:12) password=…]` |
  | witness passes `True` in every epoch | `test_the_three_callers_share_one_scanner_and_scope_the_frame_rule_to_the_sweep` |
  | A1 reverted (text glued to `)` allowed) | `…[password(Store.java:1)=…]` |
  | A2 reverted (frame test before the overlong-key bound) | `…[xxx…password(Store.java:12)]` |
  | switch not threaded into `_walk_json` | `test_the_switch_reaches_the_json_walk` |

## Replay of relaunch 1 (offline, capture level only; no detection time, catch or score computed)
- **Evidence.** The archive is `tmp/teastore-sweep-evidence/teastore-traffic-sweep-v1-relaunch1.tgz` (made by the
  coordinator; sha256 `beac0eb7…cbb599`, 26.7 MB). It was extracted to the session scratchpad (330 files). The digest
  of the copy's sorted file list, `find teastore-traffic-sweep-v1 -type f | LC_ALL=C sort | xargs shasum -a 256 |
  shasum -a 256`, is `8c4789b2…aae54`, equal to the host value recorded in
  `teastore-traffic-sweep-v1-relaunch1.host.sha256sum-of-list`. The only srv5 contact in this work was the DRY_RUNs'
  read-only queries (campaign status, `docker info` / `docker ps`, `df`); nothing there was moved or deleted.
- **Which file.** The scanned file is the top-level bounded `persistence.log` of `b01-11-full.blocked-evidence`
  (4,500 lines). The `.operational` staging copy is longer (4,891 lines).
- **Method.** This is the attempt-1 replay script, unchanged, run on a tree byte-identical to `0588a41` (`diff -rq`
  against `git archive HEAD`), with relaunch 1's runtime package. The interpreter was `/usr/bin/python3` 3.9.6 with a
  fresh `-X pycache_prefix`.
  - **Cell 11:** the producer's post-slice steps are re-run from the retained `.operational` staging, with its
    collector blockers recomputed. Those steps are app-witness extraction, native-token correlation and sealing, and
    the cell validator follows them.
  - **The 10 valid cells:** `validate_run` on copies.

  The same replay at `1a3ca07` gave identical summaries.
- **Cell 11 now seals valid**: production `validated`, `safeToContinue`, verdict pass, **0 of 37 gates failed**.
  - The witness extraction passes the secret scan: 1,885 auth and 2,516 persistence witness observations, and 1,800
    ledger opportunities.
  - The native-token extraction reads 1,800 bridge observations.
  - Decision 25: window (i) [60.072, 139.118] s holds 791 journeys, 371 of them incomplete, 288 unattributable
    clusters and 7,528 defective records. All of these are recorded, not blocking. Window (ii) holds 1,009 successful
    journeys with **0 incomplete of an allowance of 10**.
  - Drain allowance: 0 excused failures.
  - **Nothing else blocks it on this evidence.**
- **The 10 valid cells stay valid** (pass, no failed gate, (ii) 0 incomplete in each):

  | # | cell | relaunch 1 (host) | replay at `0588a41` | (ii) incomplete / allowance | (i) incomplete journeys |
  |---|---|---|---|---|---|
  | 1 | auth-freeze r10 | pass | pass | 0 / 9 | 19 |
  | 2 | auth-freeze r0.2 | pass | pass | 0 / 1 | 2 |
  | 3 | auth-freeze r1 | pass | pass | 0 / 1 | 14 |
  | 4 | no-fault r0.05 | pass | pass | 0 / 1 | — |
  | 5 | no-fault r1 | pass | pass | 0 / 1 | — |
  | 6 | no-fault r10 | pass | pass | 0 / 18 | — |
  | 7 | auth-freeze r0.05 | pass | pass | 0 / 1 | 1 |
  | 8 | no-fault r0.2 | pass | pass | 0 / 1 | — |
  | 9 | throttle r0.2 | pass | pass | 0 / 1 | 1 |
  | 10 | throttle r0.05 | pass | pass | 0 / 1 | 0 |
  | 11 | throttle r10 | **blocked** (`WitnessError`, secret scan) | **pass** | 0 / 10 | 371 |
  | 12 | throttle r1 | — (not run) | — | — | — |

- **Notes on the replay.**
  - Run with `-I`, the laptop replay reported `ModuleNotFoundError: jsonschema` in the native-token gate. On this laptop
    `jsonschema` lives in the user site, which `-I` excludes. On srv5 the installer requires it as a runtime module
    (`candidate_release_installer.py:93`, `RUNTIME_PYTHON_MODULES`), and the 10 cells sealed there with the same
    import. This is not a host blocker.
  - A 3.13 run (at `1a3ca07`) gives the same verdict and gate summary. Its `candidate-validation.json` differs only in
    the scratch path and in one float (`signatureWeightedRecords` 27.999999999999105 vs 28.0, the 3.12+ compensated
    `sum()`).
  - The recorded, non-blocking `application.log` flag `secretBearingTextDetected` is True in 8 of the 10 retained valid
    cells and in cell 11, in sweep mode too, and the fix leaves that unchanged. The reviewer decomposed it as one
    overlong quoted key spanning lines, which fails closed, with 0 bearer and 0 unquoted secret keys. It is not the
    frame rule. No test references it, and it never blocks.

## Binding
- Harness `e6d6600` → **`0588a412ea7355f0aaa143b5468e8c4b9b7f0943`** (via `1a3ca07`). The selector stays committed and
  the activation is unchanged.
- Descriptor `f2e35292…` → **`f90bd64c13075c3019c03c4aee4df3744bb1494b194645b17d246bea063b160a`**.
- Plan `c7df47ab…` → **`88a3017a781233a4848f7ea638b4763f82f63bc902d848514cd8ae5089529355`**. It is identical under
  `/usr/bin/python3 -I` (3.9.6, fresh `-X pycache_prefix`) and `uv run` (3.13.12).
- `1a3ca07`'s intermediate pins, `5547b104…` and `5eb58cf3…`, are superseded and must not be launched.
- **Cell timing, run IDs, order and run keys are unchanged** (compared cell by cell against `e6d6600`). The only plan
  field that differs is `descriptorSha256`, and the only descriptor field that differs is
  `collection.witnessLogSecretScan`.
- Descriptor file sha256 `e2aa24a4…`, so the plan directory is `.local/candidate-v4/teastore/plan-e2aa24a4`
  (materialized under `/usr/bin/python3 -I`; campaign sha256 `68b3198d5edf6718a6ddaa752febef021688349b2cac501b83c06f0cd830051a`).

## Dry run
DRY_RUN on `0588a41`, rc 0 (`scratchpad/gate-drivers/teastore-sweep1r2dry2-launch.log`, paths shortened). The first
DRY_RUN, `sweep1r2dry` on `1a3ca07`, also passed (rc 0); it is superseded.
```
15:47:33Z === teastore launcher sweep1r2dry2 (ROOT .../observability-placement-runtime-teastore-protocol, HEAD 0588a41, dry=1) ===
15:47:37Z previous campaign status (<worktree> live package): state=stopped systemd=failed/failed result=exit-code journalRows=11 terminal=False abort=True lease=False
15:47:38Z plan: descriptor f90bd64c..., firstRunId .../auth-freeze-effect/r10/b01/full/a01, minimumFirstMutationRemainingSeconds 6600, plan 88a3017a..., runCount 12, runWindowHours 3
15:47:38Z drivers read: ROOT=<worktree> STUDY=teastore-traffic-sweep-v1 RUN_WINDOW_HOURS=3 PLAN_DIR=.../plan-e2aa24a4 SWEEP=True
15:47:42Z srv5 host facts (stdout only): ncpu=24 cgroup=systemd/2 candidate_containers=0 containers=0
15:47:42Z authorization: HEAD 0588a41... / authorized 2026-10-03T13:41:16Z deadline 2026-10-10T13:41:16Z live=True / provenance derived by `auto` / invariants match=False
15:47:46Z srv5 free GB (stdout only): 365
15:47:46Z DRY RUN: all guards passed; stopping before the first mutation
```
The SETUP-CAMPAIGN invariants no longer match because the digests are new, so `auto` re-derives it and records it as
auto-derived.

## Relaunch 2
- **All 12 cells, relaunch 2 of 2.** The plan, run IDs and seeded onsets are the same as attempt 1 and relaunch 1.
- **Decided** (user, decision j; as amendment 1 did for attempt 1): relaunch 1's 10 valid cells are **not pooled**. They are same-plan
  repeats under an older harness, and any use of them is exploratory. 
- **Attempts and results root.**
  - TeaStore's adapter keeps **no spent-attempt record**. `ATTEMPT = 1` is a constant bound into every run key
    (`candidate_runtime_adapter.py:85`), and the "attempt is consumed" guard (`:2530`) is per process. Attempt 1 and
    relaunch 1 both ran run IDs `…/a01`, and relaunch 2 will too.
  - Launches are separated by setup ID. `campaign_setup.py:369` mints `secrets.token_hex(16)` on every `auto`, and the
    results root is `RESULTS_ROOT / setup_id` (`candidate_release_installer.py:1404`, `:2426`). Relaunch 2 therefore
    gets a **new results root**, and relaunch 1's root `results/31fa6248…` is not touched. **Nothing needs moving.**
- **Local gate state.** The gates directory still holds relaunch 1's working set, bound to `e6d6600`: `gate-run.json`,
  `runtime-package.json`, `run-authorization.json`, `campaign-terminal.json` and the release bundle. It holds no lease
  lock file. The same path worked for relaunch 1 after attempt 1, because the launcher and `auto` clear it:
  - the launcher moves the four run-state files (and any `campaign-result/`) into
    `gates/run-state-before-sweep1r2-<stamp>` before `auto`;
  - `auto`'s `archive_previous` moves the setup documents into `gates/attempt-<stamp>-<commit>`;
  - `auto` unlinks and rebuilds the bundle and manifest.

  All of these are moves except the rebuilt bundle. A copy of relaunch 1's runtime package is also kept with the
  replay.
- **Command**, after this amendment is committed alone:
  ```
  W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
  M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
  cd $M
  TEASTORE_ROOT=$W EXPECTED_HEAD=0588a412ea7355f0aaa143b5468e8c4b9b7f0943 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_sweep.py EXPECTED_PLAN=88a3017a781233a4848f7ea638b4763f82f63bc902d848514cd8ae5089529355 RUN_COUNT=12 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh sweep1r2 > $M/scratchpad/gate-drivers/teastore-sweep1r2.out 2>&1 &
  nohup uv run python tools/wandb_campaign.py follow teastore-sweep1r2 scratchpad/gate-drivers/teastore-sweep1r2-launch.log \
    > scratchpad/gate-drivers/teastore-sweep1r2-wandb.out 2>&1 &
  ```
- Expected wall time: relaunch 1 took ~62 min for 11 cells, so 12 cells take about 70 min. This is `?` until the
  cells run, and the GATE-RUN window is 3 h.
- **Residual risk (by design).** A non-frame line whose key embeds a secret name still blocks a cell. One example is
  an exception header such as `Caused by: <package>.sessions.<Name>Exception: …`; it blocks in both modes (review, B5).
  None was seen in the 312 retained logs (0 flagged in sweep mode).

  Exceptions under the throttle are not deterministic, though: attempt 1 had 0 frame lines in cell 11 and relaunch 1
  had 1,344. A block of that kind would be TeaStore's 3rd critical-path defect, and the stop rule would apply.
- The analysis stays blind: no detection result of attempt 1, relaunch 1 or this replay has been looked at.

## Review
One read-only adversarial review of `1a3ca07` was run by a separate subagent (Fable, `adversarial-review`, neutral
prompt: five questions and three report categories). It ran:
- probes of 27+ inputs under 3.9;
- per-file counts of the frame locations in cell 11;
- 10 scanner mutants;
- the digests under 3.9 and 3.13;
- a cell-by-cell plan comparison against `e6d6600`;
- the scanner and sweep test files (212 passed, 3 skipped);
- the 3.9 import of the changed target files.

| finding | rating | action |
|---|---|---|
| A1: text glued to the frame's `)` passed (`password(Store.java:1)=x`), wider than the documented ceiling | defect (falsified claim; no retained log has this shape) | **fixed** in `0588a41` (`(?=\s|\Z)`), 4 negatives |
| A2: the frame skip ran before the overlong-key bound | defect (invariant broken; real frame keys ≤ 151 chars) | **fixed** in `0588a41`, 2 negatives |
| B1: a mutant dropping the switch in `_walk_json` survived | test gap | **fixed**: `test_the_switch_reaches_the_json_walk` |
| B2: the e6d6600 failures of the scanner tests are mostly `TypeError` (switch absent) | weak evidence | recorded (Tests); the cell-level failures are the discriminating ones |
| B3: the gates directory holds relaunch 1's working set (`e6d6600`) | process | recorded (Relaunch 2, local gate state); the launcher and `auto` move it, as for relaunch 1 |
| B4: `application.log` `secretBearingTextDetected` is True for an unrelated reason (overlong quoted key) | reader trap | recorded (Replay notes) |
| B5: `Caused by: <pkg>.SessionException: …` still blocks in both modes | residual stop risk | recorded (Relaunch 2, residual risk) |
| B6: say which `persistence.log` the counts come from | clarity | recorded (Replay, which file) |

The review's checks that held:
- the digests are equal under 3.9 and 3.13;
- the descriptor bytes equal the generator's output;
- the plans differ only in `descriptorSha256`;
- the four call sites are as listed and scoped;
- the frozen path is unchanged;
- the replay outputs are byte-identical between 3.9 and 3.13 at the summary level;
- 312 files, 1 verdict change, 0 flagged.

`0588a41` itself has not had a second independent review.
