# Budget and stop rule: OTel campaign F (detection lanes: own silence, coordinator, consumer-group lag), 2026-10-13

Committed alone, before any F work. Authority: user, 2026-10-13 ~13:40Z, choosing "Yes, full F" on the plan
`research/PLAN_LANES_20261014.md` (`c2914de`). Campaign E's FAIL stays reported as it is (`research/placement/test-e/RESULT_E.md`).
Scope of every number: instance (OTel Demo 1.12.0 on fb14srv6). Paper deadline 2026-10-16 11:59Z.

## What F is
E's design (upstream mix, open loop, 25 req/s; regimes no-fault, frauddetectionservice pause, accountingservice pause, frontend
pause as on-path control; split blocks 1-3 training / 4-5 test) with four changes, in a new epoch (`otel-offpath-f-v1`):
1. SDK metric export interval 5 s (`OTEL_METRIC_EXPORT_INTERVAL=5000`) where the SDK honours it; which services do is recorded.
2. spanmetrics connector flush interval 5 s.
3. The collector's `kafkametrics` receiver (consumer-group lag, scrapers `consumers`, 5 s), with `service.name=kafka` upserted.
   If the receiver is not in the pinned contrib image (0.108), F runs without it and the declaration says so before launch.
4. More no-fault time: two no-fault cells per block (engineering default; final count in the declaration).

## Sequence and deadlines (UTC)
1. Harness epoch F (tests with a planted defect per change, activation): **2026-10-14 00:00Z**.
2. Independent review GO; per-lane manifestation/prediction text and the pass rule in a declaration committed alone; DRY_RUN
   passed: **2026-10-14 03:00Z**.
3. Launch by **2026-10-14 03:30Z**; terminal and fetched (byte-verified) **2026-10-14 10:00Z**. At most 1 relaunch, harness or
   infrastructure defects only.
4. Reader v3.3 (admits F and the TeaStore off-path epoch) frozen by digest **before any F cell is read**: **2026-10-14 08:00Z**.
5. Training placement and scoring, outputs committed unedited before reading: **2026-10-14 16:00Z**. Paper text from then.

## Stop rules
1. A missed deadline stops that step; the paper then reports E and the offline lane rows only. No extension without the user.
2. 30 minutes per critical-path defect; 3 critical-path harness defects stop F.
3. Launch only from a declaration committed alone plus a passing DRY_RUN, mirrored to wandb; one campaign per host (srv6).
4. No F cell is read (validity fields only) before v3.3, the training placement and the pass rule are frozen.
5. Disk guard 40 GB free; collector log and pcap volume grow with 5 s export, so the DRY_RUN reports per-cell bytes.

## Amendment 1 (user, 2026-10-13 ~23:45Z, committed alone)
The coordinator's VPN dropped (~23:00Z, all three hosts unreachable) while F's activation was blocked by a permission denial. The user reconnected the VPN and
**extended every deadline above by one day** (harness 2026-10-15 00:00Z; review, declaration, DRY_RUN 03:00Z; launch by 03:30Z; terminal and fetched 10:00Z;
reader v3.3 frozen 08:00Z; scoring 16:00Z, all 2026-10-15), and asked to rerun. Stop rules unchanged. The paper deadline (2026-10-16 11:59Z) is unchanged.
