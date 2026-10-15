"""Per-cell offline terminal replay of TeaStore off-path relaunch 1 (read-only on harness and evidence).

Usage (interpreter /usr/bin/python3 3.9, the host's; fresh PYTHONPYCACHEPREFIX, PYTHONDONTWRITEBYTECODE=1):
  python3 replay_ts_r1.py <teastore worktree> <fetch dir (r1-fetch)> <new output json>
Runs the harness's own validate_run on each cell and compares with the retained candidate-validation.json.
The campaign-level replay_fetched_campaign is also called once and its outcome recorded (it needs the evidence at
the host's absolute path, so it is expected to be blocked by host-path embedding on a laptop copy).
"""
import hashlib, importlib.util, json, re, sys
from pathlib import Path

W = Path(sys.argv[1]); fetch = Path(sys.argv[2]); out = Path(sys.argv[3])
assert not out.exists(), "new evidence never overwrites old"
sys.path.insert(0, str(W / "src"))
spec = importlib.util.spec_from_file_location("ts_transport", W / "modules/teastore/execution/candidate_transport.py")
m = importlib.util.module_from_spec(spec); sys.modules["ts_transport"] = m; spec.loader.exec_module(m)
root = fetch / "x/teastore-offpath-v1"
pkg = json.loads((fetch / "x/.packages/teastore-offpath-v1.json").read_text())
camp = json.loads((root / "campaign.json").read_text())
keys = {c["runId"]: c["runKey"] for c in pkg["cells"]}
term = m._terminal_module()


def diff(a, b, p=""):
    out_ = []
    if type(a) != type(b):
        return [{"pointer": p, "retained": a, "replayed": b}]
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out_.append({"pointer": f"{p}/{k}", "retained": a.get(k, "<absent>"), "replayed": b.get(k, "<absent>")})
            else:
                out_ += diff(a[k], b[k], f"{p}/{k}")
    elif isinstance(a, list):
        if len(a) != len(b):
            return [{"pointer": p, "retained": f"len {len(a)}", "replayed": f"len {len(b)}"}]
        for i, (x, y) in enumerate(zip(a, b)):
            out_ += diff(x, y, f"{p}[{i}]")
    elif a != b:
        out_.append({"pointer": p, "retained": a, "replayed": b})
    return out_


cells = []
for run in camp["runs"]:
    d = root / run["path"]
    retained = json.loads((d / "candidate-validation.json").read_text())
    replayed = term._candidate_validator().validate_run(d, expected=dict(keys[run["runId"]]))
    ds = diff(retained, replayed)
    cells.append({
        "runId": run["runId"], "path": run["path"], "replayVerdict": replayed.get("verdict"),
        "retainedVerdict": retained.get("verdict"), "byteEqualToRetained": not ds,
        "differences": ds,
    })

journal = [json.loads(l) for l in (root / "runtime-journal.jsonl").read_text().splitlines()]
anchors = {r["runId"]: r["manifestSha256"] for r in journal}
campaign_level = term.validate_candidate_campaign(
    root, expected_campaign_sha256=pkg["campaignSha256"], manifest_anchors=anchors)
host_path = root / "campaign-terminal-validation.json"
host = json.loads(host_path.read_text())
doc = {
    "kind": "teastore-offpath-relaunch1-per-cell-terminal-replay",
    "setupId": pkg["setupId"], "campaignId": pkg["campaignId"], "frameworkCommit": pkg["frameworkCommit"],
    "interpreter": sys.version,
    "campaignLevelReplay": {
        "verdict": campaign_level.get("verdict"), "blockers": campaign_level.get("blockers"),
        "runReportVerdicts": sorted({r.get("verdict") for r in campaign_level.get("runReports", [])}),
        "label": "blocked by host-path embedding (not an evidence defect)",
    },
    "cellsReplayed": len(cells),
    "cellsReplayPass": sum(c["replayVerdict"] == "pass" for c in cells),
    "cellsByteEqualToRetained": sum(c["byteEqualToRetained"] for c in cells),
    "cellsDifferingOnlyInObservationPath": sum(
        (not c["byteEqualToRetained"]) and all(
            re.sub(r"\[\d+\]", "[]", x["pointer"]) == "/validationTable[]/observation/path" for x in c["differences"])
        for c in cells),
    "cells": cells,
    "hostTerminalValidation": {
        "file": "x/teastore-offpath-v1/campaign-terminal-validation.json",
        "sha256": hashlib.sha256(host_path.read_bytes()).hexdigest(),
        "verdict": host.get("verdict"), "runCount": host.get("runCount"), "blockers": host.get("blockers"),
        "runReportVerdicts": sorted({r.get("verdict") for r in host.get("runReports", [])}),
        "runReportsPass": sum(r.get("verdict") == "pass" for r in host.get("runReports", [])),
    },
}
out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
print("cells", doc["cellsReplayed"], "pass", doc["cellsReplayPass"], "byteEqual", doc["cellsByteEqualToRetained"],
      "pathOnly", doc["cellsDifferingOnlyInObservationPath"], "campaignLevel", doc["campaignLevelReplay"]["verdict"])
