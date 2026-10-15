#!/usr/bin/env python3
"""Generate the synthetic TeaStore cells that test analysis v2.2's TeaStore reader, with the TeaStore harness's own
fixture writer: tests/test_teastore_traffic_sweep.py `make_sweep_run` at harness commit 91c4967 (the sweep's compiled
cell timing, the real witness and native-token extractors, kieker.build_fixture and the spool replay, the
intervention receipt the producer writes). Not a test and not evidence; regenerate, never hand-edit.

    W=../observability-placement-runtime-teastore-protocol
    $W/.venv/bin/python -B tests/fixtures/sweep_v22/generate_teastore.py $W <scratch dir>

Writes tests/fixtures/sweep_v22/teastore/campaign/runs/<regime>/b01-<OO>-full (no-fault, auth-freeze and
persistence-cpu-throttle at 0.2 journeys/s) and tests/fixtures/sweep_v22/teastore/MANIFEST.json. In the auth-freeze
cell every journey that starts inside the hold times out at the client (15 s) and logs no witness or bridge line
(make_sweep_run's `failed`); each cell is then validated by the harness's validator (validate_run, as the
producer does) and its report written as candidate-validation.json; everything else is the harness fixture's own
content. The harness code is `git archive` of the
pinned commit (tests/fixtures/sweep_v22/_pinned.py), not the worktree's HEAD.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

PINNED = "91c4967"
HERE = Path(__file__).resolve().parent
OUT = HERE / "teastore"
CELLS = (("no-fault-cost", 0.2), ("auth-freeze-effect", 0.2), ("persistence-cpu-throttle-effect", 0.2))


class Factory:
    def __init__(self, base):
        self.base = Path(base)

    def mktemp(self, name):
        return Path(tempfile.mkdtemp(prefix=name + "-", dir=self.base))


def main(argv):
    worktree, scratch = Path(argv[1]).resolve(), Path(argv[2]).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(HERE))
    from _pinned import pinned_tree                     # noqa: E402
    source, head = pinned_tree(worktree, PINNED, scratch)
    sys.path.insert(0, str(source / "tests"))
    import test_teastore_traffic_sweep as H          # noqa: E402  the harness's own fixtures
    tree = H.tree.__wrapped__(Factory(scratch))
    if OUT.exists():
        shutil.rmtree(OUT)
    camp = OUT / "campaign"
    written = []
    for regime, rate in CELLS:
        cell = H._cell(regime, rate)
        d = camp / "runs" / regime / ("b%02d-%02d-full" % (cell["runKey"]["block"], cell["ordinalPosition"]))
        timing = cell["timing"]
        failed = {}
        if timing["fault"] == "auth-freeze":
            onset, hold = timing["faultOnsetSeconds"], timing["faultHoldSeconds"]
            failed = {i: False for i in range(timing["offered"]) if onset <= i / rate <= onset + hold}
        H.make_sweep_run(tree, d, cell, failed=failed)
        # the producer's next step (performance_campaign.py:3672-3677): the cell validator's report
        report = tree["validator"].validate_run(d, expected={**cell["runKey"], "runId": cell["runId"]})
        if report.get("verdict") != "pass" or report.get("cellStatus") != "valid":
            raise SystemExit("the harness validator refused %s: %s" % (d, report.get("cellStatus")))
        (d / "candidate-validation.json").write_text(json.dumps(report, allow_nan=False, indent=2, sort_keys=True)
                                                     + "\n", encoding="utf-8")
        written.append({"cell": d.relative_to(OUT).as_posix(), "runId": cell["runId"], "regime": regime,
                        "rate": rate, "timedOutJourneys": sorted(failed)})
    files = sorted(p for p in camp.rglob("*") if p.is_file())
    manifest = {"harness": "observability-placement-runtime-teastore-protocol", "harnessCommit": head,
                "writer": "tests/test_teastore_traffic_sweep.py make_sweep_run (harness)",
                "generator": "tests/fixtures/sweep_v22/generate_teastore.py", "cells": written,
                "files": {p.relative_to(OUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print("wrote %d files under %s" % (len(files), OUT))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    sys.exit(main(sys.argv))
