#!/usr/bin/env python3
"""F ablation (otel-offpath-f-nolag-v1) scorer: score_test_v3_5.main(argv) unchanged, under a RECORDED pin override.

    uv run python research/placement/test-f-nolag/score_nolag.py <v3.5 scoring readout of the ablation> \
        --ablation-placement-sha256 <64 hex> --placement research/placement/test-f-nolag/placement-nolag.json \
        --training-readout <ablation training readout.json> --test-blocks 4 5 --out research/placement/test-f-nolag/otel-nolag.json

WHY. The ablation (F without the kafkametrics receiver) is read by the frozen v3.5 chain on its own cells. score_test_v3_5.PINNED_PLACEMENTS
is empty (no ablation placement existed at the freeze, FREEZE_V35_20261015.md) and stays empty: no frozen file is edited. This wrapper imports
score_test_v3_5, sets PINNED_PLACEMENTS to {"otel": <the sha given by --ablation-placement-sha256>} for the duration of the one main() call, and
restores the original object afterwards (a process-local override; nothing is written to the scorer or to the registry). The same device as
research/placement/test-f-rep1/score_rep.py, which does it for F's replicate against score_test_v3_3.

REFUSES (before the scorer runs) unless: the given sha is 64 lower-case hex; the --placement file's sha256 equals it; the --placement file
resolves under research/placement/test-f-nolag/ (symlinks followed); the sha is not F's placement (ce6bfc1b...); the scorer's pin is still empty at
import (a pinned scorer is a deviation to record, not to override over); neither readout is a byte copy of F's committed readouts, and both are
readouts of the ablation epoch ONLY (v32.epochsRead names otel-offpath-f-nolag-v1 and nothing else: an F readout, an F-replicate readout or a
pooled one is refused whatever its bytes); the placement's input readout is not one of F's; the sidecar path does not exist. --allow-unpinned is
refused (the ablation is scored under the recorded override, never unpinned). Every other argument and check is the scorer's.

RECORD. The scorer writes <out>.json and <out>.md unedited. Beside them this script writes <out stem>.override.json: the override, the scorer's
untouched empty pin (before and after the call), F's pin in score_test_v3_3 (read, untouched), the reader and registry pins and the digests of the
files that carry them. Scope: instance.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PLACEMENT_DIR = (REPO / "research" / "placement" / "test-f-nolag").resolve()
sys.path.insert(0, str(REPO / "research" / "placement"))
import celf_v3_2 as c2  # noqa: E402
import celf_v3_3 as c3  # noqa: E402
import celf_v3_5 as c5  # noqa: E402
import score_test_v3_3 as s3  # noqa: E402  frozen; read for F's pin only, never edited
import score_test_v3_5 as s5  # noqa: E402  frozen; imported, never edited

VERSION = "score-nolag-f-nolag-v1"
FLAG = "--ablation-placement-sha256"
EPOCH = "otel-offpath-f-nolag-v1"
F_PLACEMENT_SHA256 = "ce6bfc1b9addbb1771b189c9330b1930f0d84c9890c1fd8d8e8cae0978d20a3d"    # research/placement/test-f/placement-f.json
F_READOUT_SHA256 = {                                                                        # F's committed readouts (49d0265, 044b210)
    "73e4f9f8295707a10dc80e64dcc4c0a0e411de60d9bc2eb49ee97581b61f221f": "F training readout",
    "ce996be9db5aca8e96a755429baec3277a324b0f68a3e84458277b99675b1db2": "F scoring readout",
}
_PIN_AT_IMPORT = dict(s5.PINNED_PLACEMENTS)


def refuse(msg):
    raise SystemExit("refusing: " + msg)


def split_argv(argv):
    """(sha, rest): `--ablation-placement-sha256 X` (or `=X`) removed from argv; rest goes to score_test_v3_5.main unchanged."""
    rest, sha, i = [], None, 0
    while i < len(argv):
        t = argv[i]
        if t == FLAG:
            if sha is not None or i + 1 >= len(argv):
                refuse("%s given twice or without a value" % FLAG)
            sha, i = argv[i + 1], i + 2
        elif t.startswith(FLAG + "="):
            if sha is not None:
                refuse("%s given twice" % FLAG)
            sha, i = t[len(FLAG) + 1:], i + 1
        else:
            rest.append(t)
            i += 1
    if sha is None:
        refuse("%s is required" % FLAG)
    return sha, rest


def parse_scorer_args(rest):
    """The scorer's own arguments, parsed here only to be checked (same options as score_test_v3_5.main; no abbreviations, strict)."""
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


def check_ablation_only(path, label):
    """The readout reads the ablation epoch and nothing else (v32.epochsRead keys == {EPOCH}); any other epoch, F's included, is refused."""
    try:
        J = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        refuse("%s %s is not readable JSON (%s)" % (label, path, exc))
    read = ((J.get("v32") or {}).get("epochsRead")) if isinstance(J, dict) else None
    if not isinstance(read, dict) or set(read) != {EPOCH}:
        refuse("the %s %s reads epoch(s) %s, not %s alone: an F, F-replicate or pooled readout is not the ablation's" % (
            label, path, sorted(read) if isinstance(read, dict) else read, EPOCH))
    return J


def check_inputs(sha, rest):
    """All refusals, before anything runs. Returns (placement Path, out Path, sidecar Path)."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        refuse("%s %r is not 64 lower-case hex" % (FLAG, sha))
    a = parse_scorer_args(rest)
    placement = Path(a.placement)
    resolved = placement.resolve()
    if not resolved.is_file():
        refuse("--placement %s is not a file" % placement)
    if PLACEMENT_DIR not in resolved.parents:
        refuse("--placement %s is not under %s" % (resolved, PLACEMENT_DIR.relative_to(REPO)))
    got = s5.sha256(resolved)
    if got != sha:
        refuse("sha256 of --placement is %s, not the given %s" % (got, sha))
    if sha == F_PLACEMENT_SHA256 or sha in s3.PINNED_PLACEMENTS.values():
        refuse("the placement is F's (%s...): the ablation's own placement is required" % F_PLACEMENT_SHA256[:8])
    if _PIN_AT_IMPORT:
        refuse("score_test_v3_5.PINNED_PLACEMENTS is %r, not empty: record that deviation first" % (_PIN_AT_IMPORT,))
    if a.allow_unpinned:
        refuse("--allow-unpinned: the ablation is scored under the recorded pin override, never unpinned")
    for p, label in ((a.training_readout, "training readout"), (a.readout, "scoring readout")):
        if not Path(p).is_file():
            refuse("%s %s is not a file" % (label, p))
        h = s5.sha256(p)
        if h in F_READOUT_SHA256:
            refuse("the %s %s is a byte copy of the %s: the ablation alone" % (label, p, F_READOUT_SHA256[h]))
        check_ablation_only(p, label)
    P = json.loads(resolved.read_text())
    inp = (P.get("inputs") or {}).get("readoutSha256") if isinstance(P, dict) else None
    if inp in F_READOUT_SHA256:
        refuse("the placement was solved on the %s: the ablation's own training readout is required" % F_READOUT_SHA256[inp])
    if inp != s5.sha256(a.training_readout):
        refuse("the placement's input readout sha256 (%s) is not the given --training-readout's" % inp)
    out = Path(a.out)
    if out.suffix != ".json":
        refuse("--out must end in .json")
    sidecar = out.with_name(out.stem + ".override.json")
    if sidecar.exists() or sidecar.is_symlink():
        refuse("to write into an existing path: %s" % sidecar)
    return resolved, out, sidecar


@contextlib.contextmanager
def pin_override(sha):
    """score_test_v3_5.PINNED_PLACEMENTS = {"otel": sha} inside the block; the ORIGINAL object is put back after, also on an error."""
    saved = s5.PINNED_PLACEMENTS
    s5.PINNED_PLACEMENTS = {"otel": sha}
    try:
        yield
    finally:
        s5.PINNED_PLACEMENTS = saved


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    sha, rest = split_argv(argv)
    placement, out, sidecar = check_inputs(sha, rest)
    pin_before, f_pin_before = dict(s5.PINNED_PLACEMENTS), dict(s3.PINNED_PLACEMENTS)
    with pin_override(sha):
        rc = s5.main(rest)
    pin_after, f_pin_after = dict(s5.PINNED_PLACEMENTS), dict(s3.PINNED_PLACEMENTS)
    if pin_after != pin_before or f_pin_after != f_pin_before:
        refuse("a scorer pin changed across the run (score_test_v3_5 %r -> %r; score_test_v3_3 %r -> %r)" % (
            pin_before, pin_after, f_pin_before, f_pin_after))
    rec = {
        "version": VERSION, "scope": "instance",
        "override": {"module": "score_test_v3_5.PINNED_PLACEMENTS", "system": "otel", "ablationPlacementSha256": sha,
                     "placement": str(placement.relative_to(REPO)), "placementSha256": s5.sha256(placement),
                     "scope": "this process, this one main() call"},
        "scorerPin": {"before": pin_before, "after": pin_after, "unchanged": pin_before == pin_after == {}},
        "fPin": {"module": "score_test_v3_3.PINNED_PLACEMENTS", "before": f_pin_before, "after": f_pin_after,
                 "recorded": {"otel": F_PLACEMENT_SHA256}, "unchanged": f_pin_before == f_pin_after == {"otel": F_PLACEMENT_SHA256},
                 "fPlacementFile": "research/placement/test-f/placement-f.json"},
        "readerAndRegistryPins": {
            "pinnedV35ReaderSha256": s5.PINNED_V35_SHA256, "pinnedParametersV35Sha256": s5.PINNED_PARAMETERS_V35_SHA256,
            "pinnedV33ReaderSha256": c3.PINNED_V33_SHA256, "pinnedParametersV33Sha256": c3.PINNED_PARAMETERS_V33_SHA256,
            "pinnedV32ReaderSha256": c2.PINNED_V32_SHA256, "pinnedParametersV32Sha256": c2.PINNED_PARAMETERS_V32_SHA256,
            "pinnedV31ReaderSha256": c2.PINNED_V31_SHA256, "pinnedCelfV3Sha256": c2.PINNED_CELF_SHA256},
        "fileDigests": {
            "research/placement/score_test_v3_5.py": s5.sha256(s5.__file__), "research/placement/celf_v3_5.py": s5.sha256(c5.__file__),
            "research/detection-time/sweep_analysis_v3_5.py": s5.sha256(c5.READER_V35),
            "research/protocol/parameters_v3_5.json": s5.sha256(c5.PARAMETERS_V35),
            "research/placement/score_test_v3_3.py": s5.sha256(s3.__file__), "research/placement/celf_v3_3.py": s5.sha256(c3.__file__),
            "research/detection-time/sweep_analysis_v3_3.py": s5.sha256(c3.READER_V33),
            "research/protocol/parameters_v3_3.json": s5.sha256(c3.PARAMETERS_V33),
            "research/protocol/parameters_v3_2.json": s5.sha256(c2.PARAMETERS_V32),
            "script": str(Path(__file__).resolve().relative_to(REPO)), "scriptSha256": s5.sha256(__file__)},
        "scorerArgv": rest, "python": sys.version,
    }
    with open(sidecar, "x", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, indent=1, sort_keys=True, allow_nan=False))
    print("wrote", sidecar)
    return rc


if __name__ == "__main__":
    sys.exit(main())
