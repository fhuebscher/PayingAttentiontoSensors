#!/usr/bin/env python3
"""R6, campaign F's design on new cells (attempt 8) scorer: a copy of test-f-seed2/score_rep_fs1.py (DECLARATION_OTEL_R6.md, 0ee8d62, analysis
item 1), changed in PLACEMENT_DIR (test-f-r6), VERSION (score-rep-f-r6-v1) and the refusal lists, extended by R2's placement (633b89f1...) and
R2's readouts (bcc4cd34... training, 6c5f6bc1... scoring); plus the two readout checks the declaration names for both readouts (campaignsRead
exactly [tmp/otel-f-evidence/r6-fetch/x]; the scoring readout's calibration byte-equal to the training readout's), made here before the scorer
runs (the scorer's own SAME_CALIBRATION compares parsed values; this compares canonical JSON bytes). score_test_v3_3.main(argv) unchanged,
under a RECORDED pin override. (Below, "the replicate" is R6; the text after this paragraph is score_rep_fs1's, paths updated.)

    uv run python research/placement/test-f-r6/score_rep_r6.py <v3.3 scoring readout of R6> \
        --replicate-placement-sha256 <64 hex> --placement research/placement/test-f-r6/placement-r6.json \
        --training-readout <R6 training readout.json> --test-blocks 4 5 --out research/placement/test-f-r6/otel-r6.json

WHY. DECLARATION_F_OTEL_REP1.md (d0ef902) runs the frozen v3.3 chain on the replicate alone. score_test_v3_3.PINNED_PLACEMENTS["otel"]
is F's training placement (ce6bfc1b...) and stays F's: no frozen file is edited. This wrapper imports score_test_v3_3, replaces
PINNED_PLACEMENTS with {"otel": <the sha given by --replicate-placement-sha256>} for the duration of the one main() call, and restores the
original object afterwards (a process-local override; nothing is written to the scorer or to the registry).

REFUSES (before the scorer runs) unless: the given sha is 64 lower-case hex; the --placement file's sha256 equals it; the --placement file
resolves under research/placement/test-f-r6/ (symlinks followed); the sha is not F's placement (ce6bfc1b...) nor the rerun's, the
ablation's or R2's; score_test_v3_3's own pin is still F's (a changed frozen pin is a deviation to record, not to override over); neither
the scoring readout nor the training readout is a byte copy of F's, the rerun's, the ablation's or R2's committed readouts; each readout's
campaignsRead[*].campaign is exactly [tmp/otel-f-evidence/r6-fetch/x]; the scoring readout's calibration serialises (json, sort_keys) to
the same bytes as the training readout's; the sidecar path does not exist. --allow-unpinned is refused (the replicate is scored under the recorded override, never unpinned). Every other argument and check is the scorer's.

RECORD. The scorer writes <out>.json and <out>.md unedited. Beside them this script writes <out stem>.override.json: the override, F's
untouched pin (before, during-call-independent and after the call), the reader and registry pins and the digests of the files that
carry them. Scope: instance.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PLACEMENT_DIR = (REPO / "research" / "placement" / "test-f-r6").resolve()
R6_FETCH = "tmp/otel-f-evidence/r6-fetch/x"                                                   # DECLARATION_OTEL_R6.md: campaignsRead, exactly
sys.path.insert(0, str(REPO / "research" / "placement"))
import celf_v3_2 as c2  # noqa: E402
import celf_v3_3 as c3  # noqa: E402
import score_test_v3_3 as s3  # noqa: E402  frozen; imported, never edited

VERSION = "score-rep-f-r6-v1"
FLAG = "--replicate-placement-sha256"
F_PLACEMENT_SHA256 = "ce6bfc1b9addbb1771b189c9330b1930f0d84c9890c1fd8d8e8cae0978d20a3d"    # research/placement/test-f/placement-f.json
F_READOUT_SHA256 = {                                                                        # F's committed readouts (49d0265, 044b210)
    "73e4f9f8295707a10dc80e64dcc4c0a0e411de60d9bc2eb49ee97581b61f221f": "F training readout",
    "ce996be9db5aca8e96a755429baec3277a324b0f68a3e84458277b99675b1db2": "F scoring readout",
    "f56feb556d319443eeaaa398a5e1a998a61de7cabb62702a2278780e1c4a7f11": "F rerun (attempt 3) training readout",
    "642d2c9de033c4234881de3792bfb556875cf1506bf0c91a3e0239b214c30a97": "F rerun (attempt 3) scoring readout",
    "e4f81b81f85f2655342cf561595fb6d3736f0714ead060073bfeb9b1c15ef558": "ablation training readout",
    "ad54cdbc7c7ab894a6bf57c99f442dcbb0599a756c105ee43143f0e3c78df2df": "ablation scoring readout",
    "bcc4cd34901011b25c4c489ddfd9ef67111950ba0f9fd5b430b3ce3f36d95300": "R2 (new seed, attempt 4) training readout",   # readout-otel-fs1-train-v3.3
    "6c5f6bc19412300691e451c17d7f5f861717e0f2953e792437d93ce0755b64a3": "R2 (new seed, attempt 4) scoring readout",    # readout-otel-fs1-score-v3.3
}
OTHER_PLACEMENT_SHA256 = {"674580e08353e667ea32d587091fc38327db6d68e1d3f2142fdd94c9e433b606": "F rerun (attempt 3) placement", "8263bfd0b16659e82c8d43f9835772c4f279918262b84a37f1c0e5d3e5425085": "ablation placement",
                          "633b89f1beea3b6896488aa41de82983ac84c80d2230a768938190f0d181e560": "R2 (new seed, attempt 4) placement"}   # test-f-seed2/placement-fs1.json
F_SCORER_SHA256 = "704cf341ae23e09a123915e14b4546dc1e3b02b3cf7bf2fa4808059acbd2e442"        # score_test_v3_3.py after F's pin (FREEZE_V33 step 2)
_F_PIN_AT_IMPORT = dict(s3.PINNED_PLACEMENTS)


def refuse(msg):
    raise SystemExit("refusing: " + msg)


def split_argv(argv):
    """(sha, rest): `--replicate-placement-sha256 X` (or `=X`) removed from argv; rest goes to score_test_v3_3.main unchanged."""
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
    """The scorer's own arguments, parsed here only to be checked (same options as score_test_v3_3.main; no abbreviations, strict)."""
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


def check_inputs(sha, rest):
    """All refusals, before anything runs. Returns (placement Path, out Path, sidecar Path, readout-check record)."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        refuse("%s %r is not 64 lower-case hex" % (FLAG, sha))
    a = parse_scorer_args(rest)
    placement = Path(a.placement)
    resolved = placement.resolve()
    if not resolved.is_file():
        refuse("--placement %s is not a file" % placement)
    if PLACEMENT_DIR not in resolved.parents:
        refuse("--placement %s is not under %s" % (resolved, PLACEMENT_DIR.relative_to(REPO)))
    got = s3.sha256(resolved)
    if got != sha:
        refuse("sha256 of --placement is %s, not the given %s" % (got, sha))
    if sha == F_PLACEMENT_SHA256 or sha in _F_PIN_AT_IMPORT.values():
        refuse("the placement is F's (%s...): the replicate's own placement is required" % F_PLACEMENT_SHA256[:8])
    if sha in OTHER_PLACEMENT_SHA256:
        refuse("the placement is the %s: R6's own placement is required" % OTHER_PLACEMENT_SHA256[sha])
    if _F_PIN_AT_IMPORT != {"otel": F_PLACEMENT_SHA256}:
        refuse("score_test_v3_3.PINNED_PLACEMENTS is %r, not F's {'otel': %s...}: record that deviation first" % (_F_PIN_AT_IMPORT, F_PLACEMENT_SHA256[:8]))
    if a.allow_unpinned:
        refuse("--allow-unpinned: the replicate is scored under the recorded pin override, never unpinned")
    for p, label in ((a.training_readout, "training readout"), (a.readout, "scoring readout")):
        if not Path(p).is_file():
            refuse("%s %s is not a file" % (label, p))
        h = s3.sha256(p)
        if h in F_READOUT_SHA256:
            refuse("the %s %s is a byte copy of the %s: the replicate alone" % (label, p, F_READOUT_SHA256[h]))
    cal = {}
    for p, label in ((a.training_readout, "training readout"), (a.readout, "scoring readout")):
        try:
            J = json.loads(Path(p).read_text(encoding="utf-8"))
        except ValueError as e:
            refuse("the %s %s is not JSON (%s)" % (label, p, e))
        got_cr = [c.get("campaign") if isinstance(c, dict) else c for c in (J.get("campaignsRead") if isinstance(J, dict) else None) or []]
        if got_cr != [R6_FETCH]:
            refuse("the %s %s has campaignsRead %r, not exactly [%r]" % (label, p, got_cr, R6_FETCH))
        if "calibration" not in J:
            refuse("the %s %s has no calibration block" % (label, p))
        cal[label] = json.dumps(J["calibration"], sort_keys=True, allow_nan=True).encode("utf-8")
    if cal["scoring readout"] != cal["training readout"]:
        refuse("the scoring readout's calibration is not byte-equal (json, sort_keys) to the training readout's")
    out = Path(a.out)
    if out.suffix != ".json":
        refuse("--out must end in .json")
    sidecar = out.with_name(out.stem + ".override.json")
    if sidecar.exists() or sidecar.is_symlink():
        refuse("to write into an existing path: %s" % sidecar)
    rc = {"campaignsRead": [R6_FETCH], "calibrationByteEqual": True,
          "calibrationSha256": hashlib.sha256(cal["training readout"]).hexdigest(), "encoding": "json.dumps(sort_keys=True)"}
    return resolved, out, sidecar, rc


@contextlib.contextmanager
def pin_override(sha):
    """score_test_v3_3.PINNED_PLACEMENTS = {"otel": sha} inside the block; the ORIGINAL object is put back after, also on an error."""
    saved = s3.PINNED_PLACEMENTS
    s3.PINNED_PLACEMENTS = {"otel": sha}
    try:
        yield
    finally:
        s3.PINNED_PLACEMENTS = saved


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    sha, rest = split_argv(argv)
    placement, out, sidecar, readout_checks = check_inputs(sha, rest)
    f_pin_before = dict(s3.PINNED_PLACEMENTS)
    with pin_override(sha):
        rc = s3.main(rest)
    f_pin_after = dict(s3.PINNED_PLACEMENTS)
    if f_pin_after != f_pin_before:
        refuse("score_test_v3_3.PINNED_PLACEMENTS changed across the run (%r -> %r)" % (f_pin_before, f_pin_after))
    rec = {
        "version": VERSION, "scope": "instance",
        "override": {"module": "score_test_v3_3.PINNED_PLACEMENTS", "system": "otel", "replicatePlacementSha256": sha,
                     "placement": str(placement.relative_to(REPO)), "placementSha256": s3.sha256(placement), "scope": "this process, this one main() call"},
        "fPin": {"before": f_pin_before, "after": f_pin_after, "recorded": {"otel": F_PLACEMENT_SHA256},
                 "unchanged": f_pin_before == f_pin_after == {"otel": F_PLACEMENT_SHA256}, "fPlacementFile": "research/placement/test-f/placement-f.json"},
        "readerAndRegistryPins": {
            "pinnedV33ReaderSha256": s3.PINNED_V33_SHA256, "pinnedParametersV33Sha256": s3.PINNED_PARAMETERS_V33_SHA256,
            "pinnedV32ReaderSha256": c2.PINNED_V32_SHA256, "pinnedParametersV32Sha256": c2.PINNED_PARAMETERS_V32_SHA256,
            "pinnedV31ReaderSha256": c2.PINNED_V31_SHA256, "pinnedCelfV3Sha256": c2.PINNED_CELF_SHA256},
        "fileDigests": {
            "research/placement/score_test_v3_3.py": s3.sha256(s3.__file__), "scoreTestV33RecordedAfterFPin": F_SCORER_SHA256,
            "research/placement/celf_v3_3.py": s3.sha256(c3.__file__), "research/detection-time/sweep_analysis_v3_3.py": s3.sha256(c3.READER_V33),
            "research/protocol/parameters_v3_3.json": s3.sha256(c3.PARAMETERS_V33), "research/protocol/parameters_v3_2.json": s3.sha256(c2.PARAMETERS_V32),
            "script": str(Path(__file__).resolve().relative_to(REPO)), "scriptSha256": s3.sha256(__file__)},
        "readoutChecks": readout_checks, "scorerArgv": rest, "python": sys.version,
    }
    with open(sidecar, "x", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, indent=1, sort_keys=True, allow_nan=False))
    print("wrote", sidecar)
    return rc


if __name__ == "__main__":
    sys.exit(main())
