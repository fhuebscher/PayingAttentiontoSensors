"""Regenerate research/placement/declared/otel.effort.json from its declared inputs.

The committed file was written on 2026-10-12 by an inline script that was never saved; this is its replacement.
Usage:  uv run python -I research/placement/declared/build_otel_effort.py --out <NEW path>
The output path must not exist (exclusive create).  Nothing is written next to the inputs.

What is computed from the inputs: the id union (readout calibration keys + placement primary groundSet), family and
service of each id (parsed from the id), the rule per id, posture membership (both catalogs), the catalog line of the
service row (`sourceLine`), every count, the input digests, and the posture-step cost numbers (parsed from
research/otel-postures/RESULT.md).  What is NOT computed: the rule texts, their tiers and citations, and the prose notes.
Those are the coordinator's rules as recorded in the committed file and in OTEL_EFFORT.md; they live in the constants
below, copied verbatim.  Changing one is a rule change and belongs to the user, not to this script.

`generatedAt` is the date of the run (UTC).  Everything else is meant to be byte-identical to the committed file.

materialize.py is read from git at MATERIALIZE_REV, not from the runtime worktree's working tree: the committed file
recorded sha256 83b3ea62... which is the blob at af40d63 (2026-10-12 13:44, load-pilot epoch); the worktree has since
moved on (d1358bb), and its file hashes differently.  Reading a pinned blob is read-only on the harness worktree.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RT = ROOT.parent / "observability-placement-runtime-otel-protocol"
MATERIALIZE_REL = "modules/otel-demo/materialize.py"
MATERIALIZE_REV = "af40d63"

READOUT = ROOT / "research/traffic-sweep/readout-otel-primary-v3.1/sweep_analysis_v3.json"
PLACEMENT = ROOT / "research/placement/out/otel-primary/placement.json"
CATALOG_CURRENT = RT / "modules/otel-demo/postures/catalog.json"
CATALOG_V3 = ROOT / "tmp/otel-v2-admission/modules/otel-demo/postures/catalog.json"
MATERIALIZE = RT / MATERIALIZE_REL
ENVOY = ROOT / "upstream/opentelemetry-demo/src/frontendproxy/envoy.tmpl.yaml"
OTELCOL = ROOT / "upstream/opentelemetry-demo/src/otelcollector/otelcol-config.yml"
PROFILE = ROOT / "research/system-profiles/otel.md"
README = ROOT / "research/placement/declared/README.md"
RESULT = ROOT / "research/otel-postures/RESULT.md"

POSTURES = ("none", "selected", "async", "full")

# ---- the coordinator's rules and notes, verbatim from the committed otel.effort.json (@ROOT@/@RT@ = repo/runtime root)
DESCRIPTION = ('Sensor effort tiers for the OTel demo, union of readout calibration sensor keys and placement '
 'groundSet ids (primary arm).')

RULES = {'R-SPAN-UP': {'effortTier': 0,
               'ootb': True,
               'text': 'Span from an application service that upstream instruments as shipped. '
                       'Every app service has an upstream load site with no harness code change '
                       '(catalog serviceInstrumentation row per service; otel.md "Every app '
                       'service is instrumented with no code change"). Harness guards only disable '
                       'existing registrations (materialize.py:369 apply_source_placement_guards).',
               'cites': ['@RT@/modules/otel-demo/postures/catalog.json:323 (serviceInstrumentation '
                         'row per service, see sourceLine)',
                         '@ROOT@/research/system-profiles/otel.md:55',
                         '@RT@/modules/otel-demo/materialize.py:369']},
 'R-METRIC-OTLP': {'effortTier': 0,
                   'ootb': True,
                   'text': 'OTLP metric point from an application service that upstream '
                           'instruments as shipped (same evidence as R-SPAN-UP).',
                   'cites': ['@RT@/modules/otel-demo/postures/catalog.json:363',
                             '@ROOT@/research/system-profiles/otel.md:55']},
 'R-SPANMETRICS': {'effortTier': 0,
                   'ootb': True,
                   'text': 'Collector spanmetrics connector output (metric names calls, '
                           'duration~*). Upstream collector pipeline already exports to '
                           'spanmetrics.',
                   'cites': ['@ROOT@/upstream/opentelemetry-demo/src/otelcollector/otelcol-config.yml:120 '
                             '(spanmetrics connector)',
                             '@ROOT@/upstream/opentelemetry-demo/src/otelcollector/otelcol-config.yml:127 '
                             '(traces pipeline exporters incl. spanmetrics)']},
 'R-LOG-STDOUT': {'effortTier': 0,
                  'ootb': True,
                  'text': 'Log id from an upstream service stdout line (log ids are 12-hex hashes '
                          'of stdout lines). Stdout is not controlled by OTEL_*_EXPORTER, and '
                          'services run in every posture.',
                  'cites': ['@ROOT@/research/placement/declared/README.md:30']},
 'R-WITNESS': {'effortTier': 1,
               'ootb': None,
               'text': 'frontendproxy log line that may come from the harness-added Envoy stdout '
                       'access log (obsplacement_kind witness). Template config change, no service '
                       'code. Upper bound: the hash cannot separate harness witness lines from '
                       'upstream Envoy stdout lines, so the whole family is tier 1 and ootb is '
                       'unknown (null).',
               'cites': ['@RT@/modules/otel-demo/materialize.py:652 (witness access_log inserted '
                         'into envoy.tmpl.yaml)',
                         '@ROOT@/upstream/opentelemetry-demo/src/frontendproxy/envoy.tmpl.yaml:18 '
                         '(upstream envoy.tmpl.yaml tracing block; no access_log, checked by '
                         'script)']},
 'L-LEDGER': {'effortTier': None,
              'ootb': False,
              'text': 'Client-side request-ledger field from the harness load client, not emitted '
                      'by any service. Not classifiable with the three-tier scale.',
              'cites': ['readout calibration.primary.perRate[*].sensors key with prefix ledger: '
                        '(sweep_analysis_v3.json)']},
 'R-CODE-PATCH': {'effortTier': 2,
                  'ootb': False,
                  'text': 'Sensor that exists only because the harness patched service code to add '
                          'telemetry. Applies to zero ids: the source guards only gate '
                          'registrations that upstream already contains.',
                  'cites': ['@RT@/modules/otel-demo/materialize.py:369']}}

COST_UNIT = 'CPU ms per offered request, paired steps, no-fault-cost, 3 blocks (mean)'

COST_SOURCE = '@ROOT@/research/otel-postures/RESULT.md:19-25 and :38'

COST_SCOPE = 'instance (one SUT, one host, n=3)'

COST_NOTE = ('Per posture step, not per sensor. Step shares fall in the >10% (none->selected) and 1-10% (other '
 'steps) bins if applied to the step service group; no sensor-level cost exists. async step: four '
 'added services = 52-91% of the step per block (RESULT.md:38, per-service resources.json, not '
 're-derived).')

POSTURE_CATALOG_NOTES = {'v3': 'v3 epoch used by the v3 readout cells (selected = frontend, frontendproxy, '
       'recommendationservice)',
 'current': 'runtime worktree, catalog HEAD; selected has 11 services. Differs from v3 for '
            'selected/async.'}

RUNTIME_COST_NOTE = 'not derivable per sensor: posture-step CPU only (see postureCostEvidence)'

OBS_NOTE = ('span/metric ids are read from the otelcol debug exporter, which the harness sets to verbosity '
 'detailed (@RT@/modules/otel-demo/materialize.py:697); upstream sets no verbosity '
 '(@ROOT@/upstream/opentelemetry-demo/src/otelcollector/otelcol-config.yml:92). Emission is '
 'unaffected.')

TIER_NOTE = 'upper bound; see rules.R-WITNESS'


def fill(o):
    """Replace the @ROOT@ / @RT@ placeholders in a constant by this checkout's paths."""
    if isinstance(o, str):
        return o.replace("@RT@", str(RT)).replace("@ROOT@", str(ROOT))
    if isinstance(o, list):
        return [fill(x) for x in o]
    if isinstance(o, dict):
        return {fill(k): fill(v) for k, v in o.items()}
    return o


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def materialize_bytes() -> bytes:
    return subprocess.run(["git", "-C", str(RT), "show", f"{MATERIALIZE_REV}:{MATERIALIZE_REL}"],
                          check=True, capture_output=True).stdout


def parse_id(sid: str):
    """family, service of a sensor id.  ledger ids carry a service in the id but the record has none."""
    family, rest = sid.split(":", 1)
    return family, (None if family == "ledger" else rest.split(":", 1)[0])


def service_lines(catalog_path: Path) -> dict:
    """1-based line of each service key inside serviceInstrumentation (the row `sourceLine` points at)."""
    lines = catalog_path.read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith('  "serviceInstrumentation"'))
    out = {}
    for i in range(start + 1, len(lines)):
        m = re.match(r'^    "([^"]+)": \{$', lines[i])
        if m:
            out[m.group(1)] = i + 1
        elif lines[i].startswith("  }"):
            break
    return out


def classify(sid: str, family: str, service):
    """rule name per id: the rule table is RULES, this is only which row an id falls in."""
    if family == "ledger":
        return "L-LEDGER"
    if family == "span":
        return "R-SPAN-UP"
    if family == "metric":
        name = sid.split(":", 2)[2]
        return "R-SPANMETRICS" if name == "calls" or name.startswith("duration~") else "R-METRIC-OTLP"
    if family == "log":
        return "R-WITNESS" if service == "frontendproxy" else "R-LOG-STDOUT"
    raise ValueError(f"unknown family in id {sid!r}")


def cost_evidence(result_text: str) -> dict:
    """posture-step CPU numbers from RESULT.md's paired-steps table; shares are step delta / none level."""
    none_level = float(re.search(r"`none` level ~([0-9.]+) ms CPU per request", result_text).group(1))
    rows = {"none -> selected": "none_to_selected", "selected -> async": "selected_to_async",
            "async -> full": "async_to_full", "none -> full": "none_to_full"}
    steps = {}
    for label, key in rows.items():
        m = re.search(r"^\| " + re.escape(label) + r" \| \+([0-9.]+) ms ", result_text, re.M)
        delta = float(m.group(1))
        steps[key] = {"delta_ms": delta, "share_of_none_level": round(delta / none_level, 3)}
    return {"unit": COST_UNIT, "source": fill(COST_SOURCE), "none_level_ms": none_level, "steps": steps,
            "scope": COST_SCOPE, "note": COST_NOTE}


def build() -> dict:
    readout = json.loads(READOUT.read_text())
    placement = json.loads(PLACEMENT.read_text())
    cat_cur = json.loads(CATALOG_CURRENT.read_text())
    cat_v3 = json.loads(CATALOG_V3.read_text())

    # checks the prose records as "checked by script"
    assert cat_cur["serviceInstrumentation"] == cat_v3["serviceInstrumentation"], "serviceInstrumentation differs"
    assert "access_log" not in ENVOY.read_text(), "upstream envoy.tmpl.yaml has an access_log"
    mat = materialize_bytes()
    assert b"verbosity: detailed" in mat, "materialize.py no longer sets debug verbosity: detailed"

    calib = set()
    for rate in readout["calibration"]["primary"]["perRate"].values():
        calib |= set(rate["sensors"])
    ground = set()
    for arm in placement["arms"]["primary"].values():
        ground |= set(arm["groundSet"])
    ids = sorted(calib | ground)

    lines = service_lines(CATALOG_CURRENT)
    rules = fill(RULES)
    sensors = []
    for sid in ids:
        family, service = parse_id(sid)
        rname = classify(sid, family, service)
        rule = rules[rname]
        if family in ("span", "metric"):
            post_v3 = [p for p in POSTURES if service in cat_v3["postures"][p]["activeApplicationServices"]]
            post_cur = [p for p in POSTURES if service in cat_cur["postures"][p]["activeApplicationServices"]]
        else:  # logs survive every posture (declared/README.md:30); the ledger is a client-side field
            post_v3, post_cur = list(POSTURES), list(POSTURES)
        row = {"id": sid, "family": family, "service": service, "effortTier": rule["effortTier"], "rule": rname,
               "ootb": rule["ootb"], "postures": post_v3, "postureCurrentCatalog": post_cur,
               "runtimeCostShare": None, "runtimeCostShareNote": RUNTIME_COST_NOTE,
               "observationTier": 1 if family in ("span", "metric") else None,
               "observationNote": fill(OBS_NOTE) if family in ("span", "metric") else None,
               "inReadoutCalibration": sid in calib, "inPlacementGroundSet": sid in ground}
        if rname == "R-WITNESS":
            row["tierNote"] = TIER_NOTE
        if family != "ledger":
            row["sourceLine"] = f"{CATALOG_CURRENT}:{lines[service]}"
        sensors.append(row)

    def tally(keyf):
        c = {}
        for r in sensors:
            k = keyf(r)
            c[k] = c.get(k, 0) + 1
        return c

    applied = tally(lambda r: r["rule"])
    for name, rule in rules.items():
        rule["appliedTo"] = applied.get(name, 0)

    inputs = {}
    for path in (READOUT, PLACEMENT, CATALOG_CURRENT, CATALOG_V3, MATERIALIZE, ENVOY, OTELCOL, PROFILE, README):
        inputs[str(path)] = {"sha256": sha256(mat if path == MATERIALIZE else path.read_bytes())}

    return {
        "schemaVersion": 1, "system": "otel", "scope": "instance",
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        "description": DESCRIPTION,
        "inputs": inputs,
        "postureCatalogs": {"v3": {"path": str(CATALOG_V3), "note": POSTURE_CATALOG_NOTES["v3"]},
                            "current": {"path": str(CATALOG_CURRENT), "note": POSTURE_CATALOG_NOTES["current"]}},
        "denominator": {
            "idsTotal": len(ids),
            "sensorIdsSpanLogMetric": sum(1 for r in sensors if r["family"] != "ledger"),
            "ledgerIds": sum(1 for r in sensors if r["family"] == "ledger"),
            "idsInReadoutCalibration": len(calib & set(ids)),
            "idsInPlacementGroundSet": len(ground),
            "idsOnlyInGroundSet": len(ground - calib),
            "idsOnlyInCalibration": len(calib - ground),
        },
        "countsByTier": {str(k): v for k, v in tally(lambda r: r["effortTier"]).items()},
        "countsByOotb": {str(k): v for k, v in tally(lambda r: r["ootb"]).items()},
        "countsByFamilyTier": tally(lambda r: f"{r['family']}|tier{r['effortTier']}"),
        "countsByFamilyOotb": tally(lambda r: f"{r['family']}|ootb={r['ootb']}"),
        "postureSetsDifferBetweenCatalogs": sum(1 for r in sensors if r["postures"] != r["postureCurrentCatalog"]),
        "postureCostEvidence": cost_evidence(RESULT.read_text()),
        "sensors": sensors,
        "rules": rules,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, type=Path, help="new output path; refuses to overwrite")
    out = ap.parse_args(argv).out
    if out.exists():
        print(f"refusing to overwrite existing path: {out}", file=sys.stderr)
        return 2
    text = json.dumps(build(), indent=1) + "\n"
    with open(out, "x") as fh:  # exclusive create
        fh.write(text)
    print(f"wrote {out} sha256={sha256(text.encode())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
