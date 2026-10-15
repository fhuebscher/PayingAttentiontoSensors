"""POST HOC: the reader's own level material, thresholds and per-rule alarms for the two frozen sets' sensors on the 4 held-out
no-fault cells (same call as fresh_fa_f.py, then the reader's level_material / thresholds / simulate on the validation cells under the
same context). Writes out/reader_detail.json for hand_check.py. Imports the frozen reader; edits nothing.
    uv run python research/placement/test-f/fresh-fa/reader_detail.py <new output json>
"""
import sys, json
sys.path.insert(0, "research/detection-time")
import sweep_analysis_v3_3 as v33, sweep_analysis_v3_2 as v32, sweep_analysis_v3 as v31, sweep_analysis_v2 as v24
from pathlib import Path
farm = Path("tmp/fresh-fa-f/farm"); camp = Path("tmp/otel-f-evidence/f1-fetch/x")
blocks, tb = {1,2,3,4,5}, {4,5}
R = v33.run33(camp, system="otel", validation_dirs=[farm], blocks=blocks, split="research/protocol/split_f_otel.json", test_blocks=tb)
out = {}
with v24.use_system("otel"), v33._v33_wrapped(False), v32.v32_context("otel", R["_v32ctx"]["rates"], blocks, tb):
    found, vcells = v31.find_and_load3([farm])
    cr = R["cal"]["primary"]["perRate"][25]
    F = R["fits"][25]
    share = v24.ARMS["primary"]
    for sid in ["metric:kafka:kafka.consumer_group.lag", "metric:kafka:kafka.request.count"]:
        key = tuple(sid.split(":", 2)); key = (key[0], key[1], key[2])
        for X in vcells:
            ts, vs, inst = v31.level_material(X, key)
            lv = F.lvl(key)
            row = {"cell": X["cell"], "t0wall": X["t0"]["wall"], "endwall": X["end"]["wall"], "t0mono": X["t0"]["mono"], "endmono": X["end"]["mono"],
                   "n": len(ts), "lvl": lv, "inst": inst, "ts": ts, "vs": vs, "rules": {}}
            for rule in v31.LEVEL:
                val = cr["score"][(key, rule)]
                thr = v31.thresholds(F, key, lv, val, share, F.res.get(inst))
                row["rules"][rule] = {"value": val, "thr": thr, "alarms": [(t, n) for t, n in v31.simulate(X, F, [(key, rule, val)], share)]}
            out.setdefault(sid, []).append(row)
if Path(sys.argv[1]).exists():
    raise SystemExit("refusing: exists: " + sys.argv[1])
json.dump(out, open(sys.argv[1], "w"), default=str)
print("done")
