#!/usr/bin/env python3
"""Count distinct OTel log templates per service under the adapter's templating and the fixed one (README table).

    /usr/bin/python3 -B research/protocol/sensor_rep/otel_templates.py [tmp/otel-v3-evidence]
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensor_rep.parsers import common, otel  # noqa: E402


def main(root):
    toks = {m: defaultdict(set) for m in ("symptoms", "callsite")}
    nf = {m: defaultdict(set) for m in toks}
    basis = Counter()
    for d in otel.cell_dirs(root):
        with open(d / "otelcol.log", encoding="utf-8", errors="replace") as fh:
            logs, _ = otel.parse_log_records(fh)
        for svc, recs in logs.items():
            for r in recs:
                for m in toks:
                    tid, how = otel.template(r, m)
                    toks[m][svc].add(tid)
                    if "no-fault" in str(d):
                        nf[m][svc].add(tid)
                    if m == "callsite":
                        basis["%s/%s" % (svc, how)] += 1
    out = {"allCells": {m: {s: len(v) for s, v in sorted(t.items())} for m, t in toks.items()},
           "noFaultCells": {m: {s: len(v) for s, v in sorted(t.items())} for m, t in nf.items()},
           "fixedKeyBasisRecords": dict(sorted(basis.items()))}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else common.REPO / "tmp" / "otel-v3-evidence")
