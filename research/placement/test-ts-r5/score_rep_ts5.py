#!/usr/bin/env python3
"""R5, TeaStore same-plan repeat of R1 (DECLARATION_TEASTORE_R5.md, c61cde6): score_test_v3_6.main(argv) unchanged, under a RECORDED pin override.
The score_rep pattern (research/placement/test-f-rep1/score_rep.py, research/placement/test-f-seed2/score_rep_fs1.py) over the v3.6 scorer.

    uv run python research/placement/test-ts-r5/score_rep_ts5.py <R5 v3.6 scoring readout> \
        --replicate-placement-sha256 <64 hex> --setup-id <R5 setup ID> --placement research/placement/test-ts-r5/<R5 placement>.json \
        --training-readout <R5 v3.6 training readout> --test-blocks 4 5 --out research/placement/test-ts-r5/<new>.json

WHY. score_test_v3_6.PINNED_PLACEMENTS is R1's {"teastore": f7f5c04a...} (FREEZE_V36_20261015.md step 2, 174ba4b) and stays R1's: no frozen
file is edited. This wrapper imports score_test_v3_6, replaces PINNED_PLACEMENTS with {"teastore": <the sha given>} for the one main() call,
and puts the ORIGINAL object back afterwards, also on an error (a process-local override; nothing is written to the scorer or the registry).

REFUSES (before the scorer runs) unless: the given sha is 64 lower-case hex; --setup-id is 32 lower-case hex and none of the seven earlier srv5
setup IDs of this plan; the --placement file resolves under research/placement/test-ts-r5/ (symlinks followed) and its sha256 equals the given
sha; the sha is not R1's placement (f7f5c04a...); score_test_v3_6.PINNED_PLACEMENTS at import is exactly R1's {"teastore": f7f5c04a...} (a
changed frozen pin is a deviation to record, not to override over); the placement file is tracked by git and unchanged since its last commit
(the declaration: committed unedited before the scoring readout exists); --allow-unpinned is absent; neither readout is a byte copy of R1's
committed readouts; both readouts' campaignsRead[*].campaign is exactly ["tmp/teastore-offpath-evidence/r5-fetch/x/teastore-offpath-v1"];
tmp/teastore-offpath-evidence/r5-fetch/source.txt is exactly fb14srv5:<results>/<setup ID> and x/.packages/teastore-offpath-v1.json has
setupId == the setup ID; the sidecar path does not exist. Every other argument and check is the scorer's.

RECORD. The scorer writes <out>.json and <out>.md unedited. Beside them this script writes <out stem>.override.json: the override, R1's
untouched pin (before and after the call), the setup ID with source.txt and the package's setupId / frameworkCommit, the placement's commit,
the readouts' digests and campaignsRead, the reader and registry pins and the digests of the files carrying them. Scope: instance.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PLACEMENT_DIR = (REPO / "research" / "placement" / "test-ts-r5").resolve()
FETCH_DIR = REPO / "tmp" / "teastore-offpath-evidence" / "r5-fetch"      # tests rebind it to a synthetic fetch
sys.path.insert(0, str(REPO / "research" / "placement"))
import score_test_v3_6 as s6  # noqa: E402  frozen; imported, never edited

c2, c3, c6 = s6.c2, s6.c3, s6.c6
VERSION = "score-rep-ts-r5-v1"
FLAG = "--replicate-placement-sha256"
SETUP_FLAG = "--setup-id"
CAMPAIGNS_READ = ["tmp/teastore-offpath-evidence/r5-fetch/x/teastore-offpath-v1"]
HOST_RESULTS = "fb14srv5:/home/stig/.local/share/observability-placement/candidate-v4/teastore/results/"
R1_PLACEMENT_SHA256 = "f7f5c04a6422394d2fab11b97d8ef974643afec69b37688dc359f42e7a64e8de"   # research/placement/test-ts-placement/placement-rep3r1.json (694851c)
R1_READOUT_SHA256 = {                                                                       # R1's committed v3.6 readouts
    "b00bafd09c33c4b7ab673412bb04e288b637bf57fec59d85eadc53b2cced0ceb": "R1 training readout (readout-teastore-offpath-rep3r1-train-v3.6)",
    "b53521c9fd95dd91d8da31facdb659b0269611e6c26ef94801f0e8c3c8dffbb1": "R1 scoring readout (readout-teastore-offpath-rep3r1-score-v3.6)",
}
EARLIER_SETUP_IDS = {                                                                       # srv5 result dirs already carrying these 30 run IDs
    "c88ed29d91c6e8e889c0dd0f54157089": "off-path attempt 1 (stopped)",
    "def272fd4c9050f8226b88d756115e79": "off-path relaunch 1 (r1-fetch, not R1)",
    "887a7838e73019806ed39607be69992f": "replication 1 (stopped)",
    "d61bfea75d299b17c17104c2578bf7b8": "replication 1 relaunch (stopped)",
    "cbe9920a4b95f47d60054186641e754c": "replication 2",
    "416ea06f6b87f7ba0291fd2823c83d53": "R1 stopped attempt",
    "dcc8b664a9d0602e019a45322d93dbf1": "R1 (relaunch 1)",
    "b4bdd8e0df7bfc1eb7562462df181b64": "R5 stopped attempt (STOP_TEASTORE_R5_ATTEMPT1.md)",
}
R1_SCORER_SHA256 = "c2ab6de8d675a356fb7842cf653e8b07f2e386d37045af6205f3fa1ebb1d4218"        # score_test_v3_6.py after R1's pin (FREEZE_V36 step 2)
_R1_PIN_AT_IMPORT = dict(s6.PINNED_PLACEMENTS)


def refuse(msg):
    raise SystemExit("refusing: " + msg)


def split_argv(argv):
    """({flag: value}, rest): FLAG and SETUP_FLAG (`X v` or `X=v`) removed from argv; rest goes to score_test_v3_6.main unchanged."""
    got, rest, i = {}, [], 0
    while i < len(argv):
        t = argv[i]
        for f in (FLAG, SETUP_FLAG):
            if t == f or t.startswith(f + "="):
                if f in got:
                    refuse("%s given twice" % f)
                if t == f:
                    if i + 1 >= len(argv):
                        refuse("%s given without a value" % f)
                    got[f], i = argv[i + 1], i + 2
                else:
                    got[f], i = t[len(f) + 1:], i + 1
                break
        else:
            rest.append(t)
            i += 1
    for f in (FLAG, SETUP_FLAG):
        if f not in got:
            refuse("%s is required" % f)
    return got[FLAG], got[SETUP_FLAG], rest


def parse_scorer_args(rest):
    """The scorer's own arguments, parsed here only to be checked (same options as score_test_v3_6.main; no abbreviations, strict)."""
    ap = argparse.ArgumentParser(allow_abbrev=False, add_help=False)
    ap.add_argument("readout")
    ap.add_argument("--placement", required=True)
    ap.add_argument("--training-readout", required=True)
    ap.add_argument("--test-blocks", nargs="+", type=int, required=True)
    ap.add_argument("--allow-unpinned", action="store_true")
    ap.add_argument("--out", required=True)
    try:
        return ap.parse_args(rest)
    except SystemExit:
        refuse("the scorer's arguments are not readout --placement --training-readout --test-blocks --out [--allow-unpinned]")


def _git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)


def placement_commit(resolved):
    """The last commit of the placement file; refused if untracked or if the file differs from HEAD's blob."""
    rel = str(resolved.relative_to(REPO))
    if _git("ls-files", "--error-unmatch", "--", rel).returncode != 0:
        refuse("--placement %s is not tracked by git: commit it unedited before scoring" % rel)
    head = _git("rev-parse", "HEAD:" + rel)
    work = _git("hash-object", "--", rel)
    if head.returncode != 0 or work.returncode != 0 or head.stdout.strip() != work.stdout.strip():
        refuse("--placement %s differs from its committed blob (or is not in HEAD)" % rel)
    c = _git("log", "-1", "--format=%H", "--", rel)
    if c.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", c.stdout.strip()):
        refuse("no commit found for --placement %s" % rel)
    return c.stdout.strip()


def check_readout_identity(p, label):
    """Not a byte copy of R1's readouts; campaignsRead[*].campaign exactly CAMPAIGNS_READ. Returns its record."""
    if not Path(p).is_file():
        refuse("%s %s is not a file" % (label, p))
    h = s6.sha256(p)
    if h in R1_READOUT_SHA256:
        refuse("the %s %s is a byte copy of the %s: R5 alone" % (label, p, R1_READOUT_SHA256[h]))
    try:
        cr = json.loads(Path(p).read_text()).get("campaignsRead")
    except (ValueError, AttributeError):
        refuse("the %s %s is not a JSON object" % (label, p))
    camps = [c.get("campaign") if isinstance(c, dict) else None for c in cr] if isinstance(cr, list) else None
    if camps != CAMPAIGNS_READ:
        refuse("the %s %s read campaigns %r, not exactly %r" % (label, p, camps, CAMPAIGNS_READ))
    return {"path": str(p), "sha256": h, "campaignsRead": camps}


def check_fetch(setup_id):
    """source.txt names the setup ID; the fetched package's setupId equals it. Returns its record."""
    src, pkg = FETCH_DIR / "source.txt", FETCH_DIR / "x" / ".packages" / "teastore-offpath-v1.json"
    if not src.is_file():
        refuse("%s not found" % src)
    want = HOST_RESULTS + setup_id
    got = src.read_text().strip()
    if got != want:
        refuse("%s is %r, not %r" % (src, got, want))
    if not pkg.is_file():
        refuse("%s not found" % pkg)
    try:
        P = json.loads(pkg.read_text())
    except ValueError:
        refuse("%s is not JSON" % pkg)
    if not isinstance(P, dict) or P.get("setupId") != setup_id:
        refuse("%s setupId is %r, not %s" % (pkg, P.get("setupId") if isinstance(P, dict) else None, setup_id))
    return {"sourceTxt": got, "package": str(pkg.relative_to(REPO)) if REPO in pkg.parents else str(pkg),
            "packageSha256": s6.sha256(pkg), "packageSetupId": P.get("setupId"), "packageFrameworkCommit": P.get("frameworkCommit")}


def check_inputs(sha, setup_id, rest):
    """All refusals, before anything runs. Returns (placement Path, out Path, sidecar Path, facts dict)."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        refuse("%s %r is not 64 lower-case hex" % (FLAG, sha))
    if not re.fullmatch(r"[0-9a-f]{32}", setup_id):
        refuse("%s %r is not 32 lower-case hex" % (SETUP_FLAG, setup_id))
    if setup_id in EARLIER_SETUP_IDS:
        refuse("%s %s is an earlier run's (%s): R5's own setup ID is required" % (SETUP_FLAG, setup_id, EARLIER_SETUP_IDS[setup_id]))
    a = parse_scorer_args(rest)
    placement = Path(a.placement)
    resolved = placement.resolve()
    if not resolved.is_file():
        refuse("--placement %s is not a file" % placement)
    if PLACEMENT_DIR not in resolved.parents:
        refuse("--placement %s is not under %s" % (resolved, PLACEMENT_DIR.relative_to(REPO)))
    got = s6.sha256(resolved)
    if got != sha:
        refuse("sha256 of --placement is %s, not the given %s" % (got, sha))
    if sha == R1_PLACEMENT_SHA256 or sha in _R1_PIN_AT_IMPORT.values():
        refuse("the placement is R1's (%s...): R5's own placement is required" % R1_PLACEMENT_SHA256[:8])
    if _R1_PIN_AT_IMPORT != {"teastore": R1_PLACEMENT_SHA256}:
        refuse("score_test_v3_6.PINNED_PLACEMENTS at import is %r, not R1's {'teastore': %s...}: record that deviation first"
               % (_R1_PIN_AT_IMPORT, R1_PLACEMENT_SHA256[:8]))
    if a.allow_unpinned:
        refuse("--allow-unpinned: R5 is scored under the recorded pin override, never unpinned")
    readouts = {"training": check_readout_identity(a.training_readout, "training readout"),
                "scoring": check_readout_identity(a.readout, "scoring readout")}
    fetch = check_fetch(setup_id)
    out = Path(a.out)
    if out.suffix != ".json":
        refuse("--out must end in .json")
    sidecar = out.with_name(out.stem + ".override.json")
    if sidecar.exists() or sidecar.is_symlink():
        refuse("to write into an existing path: %s" % sidecar)
    commit = placement_commit(resolved)
    return resolved, out, sidecar, {"readouts": readouts, "fetch": fetch, "placementCommit": commit}


@contextlib.contextmanager
def pin_override(sha):
    """score_test_v3_6.PINNED_PLACEMENTS = {"teastore": sha} inside the block; the ORIGINAL object is put back after, also on an error."""
    saved = s6.PINNED_PLACEMENTS
    s6.PINNED_PLACEMENTS = {"teastore": sha}
    try:
        yield
    finally:
        s6.PINNED_PLACEMENTS = saved


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    sha, setup_id, rest = split_argv(argv)
    placement, out, sidecar, facts = check_inputs(sha, setup_id, rest)
    r1_pin_before = dict(s6.PINNED_PLACEMENTS)
    with pin_override(sha):
        rc = s6.main(rest)
    r1_pin_after = dict(s6.PINNED_PLACEMENTS)
    if r1_pin_after != r1_pin_before:
        refuse("score_test_v3_6.PINNED_PLACEMENTS changed across the run (%r -> %r)" % (r1_pin_before, r1_pin_after))
    rec = {
        "version": VERSION, "scope": "instance",
        "override": {"module": "score_test_v3_6.PINNED_PLACEMENTS", "system": "teastore", "replicatePlacementSha256": sha,
                     "placement": str(placement.relative_to(REPO)), "placementSha256": s6.sha256(placement),
                     "placementCommit": facts["placementCommit"], "scope": "this process, this one main() call"},
        "setupId": setup_id, "fetch": facts["fetch"], "readouts": facts["readouts"],
        "r1Pin": {"before": r1_pin_before, "after": r1_pin_after, "recorded": {"teastore": R1_PLACEMENT_SHA256},
                  "unchanged": r1_pin_before == r1_pin_after == {"teastore": R1_PLACEMENT_SHA256},
                  "r1PlacementFile": "research/placement/test-ts-placement/placement-rep3r1.json"},
        "readerAndRegistryPins": {
            "pinnedV36ReaderSha256": s6.PINNED_V36_SHA256, "pinnedParametersV36Sha256": s6.PINNED_PARAMETERS_V36_SHA256,
            "pinnedV33ReaderSha256": c3.PINNED_V33_SHA256, "pinnedParametersV33Sha256": c3.PINNED_PARAMETERS_V33_SHA256,
            "pinnedV32ReaderSha256": c2.PINNED_V32_SHA256, "pinnedParametersV32Sha256": c2.PINNED_PARAMETERS_V32_SHA256,
            "pinnedV31ReaderSha256": c2.PINNED_V31_SHA256, "pinnedCelfV3Sha256": c2.PINNED_CELF_SHA256},
        "fileDigests": {
            "research/placement/score_test_v3_6.py": s6.sha256(s6.__file__), "scoreTestV36RecordedAfterR1Pin": R1_SCORER_SHA256,
            "research/placement/celf_v3_6.py": s6.sha256(c6.__file__), "research/detection-time/sweep_analysis_v3_6.py": s6.sha256(c6.READER_V36),
            "research/protocol/parameters_v3_6.json": s6.sha256(c6.PARAMETERS_V36),
            "research/protocol/parameters_v3_3.json": s6.sha256(c3.PARAMETERS_V33), "research/protocol/parameters_v3_2.json": s6.sha256(c2.PARAMETERS_V32),
            "script": str(Path(__file__).resolve().relative_to(REPO)), "scriptSha256": s6.sha256(__file__)},
        "scorerArgv": rest, "python": sys.version,
    }
    with open(sidecar, "x", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, indent=1, sort_keys=True, allow_nan=False))
    print("wrote", sidecar)
    return rc


if __name__ == "__main__":
    sys.exit(main())
