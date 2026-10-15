"""Per-cell offline terminal replay of R5 (relaunch r5r1 of the same-plan repeat of R1; barrier-fixed harness 04254228) (read-only on harness and evidence).

Usage (interpreter /usr/bin/python3 3.9, the host's; fresh PYTHONPYCACHEPREFIX, PYTHONDONTWRITEBYTECODE=1):
  python3 replay_ts_r5.py <teastore worktree> <fetch dir (r5-fetch)> <R5 relaunch setup ID, 32 hex> <new output json>
Runs the harness's own validate_run on each cell and compares with the retained candidate-validation.json.
The campaign-level replay_fetched_campaign is also called once and its outcome recorded (it needs the evidence at
the host's absolute path, so it is expected to be blocked by host-path embedding on a laptop copy).
"""
import hashlib, importlib.util, json, re, sys
from pathlib import Path

W = Path(sys.argv[1]); fetch = Path(sys.argv[2]); SETUP_ID = sys.argv[3]; out = Path(sys.argv[4])
# the setup ID is an argument (R5's relaunch ID is printed only at its GATE-RUN line) and is bound three ways below: format, the earlier-ID list, and the package.
EARLIER = {"c88ed29d91c6e8e889c0dd0f54157089", "def272fd4c9050f8226b88d756115e79", "887a7838e73019806ed39607be69992f", "d61bfea75d299b17c17104c2578bf7b8",
           "cbe9920a4b95f47d60054186641e754c", "dcc8b664a9d0602e019a45322d93dbf1", "416ea06f6b87f7ba0291fd2823c83d53", "b4bdd8e0df7bfc1eb7562462df181b64"}
assert re.fullmatch(r"[0-9a-f]{32}", SETUP_ID), "bad setup ID"
assert SETUP_ID not in EARLIER, "an earlier run's setup ID (incl. R5 attempt 1, b4bdd8e0..., stopped)"
assert not out.exists(), "new evidence never overwrites old"
sys.path.insert(0, str(W / "src"))
spec = importlib.util.spec_from_file_location("ts_transport", W / "modules/teastore/execution/candidate_transport.py")
m = importlib.util.module_from_spec(spec); sys.modules["ts_transport"] = m; spec.loader.exec_module(m)
root = fetch / "x/teastore-offpath-v1"
pkg = json.loads((fetch / "x/.packages/teastore-offpath-v1.json").read_text())
camp = json.loads((root / "campaign.json").read_text())
# copy of test-ts-placement/replay_ts_rep3r1.py for R5: the labels differ and the setup pin is the argument (no harness edit)
HARNESS = "04254228aba90566dfeca603dfcc7b05b7d8d2e3"
assert pkg["frameworkCommit"] == HARNESS, pkg["frameworkCommit"]
assert pkg["setupId"] == SETUP_ID, pkg["setupId"]
assert (fetch / "source.txt").read_text().strip().endswith("/" + SETUP_ID), (fetch / "source.txt").read_text()
import subprocess
assert subprocess.check_output(["git", "-C", str(W), "rev-parse", "HEAD"]).decode().strip() == HARNESS
assert not subprocess.check_output(["git", "-C", str(W), "status", "--porcelain", "--untracked-files=no"]).decode().strip()
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
    "kind": "teastore-offpath-r5-per-cell-terminal-replay",
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
