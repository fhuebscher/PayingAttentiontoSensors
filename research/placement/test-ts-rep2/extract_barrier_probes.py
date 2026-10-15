"""Extract each cell's queue-proof measurement.barrierProbes summary (validity data; read-only on evidence).
Usage: python3 -I extract_barrier_probes.py <fetch dir (rep2-fetch)> <new output json>
The acknowledging probe is the last probe in the list (the harness stops probing at the first read of an empty queue, or at the bound);
consumerAtStart (measurement.consumerAtStart, the value the validator binds to queueMessagesAtBarrier) is recorded beside it for comparison.
"""
import json, sys
from pathlib import Path

fetch = Path(sys.argv[1]); out = Path(sys.argv[2])
assert not out.exists(), "new evidence never overwrites old"
root = fetch / "x/teastore-offpath-v1"
camp = json.loads((root / "campaign.json").read_text())
cells = []
for run in camp["runs"]:
    q = json.loads((root / run["path"] / "queue-proof.json").read_text())["measurement"]
    probes = q["barrierProbes"]
    ack = probes[-1]
    cells.append({
        "runId": run["runId"], "regime": run["regime"], "posture": run["posture"], "block": run["block"],
        "probeCount": len(probes),
        "probes": [{"startOffsetS": p["queryStartedMonotonicOffsetSeconds"],
                    "completedOffsetS": p["queryCompletedMonotonicOffsetSeconds"],
                    "messages": p["messages"], "consumers": p["consumers"]} for p in probes],
        "acknowledgingProbe": {"index": len(probes), "completedOffsetS": ack["queryCompletedMonotonicOffsetSeconds"],
                               "messages": ack["messages"], "consumers": ack["consumers"]},
        "consumerAtStartMessages": q["consumerAtStart"]["messages"],
        "consumerAtStartConsumers": q["consumerAtStart"]["consumers"],
    })
counts = {}
for c in cells:
    counts[c["probeCount"]] = counts.get(c["probeCount"], 0) + 1
doc = {
    "kind": "teastore-offpath-rep2-barrier-probes",
    "cells": len(cells),
    "probeCountDistribution": {str(k): counts[k] for k in sorted(counts)},
    "cellsAckMessagesZero": sum(c["acknowledgingProbe"]["messages"] == 0 for c in cells),
    "cellsAckConsumersOne": sum(c["acknowledgingProbe"]["consumers"] == 1 for c in cells),
    "cellsConsumerAtStartMessagesZero": sum(c["consumerAtStartMessages"] == 0 for c in cells),
    "cellsWithMoreThanOneProbe": sum(c["probeCount"] > 1 for c in cells),
    "maxAckCompletedOffsetS": max(c["acknowledgingProbe"]["completedOffsetS"] for c in cells),
    "minAckCompletedOffsetS": min(c["acknowledgingProbe"]["completedOffsetS"] for c in cells),
    "cellDetail": cells,
}
out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
print({k: v for k, v in doc.items() if k != "cellDetail"})
