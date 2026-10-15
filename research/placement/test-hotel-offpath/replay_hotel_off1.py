"""Offline terminal replay of the Hotel off-path campaign hotel-offpath-v1 (read-only on harness and evidence).

Thin adaptation of tmp/traffic-sweep-decision25-replay-20261003/replay.py (mode "old"; that script derives the remote root from the
directory name, which here is `x`, so the remote root is taken from the retained runtime-admission.json instead). No harness edit.

Usage (interpreter /usr/bin/python3 3.9, -I -B, Apple bytecode cache cleared beforehand):
  /usr/bin/python3 -I -B replay_hotel_off1.py <hotel worktree at 9ad0b98> <fetch dir x> <NEW output json>
Per cell: the harness's own terminal validate_cell with the retained cell-contract.json, compared byte-for-byte (canonical bytes) with the
retained cell-terminal.json. Campaign level: terminal validate_campaign over the retained contracts and runtime-admission.json, compared
with the retained campaign-terminal.json; its outcome is recorded whatever it is. The host's terminal fields are recorded beside.
"""
import hashlib, importlib.util, json, subprocess, sys, traceback
from pathlib import Path

code_root, fetch, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3])
assert not out.exists(), "new evidence never overwrites old"
HARNESS = "9ad0b98194f715b921aba187df5ed511082f1f7b"
head = subprocess.check_output(["git", "-C", str(code_root), "rev-parse", "HEAD"]).decode().strip()
assert head == HARNESS, head
assert not subprocess.check_output(["git", "-C", str(code_root), "status", "--porcelain", "--untracked-files=no"]).decode().strip()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


terminal = load("replay_terminal", code_root / "modules/hotel-reservation/validation/candidate_terminal.py")
admission = json.loads((fetch / "runtime-admission.json").read_text())
assert admission["bindings"]["frameworkCommit"] == HARNESS
remote = Path(admission["bindings"]["artifactRoot"])
terminal.configure_path_remap(remote, fetch)

cell_dirs = sorted(p.parent for p in fetch.glob("runs/**/attempt-01/cell-contract.json"))
contracts = []
cells = []
for root in cell_dirs:
    contract = json.loads((root / "cell-contract.json").read_text())
    contracts.append(contract)
    row = {"ordinal": contract["ordinal"], "runId": contract["runId"], "path": str(root.relative_to(fetch)),
           "sealedOnHost": (root / "cell-terminal.json").is_file()}
    try:
        result = terminal.validate_cell(root, contract)
        row["valid"] = result["candidateCellValid"] is True
        row["terminalMatchesRetained"] = (
            terminal.canonical_bytes(result)
            == terminal.canonical_bytes(json.loads((root / "cell-terminal.json").read_text())))
    except Exception as exc:  # noqa: BLE001 - reported per cell
        row["valid"] = False
        row["error"] = "%s: %s" % (type(exc).__name__, exc)
        row["trace"] = traceback.format_exc().splitlines()[-3:]
    cells.append(row)
contracts.sort(key=lambda c: c["ordinal"])
cells.sort(key=lambda r: r["ordinal"])

host_path = fetch / "campaign-terminal.json"
host = json.loads(host_path.read_text())
campaign = {}
try:
    replayed = terminal.validate_campaign(fetch, contracts, admission)
    campaign = {"outcome": "returned", "candidateCampaignValid": replayed.get("candidateCampaignValid"),
                "validCellCount": replayed.get("validCellCount"),
                "byteEqualToHostTerminal": terminal.canonical_bytes(replayed) == terminal.canonical_bytes(host),
                "canonicalSha256": replayed.get("canonicalSha256"), "manifest": replayed.get("manifest")}
except Exception as exc:  # noqa: BLE001 - recorded
    campaign = {"outcome": "raised", "error": "%s: %s" % (type(exc).__name__, exc),
                "trace": traceback.format_exc().splitlines()[-3:]}

doc = {
    "kind": "hotel-offpath-per-cell-and-campaign-terminal-replay",
    "campaignId": admission["bindings"]["campaignId"], "frameworkCommit": head,
    "studyEpoch": admission["bindings"]["studyEpoch"],
    "compiledPlanCanonicalSha256": admission["bindings"]["compiledPlanCanonicalSha256"],
    "interpreter": sys.version, "remoteRoot": str(remote), "fetchDirectory": str(fetch),
    "cellsFound": len(cells),
    "cellsReplayValid": sum(c["valid"] is True for c in cells),
    "cellsTerminalMatchRetained": sum(c.get("terminalMatchesRetained") is True for c in cells),
    "cellsSealedOnHost": sum(c["sealedOnHost"] for c in cells),
    "campaignLevelReplay": campaign,
    "hostTerminal": {
        "file": "campaign-terminal.json", "sha256": hashlib.sha256(host_path.read_bytes()).hexdigest(),
        "canonicalSha256": host.get("canonicalSha256"),
        "candidateCampaignValid": host.get("candidateCampaignValid"), "cellCount": host.get("cellCount"),
        "validCellCount": host.get("validCellCount"), "manifest": host.get("manifest"),
        "runIdsCanonicalSha256": host.get("runIdsCanonicalSha256"),
    },
    "cells": cells,
}
out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
print("cells", doc["cellsFound"], "valid", doc["cellsReplayValid"], "terminalMatch", doc["cellsTerminalMatchRetained"],
      "campaign", campaign.get("outcome"), campaign.get("candidateCampaignValid"), campaign.get("byteEqualToHostTerminal"), campaign.get("error"))
