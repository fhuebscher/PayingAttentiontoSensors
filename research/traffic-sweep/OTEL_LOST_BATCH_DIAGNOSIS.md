# OTel quiet run A1, cell `calibration/r10-b02-04-full`: where was the productcatalogservice batch lost? (2026-10-09)

Scope: instance (one cell, one run). Read-only on the retained evidence
`tmp/otel-quiet-evidence/attempt1-fetch/retained/runs/calibration/r10-b02-04-full/` (pcap sha256 `4e80a333…96bfe`, matches
`telemetry-bytes.json`). No host contacted, no repo file changed. Not yet reviewed by an independent session.

## Verdict: collector-side, not SDK-side

The SDK exported the batch and the collector received it. The batch also left the collector on its OTLP exporter and was
counted by the spanmetrics connector. Only the debug exporter's text record in `otelcol.log` is missing. The most likely
mechanism, a candidate that was computed but not executed, is the collector's own log sampler dropping that one record.

## Evidence

Times are UTC. The pcap shows +11:00 local; frame numbers are `tshark` frame numbers. The capture is on `any`, so every
packet appears twice (consecutive frame numbers).

1. **SDK exported it, and the collector received it.** Frames 12583-12588, `10.151.0.19 -> 10.151.0.9:4317`
   (productcatalogservice -> collector), 09:52:01.272 (+139.9 s into the cell). One gRPC message, 25 212 B, 50 spans.
   All 50 trace IDs of the 50 incomplete requests are in it (the 50 IDs come from `trace-completeness.json`
   `incompleteRequestTokens` mapped through `request-ledger.json` `originalTraceId`). 50 of 50 found; independent
   `tshark -Y 'frame contains <id>'` finds the first and last ID in frames 12583/12584 and 12587/12588.
   The two other sources carrying these trace IDs are frontend-proxy (`.26`) and frontend (`.24`), as expected.
2. **The collector forwarded it.** Frames 12599/12600, `10.151.0.9 -> 10.151.0.3:4317`, 09:52:01.2915 (19 ms after
   receipt). The gRPC message is gzip compressed (3 827 B; decompresses to 25 212 B, the same 50 spans and trace IDs).
   `10.151.0.3:4317` is not identified in this evidence (the upstream demo config sends `otlp` to `jaeger:4317`; the
   harness config is not in the evidence). The capture filter is `tcp dst port 4317/4318`, so no acknowledgement is visible.
3. **The spanmetrics connector, a sibling consumer of the same traces pipeline, counted it.** Cumulative `calls` for
   `productcatalogservice` (GetProduct, server) at the 60 s flushes: delta 600 / 600 / 551 against 600 / 600 / 550 spans
   on the wire in the same windows. The 3rd window (09:51:50-09:52:50) contains the lost batch. Had it been missed, the
   delta would be 501. (The +1 is one span not seen as part of the batches; not chased.)
4. **Only the debug-exporter body is absent.** Across the capture, 1 164 inbound trace exports (12 705 spans) were matched
   by span ID against `otelcol.log` (14 782 span IDs in the log). 1 163 are present in full; exactly one is absent, this
   one: 0 of its 50 span IDs and 0 of its 50 trace IDs appear under productcatalogservice. The other 36 pcs batches in
   the capture all have a log body 8-190 ms after receipt. In the log, nothing sits between the frontend-proxy body at
   09:52:01.089 and the next trace body at 09:52:01.493 except one metrics body.
5. **No error evidence.** `otelcol.log` has no warn/error/drop/refused/queue line at all: every non-body line is a
   startup `info`.

## Candidate mechanism (computed, not executed)

The collector logs through zap with sampling. Evidence in this log that sampling is on: the one-line `TracesExporter`
summary appears at most 10 times per 10 s window (17 of 24 aligned 10 s ticks show exactly 10; 222 summaries for 433+
trace bodies). Around the event: 10 summaries from 09:51:52.835 to 09:51:57.668, then none until 09:52:02.897, which is
10.06 s after the window opened. The lost body falls inside that exhausted window.

zap's sampler counts by (level, message) in 4096 hash buckets (FNV-1a 32-bit, `% 4096`) and drops everything past the
first `initial` messages per tick whose bucket is shared. The debug body is one unique message per batch, so it is
normally never sampled, but a body whose message hashes into the same bucket as the (exhausted) message `TracesExporter`
is dropped. I rebuilt the lost batch's exact message text from the wire (the same reconstruction reproduces the logged
text of 15 of 15 present pcs bodies byte for byte; the resource/scope header is identical in all 35 pcs bodies in the
log) and hashed it: bucket **870** with the trailing newline the log format implies, which is also the bucket of
`TracesExporter` (870). Chance of that coincidence is 1 in 4096.

Limits: the sampler parameters (initial 10, thereafter 100, tick 10 s) are inferred from this log and from my recall of
the collector defaults, not read from the harness's collector config. I did not run the collector or zap on the message.
If the mechanism is right, the loss is a deterministic function of message text and window state, not random noise, and
about 3/4096 of all bodies (traces, metrics, logs: buckets 870, 715, 3771) are exposed whenever their summary bucket is
exhausted. Rough order of magnitude: about 0.06 trace-body drops per cell, against one observed in 8 quiet cells and 0 in
4 r10 sweep cells.

## What this changes for the open items

- `STOP_QUIET_OTEL_A1.md` said the loss was between collector receipt and the debug-exporter carrier and that an SDK
  drop was not ruled out. The SDK reading is now ruled out for this cell (point 1).
- The carrier (`otelcol.log`) can silently lose a batch while the telemetry is intact on the wire and downstream. For any
  `absent` calibration, the pcap is the carrier that did not lose it; `trace-completeness.json` computed from the log
  counts it as a system loss.
- Candidate fixes, none applied (they change what the harness emits, so they are for the user to classify): disable
  collector log sampling (`service::telemetry::logs::sampling::enabled: false`); or cross-check the log against the pcap
  in the terminal (adds to open item M3).

## Reproduce

Scripts are in the session scratchpad, which is reaped; copy them if they are wanted:
`/private/tmp/claude-502/-Users-fhuebscher-Desktop-ma-thesis-oltp-submodularity-evaluation-observability-placement/70ef7069-de5b-4b65-a510-310d1fa1a1a1/scratchpad/otel-batch/`
(stdlib only, run with `uv run --no-project python -I <script> <scratch> <cell dir>`).

```
CELL=tmp/otel-quiet-evidence/attempt1-fetch/retained/runs/calibration/r10-b02-04-full
T=/Applications/Wireshark.app/Contents/MacOS/tshark
$T -r $CELL/telemetry.pcap -T fields -e frame.number -e frame.time_epoch -e ip.src -e tcp.srcport -e tcp.dstport \
   -e tcp.stream -e tcp.seq_raw -e tcp.flags -e tcp.len -e tcp.payload -E separator=, > pkts.csv
python reasm.py pkts.csv streams.pkl        # TCP reassembly per stream, retransmits and capture duplicates dropped
python decode.py .                           # HTTP/2 frames -> gRPC messages (gzip handled) -> OTLP traces; HTTP/1.1 too
python analyse.py . $CELL                    # 50 trace IDs: on the wire inbound from .19 and outbound from .9
python batch.py . $CELL                      # per-batch table; the 09:52:01.272 batch carries all 50
python allexports.py . $CELL                 # every inbound export vs span IDs in otelcol.log: 1 absent of 1164
python spanmetrics.py . $CELL                # spanmetrics `calls` deltas vs wire spans
python recon.py . $CELL && python bucket.py .   # rebuild the lost message; bucket 870 == TracesExporter
python sampler.py $CELL                      # summary-line windows; bucket of each logged body
# independent check of one ID (no script):
$T -r $CELL/telemetry.pcap -Y "frame contains 47801a33405427eec68bf381b09a31d3" -T fields -e frame.number -e ip.src -e ip.dst
```

What was checked and how: the packet decoding was checked against `tshark`'s byte search for 2 of the 50 IDs and against
`trace-correlation.json` (observed 1750 complete, 50 incomplete, matching the log and the pcap per service). The
reconstruction was checked against 15 present log bodies (15/15 identical). Nothing was seen failing on a planted defect.
