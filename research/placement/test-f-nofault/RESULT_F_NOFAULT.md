# R4: price check of F's frozen sensors on fresh no-fault time (attempt 6): result (2026-10-15)

Scope: **instance** (OTel Demo 1.12.0, fb14srv6, 25 req/s, F's deployment). POST HOC to every placement it checks. Every number is copied from
`out/price_check.json` / `.md` (`e8ea091`). **Review status:** one same-provider adversarial review (2026-10-15 ~17:20Z): every number confirmed, the output recomputed byte-equal; four sentences replaced, two made precise; no cross-provider review of this note.

- Declaration `research/traffic-sweep/DECLARATION_F_NOFAULT_PRICECHECK.md` (`882b09d`, committed alone before launch), budget amendment 2 (`a0e50a3`), wrapper
  `price_check.py` at `8fca1da` (sha256 `28eb4fdb…`, equal to the output's `scriptSha256`).
- Run: launched 13:30Z (label nf1, attempt 6, plan `0c7a9cdb…`, harness `715d57b`), GATE-RUN about 13:33-13:35Z (readiness 13:33:33Z, oneshot rc 0 13:35:37Z), terminal 16:03:01Z (`state=stopped`, `terminal=True`,
  `abort=False`; systemd `inactive/dead`, `result=success`; `remote-terminal.json`: 25/25 valid, `stopped: false`; `scratchpad/gate-drivers/otel-offpath-f-v1-nf1-launch.log`, uncommitted). Fetch `tmp/otel-f-evidence/nf1-fetch`: host files 437, OK 437, shasum rc 0,
  before the wrapper ran. The wrapper read only the 10 no-fault cells: `select_cells` enumerates `runs/calibration/` only, which holds exactly these 10, and the farm links to nothing else; the 15 fault cells (under `runs/effect/`) were touched only by the byte verification (macOS access times on 75 fault-cell files near the wrapper's start are unexplained, weak evidence, plausibly indexing; unverified).
- **Deviation:** the output files were written at 16:55:15Z (`out/price_check.*` and the wrapper's stdout log `tmp/otel-f-evidence/nf1-price-check.log`) and committed at 16:58:12Z (`e8ea091`); the main session displayed them in between (display time not recorded). They were not edited: a re-run of the wrapper's own row and presence code on the retained readouts reproduces `price_check.json` byte for byte, and the stdout log equals `price_check.md`.
- Presence check: every priced metric has raw samples in all 10 cells (lag 49/49, request.count 47-48, purgatory.size 48-49 per cell; whole-log counts, which do not detect a stream that stops part-way, declared).

## Result (10 no-fault cells, 0.50 h; one-sided 95 % bounds; training price = the frozen calibration's honest upper bound)
| set | sensor | k (union) | k/h | 95 % lower / upper per h | training price /h | verdict |
|---|---|---|---|---|---|---|
| F @6/T_r | `kafka.consumer_group.lag` | 0 | 0.00 | 0.00 / 5.99 | 15.81 | **bounded below the price** |
| F @3/T_r; ablation @6/T_r | `kafka.request.count` | 4 (spike) | 8.00 | 2.73 / 18.31 | 9.99 | consistent, not bounded |
| F rerun @6/T_r | `kafka.purgatory.size` | 5 (spike) | 10.00 | 3.94 / 21.03 | 9.99 | consistent, not bounded |

Ledger (unpriced; per rule, no union): every route has at least one rule with k >= 1; the largest per-rule counts are 7 (add-to-cart `spike`), 6 (ads `median`,
product `run3`, recommendations `median`).

## Predictions (declared before launch)
| id | prediction | result |
|---|---|---|
| NF-LAG | lag not contradicted; k <= 2 | **hit** (k = 0) |
| NF-REQ | request.count not contradicted; k >= 1 | **hit** (k = 4) |
| NF-PUR | purgatory.size not contradicted; k <= 3 | **miss** (not contradicted, but k = 5) |
| NF-ANY | at least one of the three bounded below the price | **hit** (lag) |
| NF-LED | at least one ledger rule on one route has k >= 2 (scored on per-rule rows, as NF-LED specifies; the ledger union rows are — by construction, the reader gives no ledger union) | **hit** (add-to-cart spike 7, among others) |

## What this does and does not say
- On 0.5 h of fresh fault-free time in F's deployment, none of the three priced sensors (lag and request.count with F's calibration, purgatory.size with the
  rerun's) is contradicted (instance); R2's `flagd.impression`, R2's set and the ablation's own request.count price (15.81/h) are not priced. F's lag sensor
  raised no alarm, so its fresh one-sided 95 % upper bound (5.99/h, R4's own zero-alarm floor) is below its training price (15.81/h, the bound for 1 honest
  training alarm): the price was not too low on this instance; this is not a measurement of lag's rate.
- request.count and purgatory.size alarmed 4 and 5 times (8 and 10/h, all spike). Their prices (9.99/h each) are the zero-alarm floor of 0.3 h of training
  no-fault time (0 honest alarms in 6 cells), a record that training saw no alarm, not a measured rate. The fresh intervals (2.73-18.31 and 3.94-21.03/h)
  contain the prices and reach about twice them: the prices are neither confirmed nor contradicted, and R4 cannot exclude rates up to twice the price. At
  0.5 h a contradiction needed k >= 10, so "not contradicted" is a weak result. NF-LED and NF-REQ were near-certain given the dry run and F's 2 alarms.
- The ledger's routes alarm in fault-free time too (per-rule counts up to 7 in 0.5 h); the ledger is the baseline and is never priced.
- Not an equivalence test; one host, one rate, one deployment; R2's flagd member and R2's set are not priced here (declared).
