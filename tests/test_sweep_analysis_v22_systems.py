"""Analysis v2.4's TeaStore and OTel readers (research/detection-time/sweep_analysis_v2.py, `--system teastore|otel`).

Layer: reader + synthetic end-to-end. The cells under tests/fixtures/sweep_v22 were written by the harnesses' own code
at the pinned commits (TeaStore 91c4967: make_sweep_run with the real extractors, then the harness's cell validator;
OTel 6e37ec2: candidate_remote.run_cell driven by the harness's fake target, then the harness's terminal), by
tests/fixtures/sweep_v22/generate_*.py; no TeaStore or OTel evidence is read. Each check reads the harness's own
files independently (the ledger, the bridge correlation the harness extracted, its trace correlation, the receipts)
and compares them with the model the reader builds. Every reader rule has a planted defect (MUTANTS) that one of its
checks catches; a file outside the pinned schema stops the run (UnknownSchema), and that check fails when the schema
check is planted away.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "detection-time"))

import sweep_analysis_v2 as v2  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "sweep_v22"
TS_CAMP, OT_CAMP = FIX / "teastore" / "campaign", FIX / "otel" / "campaign"
TS_PAUSE, TS_THROTTLE, TS_NF = "auth-freeze-effect", "persistence-cpu-throttle-effect", "no-fault-cost"
OT_PAUSE, OT_THROTTLE, OT_NF = "frontend-pause-effect", "productcatalog-cpu-throttle-effect", "no-fault-calibration"


def _cell_dir(camp, regime):
    hits = [d for d in sorted((camp / "runs").rglob("receipt.json"))
            if json.loads(d.read_text()).get("run", json.loads(d.read_text()).get("runKey", {})).get("regime") == regime]
    assert len(hits) == 1, (camp, regime, hits)
    return hits[0].parent


def _load(system, d):
    with v2.use_system(system):
        return (v2.teastore_load_or_invalid if system == "teastore" else v2.otel_load_or_invalid)(d)


def _copy(camp, dest):
    shutil.copytree(camp, dest)
    return dest


def _edit_json(path, fn):
    doc = json.loads(path.read_text())
    out = fn(doc)
    path.write_text(json.dumps(doc if out is None else out, indent=2, sort_keys=True) + "\n")


QUIET_COPIES = 9          # 10 no-fault cells x 180 s = 0.5 h per rate: one alarm stays under the 15/h bound
RARE = {"teastore": ("webui", "05-Oct-2026 06:00:01.123 INFO [main] org.example.fixture.Rare.run rare fixture template"),
        "otel": ("productcatalogservice", "rare fixture template")}


def _barrier_epoch(system, d):
    if system == "teastore":
        return v2.dt.epoch(json.loads((d / "receipt.json").read_text())["window"]["measurementStartedAt"])
    return json.loads((d / "request-ledger.json").read_text())["barrierEpoch"]


def _docker_stamp(epoch):
    whole = int(epoch)
    return v2._dt.datetime.fromtimestamp(whole, v2._dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + \
        ".%09dZ" % int(round((epoch - whole) * 1e9))


def _quiet_campaign(camp, regime, dest, copies=QUIET_COPIES, system=None):
    """A second campaign holding `copies` copies of the no-fault cell (the quiet run's shape: the sweep's no-fault cell
    repeated); pooled with the sweep it certifies an operating point (H1/H2). F8 (v2.2 review): with `system`, copy 1
    is perturbed, its application.log carrying one line of a template no other cell has (30 s after the barrier, with
    a Docker receive stamp), so a held-out cell is not its twins' copy and leave-one-cell-out is tested."""
    src = _cell_dir(camp, regime)
    for i in range(copies):
        rel = src.relative_to(camp)
        d = dest / rel.parent / ("%s-q%02d" % (rel.name, i))
        shutil.copytree(src, d)
        if system and i == 1:
            svc, line = RARE[system]
            with (d / "application.log").open("a") as fh:
                fh.write("%s-1  | %s %s\n" % (svc, _docker_stamp(_barrier_epoch(system, d) + 30.0), line))
    return dest


# ----------------------------------------------------------------------------- the fixtures are the generators' output

def test_fixture_files_are_the_generators_output():
    """No fixture file was edited after generation: every file equals its MANIFEST digest, written by the generator
    against the pinned harness commit."""
    for system, pinned in (("teastore", "91c4967"), ("otel", "6e37ec2")):
        man = json.loads((FIX / system / "MANIFEST.json").read_text())
        assert man["harnessCommit"].startswith(pinned)
        files = {p.relative_to(FIX / system).as_posix() for p in (FIX / system / "campaign").rglob("*") if p.is_file()}
        assert files == set(man["files"])
        for rel, sha in man["files"].items():
            assert hashlib.sha256((FIX / system / rel).read_bytes()).hexdigest() == sha, rel


# ----------------------------------------------------------------------------- TeaStore reader

def check_ts_ledger():
    """Ledger rows are the journey-terminal records: start/end on fixed_load's barrier clock, ok = succeeded and 200,
    token = opaqueToken, scheduled = scheduledMonotonicOffsetSeconds; the pause cell's timed-out journeys are failed."""
    ok = True
    for regime in (TS_NF, TS_PAUSE, TS_THROTTLE):
        d = _cell_dir(TS_CAMP, regime)
        c = _load("teastore", d)
        rows = [json.loads(x) for x in (d / "journey-ledger.jsonl").read_text().splitlines()]
        js = {r["sequence"]: r for r in rows if r["recordType"] == "journey-terminal"}
        ok &= c["valid"] and len(c["ledger"]) == len(js)
        for r in c["ledger"]:
            j = js[r.seq]
            ok &= (r.start, r.end, r.token, r.sched) == (j["actualStartMonotonic"], j["actualEndMonotonic"],
                                                        j["opaqueToken"], j["scheduledMonotonicOffsetSeconds"])
            ok &= r.ok == (j["outcome"] == "succeeded" and all(q["statusCode"] == 200 for q in j["requests"]))
        man = json.loads((FIX / "teastore" / "MANIFEST.json").read_text())
        timed_out = next(x["timedOutJourneys"] for x in man["cells"] if x["regime"] == regime)
        ok &= sorted(r.seq for r in c["ledger"] if not r.ok) == timed_out
    return ok


def check_ts_bridge():
    """A Kieker record's request is its trace's bridged token: the reader's span tokens equal the harness's own
    native-token correlation (native-token-correlation.json) for every row it holds; untokened traces stay untokened."""
    ok = True
    for regime in (TS_NF, TS_PAUSE):
        d = _cell_dir(TS_CAMP, regime)
        c = _load("teastore", d)
        corr = {}
        for line in (d / "native-token-correlation.json").read_text().splitlines():
            if line.strip():
                for row in (json.loads(line) if line.strip().startswith("[") else [json.loads(line)]):
                    corr[str(row["nativeTraceId"])] = row["token"]
        events = json.loads((d / "traces.json").read_text())
        seen = 0
        for e in events:
            end = e["tin"] / v2.NS_PER_S + (e["tout"] - e["tin"]) / v2.NS_PER_S
            tok = c["spanTok"].get((e["service"], v2.common.symptoms().op_token(e["operation"])), {}).get(end, set())
            if str(e["trace_id"]) in corr:
                ok &= tok == {corr[str(e["trace_id"])]}
                seen += 1
        ok &= seen > 0 and c["spanOwnTok"] == {}
    return ok


def check_ts_receipt():
    """The fault receipt on the ledger's clock: onset = the pre-command stamp, the interval's upper bound = the
    command's return (no Docker events), window end = the revert command, probes and [revert, ready] excluded."""
    d = _cell_dir(TS_CAMP, TS_PAUSE)
    c = _load("teastore", d)
    iv = json.loads((d / "intervention.json").read_text())
    cs = iv["sweep"]["commandStamps"]
    shift = v2.dt.epoch(json.loads((d / "receipt.json").read_text())["window"]["measurementStartedAt"]) - \
        c["align"]["offset"]
    near = lambda a, b: abs(a - b) < 1e-6   # noqa: E731
    return (near(c["cmd"]["A"]["mono"], shift + cs["onsetCommandIssuedMonotonicOffsetSeconds"])
            and near(c["onset"]["hi"], shift + cs["onsetCommandReturnedMonotonicOffsetSeconds"])
            and near(c["cmd"]["B"]["mono"], shift + cs["revertCommandIssuedMonotonicOffsetSeconds"])
            and c["onset"]["hiKind"] == "command-returned"
            and {w["kind"] for w in c["probeWindows"]} == {"recovery", "probe-post-revert-readiness"}
            and c["receiptAlign"]["residual"] < 1e-5 and c["faultKind"] == "pause" and c["target"] == "auth")


def check_ts_clock_shift(tmp_path):
    """fixed_load's barrier and the producer's differ (separate processes): a ledger whose monotonic offsets run 0.3 s
    ahead of its wall stamps maps the producer's onset 0.3 s later on the ledger clock."""
    camp = _copy(TS_CAMP, tmp_path / "shift")
    d = _cell_dir(camp, TS_PAUSE)
    lines = []
    for x in (d / "journey-ledger.jsonl").read_text().splitlines():
        r = json.loads(x)
        if r["recordType"] == "journey-terminal":
            for k in ("actualStartMonotonic", "actualEndMonotonic", "scheduledMonotonicOffsetSeconds"):
                r[k] = r[k] + 0.3
        lines.append(json.dumps(r, sort_keys=True))
    (d / "journey-ledger.jsonl").write_text("\n".join(lines) + "\n")
    c = _load("teastore", d)
    issued = json.loads((d / "intervention.json").read_text())["sweep"]["commandStamps"][
        "onsetCommandIssuedMonotonicOffsetSeconds"]
    return abs(c["cmd"]["A"]["mono"] - (issued + 0.3)) < 1e-6


def check_ts_samples():
    """S = the cgroup sampler: rates over consecutive samples by their `monotonic` stamps, timed at the later one,
    mapped through the producer's barrier; Hotel's tokens."""
    d = _cell_dir(TS_CAMP, TS_THROTTLE)
    c = _load("teastore", d)
    doc = json.loads((d / "system-samples.json").read_text())
    win = json.loads((d / "receipt.json").read_text())["window"]
    e_p, m_p = v2.dt.epoch(win["measurementStartedAt"]), win["measurementStartMonotonic"]
    obs, vals, meta = c["prep"][("metric", "persistence", "sys_cpu")]
    rows = doc["samples"]
    want_t = [e_p + b["monotonic"] - m_p for b in rows[1:]]
    want_v = [(b["services"]["persistence"]["cpuUsageUsec"] - a["services"]["persistence"]["cpuUsageUsec"]) /
              (b["monotonic"] - a["monotonic"]) / v2.US_PER_S for a, b in zip(rows, rows[1:])]
    toks = {k[2] for k in c["prep"] if k[0] == "metric" and k[1] == "persistence"}
    return (obs == want_t and all(abs(x - y) < 1e-12 for x, y in zip(vals, want_v)) and meta["collector"] ==
            "cgroup-sampler" and toks == {"sys_cpu", "sys_memory", "sys_io", "sys_psi_cpu", "sys_psi_memory",
                                          "sys_psi_io"})


def check_ts_family_m():
    """M (docker stats) exists in no-fault cells only: not read, `—` with the reason, never 0."""
    with v2.use_system("teastore"):
        c = v2.teastore_load_or_invalid(_cell_dir(TS_CAMP, TS_PAUSE))
        return (not v2.collects(c, "M") and v2.collects(c, "S") and v2.collects(c, "T")
                and "no-fault cells only" in c["familyAbsent"]["M"])


def check_ts_probe_trace(tmp_path):
    """An untokened webui-rooted trace that starts in the post-revert probe window is probe traffic, not read; the
    same trace outside every probe window is read (as untokened)."""
    camp = _copy(TS_CAMP, tmp_path / "probe")
    d = _cell_dir(camp, TS_PAUSE)
    c0 = _load("teastore", d)
    probe = next(w for w in c0["probeWindows"] if w["kind"] == "probe-post-revert-readiness")
    off = c0["align"]["offset"]
    events = json.loads((d / "traces.json").read_text())
    tpl = dict(events[0])
    for k, at in (("inside", probe["startMono"] + 0.01), ("outside", 30.0)):
        tin = int(round((at + off) * v2.NS_PER_S))
        events.append(dict(tpl, trace_id=str(990_000 + len(k)), kieker_trace_id=990_000 + len(k),
                           span_id="%d:0" % (990_000 + len(k)), parent_span_id="", service="webui",
                           operation="tools.descartes.teastore.webui.servlet.StatusServlet.doGet", tin=tin,
                           tout=tin + 1_000_000, eoi=0, ess=0))
    (d / "traces.json").write_text(json.dumps(events, indent=1))
    c = _load("teastore", d)
    status = [k for k in c["prep"] if k[1] == "webui" and "StatusServlet" in k[2]]
    obs = c["prep"][status[0]][0] if status else []
    return c["readStats"].get("probeTracesExcluded") == 1 and len(obs) == 1


def check_ts_p1(tmp_path):
    """P1 (auth-freeze, TeaStore's declaration): the first journey not completed by the onset times out at start +
    15 s; the ledger's first `failed` catch is there. And the declared alternative: webui answering earlier with an
    error (a 500 after 2 s) holds P1 by its own branch."""
    Rr = v2.run(TS_CAMP, system="teastore")
    p = Rr["predictions"]["P1"]
    row = p["perEpisode"][0]
    c = next(x for x in Rr["cells"] if x["regime"] == TS_PAUSE)
    first = min((r for r in c["ledger"] if r.end > row["lo"]), key=lambda r: r.start)
    ok = (p["n"] == 1 and row["ok"] is True and abs(row["expected"][0] - (first.start + 15.0 - row["lo"])) < 1e-9
          and abs(row["observed"] - (first.end - row["lo"])) < 1e-9 and row["branch"] == "timeout interval")
    camp = _copy(TS_CAMP, tmp_path / "answer")
    d = _cell_dir(camp, TS_PAUSE)
    lines = []
    for x in (d / "journey-ledger.jsonl").read_text().splitlines():
        r = json.loads(x)
        if r["recordType"] == "journey-terminal" and r["sequence"] == first.seq:
            r["actualEndMonotonic"] = r["actualStartMonotonic"] + 2.0
            r["outcome"] = "failed"
            r["requests"][0].update(statusCode=500, actualEndMonotonic=r["actualEndMonotonic"],
                                    error={"type": "HTTPError"}, outcome="failed")
            r["errors"] = [{"type": "HTTPError", "scope": "request", "requestSequence": 0}]
        lines.append(json.dumps(r, sort_keys=True))
    (d / "journey-ledger.jsonl").write_text("\n".join(lines) + "\n")
    R2 = v2.run(camp, system="teastore")
    q = R2["predictions"]["P1"]["perEpisode"][0]
    md = v2.render(R2, v2.build_json(R2))                                       # F2: the branch is printed
    return (ok and q["ok"] is True and q.get("branch", "").startswith("error answer")
            and R2["predictions"]["P1"]["holdsByBranch"] == {q["branch"]: 1}
            and "holds by branch: %s 1" % q["branch"] in md and "holds via **%s**" % q["branch"] in md)


def check_ts_end_to_end(tmp_path):
    """Sweep + a quiet campaign (4 copies of the no-fault cell) pooled: the operating point certifies at 0.2/s, the
    single pause episode's P4 is `—` (n = 1) with its descriptive comparison, P2 is `—` (n < 4), M is listed `—`,
    and the readout names the system and the harness commit."""
    quiet = _quiet_campaign(TS_CAMP, TS_NF, tmp_path / "quiet", system="teastore")
    Rr = v2.run([TS_CAMP, quiet], system="teastore")
    J = v2.build_json(Rr)
    md = v2.render(Rr, J)
    p4 = Rr["predictions"]["P4"]["P4a"][TS_PAUSE]["perRate"]["0.2"]
    km = Rr["kmaps"]["primary"][TS_PAUSE][0.2]
    return (Rr["system"] == "teastore" and len(Rr["campaigns"]) == 2 and km["E"] is not None
            and km["M"] is None and p4["holds"] is None and p4.get("singleEpisode") is not None
            and "n = 1" in p4["note"] and Rr["predictions"]["P2"]["0.2"]["holds"] is None
            and any("family M" in x["output"] for x in J["dashOutputs"])
            and "# Traffic sweep, TeaStore: analysis v2.4" in md and "91c4967" in md and "0588a41" in md
            and "not listed in HARNESS_PROVENANCE" in md and "Known limitation F9" in md
            and "## Outputs that are — by construction" in md and "Moved verdicts" not in md
            and J["v1"] is None and J["provenance"]["input"]["perCampaign"])


# ----------------------------------------------------------------------------- OTel reader

def check_ot_ledger():
    ok = True
    for regime in (OT_NF, OT_PAUSE):
        d = _cell_dir(OT_CAMP, regime)
        c = _load("otel", d)
        led = json.loads((d / "request-ledger.json").read_text())
        rows = {q["requestToken"]: q for q in led["requests"]}
        ok &= c["valid"] and len(c["ledger"]) == len(rows) and c["base"]["mono"] == led["barrierMonotonic"]
        for r in c["ledger"]:
            q = rows[r.token]
            ok &= (r.start, r.end, r.ok) == (q["startedMonotonic"], q["endedMonotonic"], q["outcome"] == "ok")
            ok &= abs(r.sched - (led["barrierMonotonic"] + q["scheduledOffsetSeconds"])) < 1e-9
        ok &= c["timing"]["requestTimeoutSeconds"] == 15.0
    return ok


def check_ot_trace_tokens():
    """A span's request is the ledger row whose originalTraceId is its Trace ID (the harness's own join): every
    request the harness's trace correlation saw complete has its three route services' spans tokened with it."""
    d = _cell_dir(OT_CAMP, OT_NF)
    c = _load("otel", d)
    corr = json.loads((d / "trace-correlation.json").read_text())
    by_tok = {}
    for (svc, _), per in c["spanTok"].items():
        for toks in per.values():
            for t in toks:
                by_tok.setdefault(t, set()).add(svc)
    rows = corr["rows"]
    complete = [r for r in rows if r.get("observedPathServices") == ["frontend", "frontendproxy",
                                                                    "productcatalogservice"]]
    return (len(complete) > 0 and all(by_tok.get(r["requestToken"]) == {"frontend", "frontendproxy",
                                                                       "productcatalogservice"} for r in complete)
            and c["spanEdges"] == {("frontendproxy", "frontend"), ("frontend", "productcatalogservice")}
            and c["spanOwnTok"] == {})


def check_ot_logs():
    """Envoy's access log names its request token (own token) and a traceparent (mapped through originalTraceId to the
    same token); application lines carry Docker receive stamps; json-line and plain-line records."""
    d = _cell_dir(OT_CAMP, OT_NF)
    c = _load("otel", d)
    own = {(k, t): v for k, per in c["logTok"].items() for t, v in per.items() if k[0] == "frontendproxy"}
    via = {(k, t): v for k, per in c["logTraceTok"].items() for t, v in per.items() if k[0] == "frontendproxy"}
    tokens = {r.token for r in c["ledger"]}
    # F3: Envoy's own stamp (start_time + duration_ms, written at completion) gives frontendproxy an app stamp, and
    # the cell's receipt-delay bound is max(Docker stamp - that stamp), recomputed here from the file
    worst = None
    for line in (d / "application.log").read_text(errors="replace").splitlines():
        if line.startswith("frontendproxy") and "{" in line:
            dock, payload = v2.v1.docker_stamp(line.split(" | ", 1)[1])
            o = json.loads(payload)
            if "start_time" in o:
                x = dock - (float(o["start_time"]) + float(o["duration_ms"]) / 1000.0)
                worst = x if worst is None else max(worst, x)
    rc = c["logReceipt"]
    return (len(own) >= len(tokens) and {x for v in own.values() for x in v} >= tokens
            and all(via[k] <= own[k] for k in via) and len(via) == len(tokens)
            and c["readStats"]["log:record:json-line"] > 0 and c["readStats"]["log:record:plain-line"] > 0
            and rc["dockerDigits"] == 9 and worst is not None and rc["bound"] is not None
            and abs(rc["bound"] - worst) < 1e-6 and "frontendproxy" not in rc["servicesWithoutAppStamp"]
            and "frontend" in rc["servicesWithoutAppStamp"])


def check_ot_metrics_and_fault():
    """M = OTLP data points (the adapter's series rules); the throttled productcatalogservice's gauge rises during the
    hold; the receipt: onset = startedMonotonic, upper bound = appliedMonotonic, end = revertingMonotonic, the
    during-fault and post-revert probes and [reverting, ready] excluded; S is `—` with the reason."""
    d = _cell_dir(OT_CAMP, OT_THROTTLE)
    with v2.use_system("otel"):
        c = v2.otel_load_or_invalid(d)
        iv = json.loads((d / "intervention.json").read_text())
        obs, vals, meta = c["prep"][("metric", "productcatalogservice", "app.fixture.load")]
        A, B = c["cmd"]["A"]["wall"], c["cmd"]["B"]["wall"]
        inside = [v for t, v in zip(obs, vals) if A + 1.0 < t < B]
        outside = [v for t, v in zip(obs, vals) if t < A or t > B + 1.0]
        return (inside and outside and min(inside) > max(outside) and meta["collector"] == "otlp-debug-exporter"
                and c["cmd"]["A"]["mono"] == iv["startedMonotonic"] and c["onset"]["hi"] == iv["appliedMonotonic"]
                and c["cmd"]["B"]["mono"] == iv["revertingMonotonic"]
                and {w["kind"] for w in c["probeWindows"]} == {"probe-during-fault", "probe-post-revert", "recovery"}
                and not v2.collects(c, "S") and v2.collects(c, "M") and "no cgroup" in c["familyAbsent"]["S"])


def check_ot_probe_traces():
    """The fault cells' probe requests (no traceparent: a fresh trace each) are not read."""
    c = _load("otel", _cell_dir(OT_CAMP, OT_PAUSE))
    return c["readStats"].get("probeTracesExcluded") == 2


def check_ot_p1():
    """P1 (frontend-pause, OTel's declaration): the expected first timeout is the first request not completed by the
    onset + 15 s; observed = the ledger's first `failed` catch; both computed from the ledger file."""
    Rr = v2.run(OT_CAMP, system="otel")
    row = Rr["predictions"]["P1"]["perEpisode"][0]
    d = _cell_dir(OT_CAMP, OT_PAUSE)
    led = json.loads((d / "request-ledger.json").read_text())
    e1 = min(q["startedMonotonic"] + 15.0 for q in led["requests"] if q["endedMonotonic"] > row["lo"])
    fail = min(q["endedMonotonic"] for q in led["requests"] if q["outcome"] != "ok")
    return (row["ok"] is not None and abs(row["expected"][0] - (e1 - row["lo"])) < 1e-9
            and abs(row["observed"] - (fail - row["lo"])) < 1e-9 and Rr["predictions"]["P1"]["n"] == 1
            and Rr["predictions"]["P2"]["1"]["threshold"] == 1 + 1.0 * 15.0 + 2)


def check_ot_route_graph():
    """The spike path filter's call graph is the project map's restricted to the sweep route: flagd and
    recommendationservice (the base run's route) are off every affected path."""
    with v2.use_system("otel"):
        ctx = v2.make_ctx([])
        return (v2.v1.path_of("productcatalogservice", ctx) == {"productcatalogservice", "frontend", "frontendproxy"}
                and "recommendationservice" not in v2.v1.path_of("frontend", ctx))


def check_ot_end_to_end(tmp_path):
    quiet = _quiet_campaign(OT_CAMP, OT_NF, tmp_path / "quiet", system="otel")
    Rr = v2.run([OT_CAMP, quiet], system="otel")
    J = v2.build_json(Rr)
    md = v2.render(Rr, J)
    p4 = Rr["predictions"]["P4"]["P4a"][OT_PAUSE]["perRate"]["1"]
    km = Rr["kmaps"]["primary"][OT_PAUSE][1.0]
    se = p4.get("singleEpisode") or {}
    return (km["E"] is not None and km["S"] is None and p4["holds"] is None and se.get("sensors")
            and all(x["category"] for x in se["sensors"]) and any("family S" in x["output"] for x in J["dashOutputs"])
            and "# Traffic sweep, OTel Demo: analysis v2.4" in md and "6e37ec2" in md and "6a47d0b" in md
            and "c532853" in md and "Reader statistics" in md
            and Rr["predictions"]["P3"][0]["state"] == v2.DASH)


def _loco(system, camp, nf, rate, regime, tmp_path):
    quiet = _quiet_campaign(camp, nf, tmp_path / ("loco-" + system), system=system)
    with v2.use_system(system):
        located, cells = v2.find_and_load([camp, quiet])
        op = v2.operating_point(cells, v2.ARMS["primary"])
    t = op["table"]["L"][regime][rate]
    return t["perK"][0]["alarms"] == 1 and any("appear" in k for k in t["atLargestK"])


def check_ts_loco(tmp_path):
    """F8: the perturbed quiet copy, held out, raises one `appear` (its rare template is in no other cell); fitted on
    itself (no LOCO) it raises none."""
    return _loco("teastore", TS_CAMP, TS_NF, 0.2, TS_PAUSE, tmp_path)


def check_ot_loco(tmp_path):
    return _loco("otel", OT_CAMP, OT_NF, 1.0, OT_PAUSE, tmp_path)


def check_ts_bridge_drops(tmp_path):
    """F11: a bridge row mapping a journey's token to a second trace is dropped by the reader (the harness would refuse
    the cell), counted, and printed in the readout."""
    camp = _copy(TS_CAMP, tmp_path / "drops")
    d = _cell_dir(camp, TS_NF)
    auth = (d / "auth.log").read_text()
    first = next(json.loads(x.split("OBSERVABILITY_NATIVE_TRACE_BRIDGE ", 1)[1]) for x in auth.splitlines()
                 if "OBSERVABILITY_NATIVE_TRACE_BRIDGE " in x)
    (d / "auth.log").write_text(auth + "OBSERVABILITY_NATIVE_TRACE_BRIDGE " + json.dumps(
        {"token": first["token"], "nativeTraceId": "987654321", "service": "auth"}, separators=(",", ":")) + "\n")
    Rr = v2.run(camp, system="teastore")
    md = v2.render(Rr, v2.build_json(Rr))
    c = next(x for x in Rr["cells"] if x["regime"] == TS_NF)
    return (c["readStats"].get("bridgeTokensWithSeveralTraces") == 1 and "bridgeTokensWithSeveralTraces 1" in md
            and v2.build_json(Rr)["readerStats"]["bridgeTokensWithSeveralTraces"] == 1)


def check_json_stamp_unit():
    """F3: only the stamp forms the harness source writes: Envoy start + duration (strings or numbers); a zoned ISO
    `timestamp` (logrus RFC3339Nano); pino's numeric `time` in ms; a zoned ISO `time` / `ts`. Not: a numeric `ts` or
    `timestamp` (no declared unit), a naive ISO string, Envoy's `-`."""
    J = v2.json_stamp
    return (abs(J({"start_time": "1791007201.123", "duration_ms": "12"}) - 1791007201.135) < 1e-6
            and abs(J({"start_time": 1791007201.123, "duration_ms": 12}) - 1791007201.135) < 1e-6
            and J({"start_time": "-", "duration_ms": "12"}) is None
            and abs(J({"timestamp": "2026-10-03T06:00:01.123456789Z"}) - 1791007201.123456) < 1e-6
            and abs(J({"time": 1791007201123}) - 1791007201.123) < 1e-6
            and abs(J({"ts": "2026-10-03T06:00:01+00:00"}) - 1791007201.0) < 1e-6
            and J({"ts": 1791007201.5}) is None and J({"timestamp": 1791007201}) is None
            and J({"time": "2026-10-03 06:00:01"}) is None and J({"message": "x"}) is None)


# ----------------------------------------------------------------------------- decision 57 on both systems

def check_d57_systems():
    """A span's silence-ending observation carries no token of its own on either system: its request is its trace's
    (TeaStore: the bridge; OTel: originalTraceId); Envoy's access-log line names its own."""
    ok = True
    for system, camp, regime, key in (("teastore", TS_CAMP, TS_NF, "auth"), ("otel", OT_CAMP, OT_NF, "frontend")):
        c = _load(system, _cell_dir(camp, regime))
        k = next(k for k in c["spanTok"] if k[0] == key)
        t, toks = next(iter(c["spanTok"][k].items()))
        ok &= v2.silence_tokens(c, "span", k[0], k[1], t) == (sorted(toks), "trace")
    c = _load("otel", _cell_dir(OT_CAMP, OT_NF))
    k = next(k for k in c["logTok"] if k[0] == "frontendproxy")
    t, toks = next(iter(c["logTok"][k].items()))
    return ok and v2.silence_tokens(c, "log", k[0], k[1], t) == (sorted(toks), "observation")


# ----------------------------------------------------------------------------- schemas and validity

SCHEMA_PLANTS = {   # label: (system, regime, file, edit)
    "teastore receipt schemaVersion 3": ("teastore", TS_NF, "receipt.json", lambda d: d.update(schemaVersion=3)),
    "teastore intervention schemaVersion 4": ("teastore", TS_PAUSE, "intervention.json",
                                              lambda d: d.update(schemaVersion=4)),
    "teastore sweep onsetSource": ("teastore", TS_PAUSE, "intervention.json",
                                   lambda d: d["sweep"].update(onsetSource="post-command")),
    "teastore samples kind": ("teastore", TS_NF, "system-samples.json", lambda d: d.update(kind="other-v2")),
    "teastore declared timeout": ("teastore", TS_NF, "receipt.json",
                                  lambda d: d["timing"].update(requestTimeoutSeconds=10.0)),
    "teastore other study epoch": ("teastore", TS_NF, "receipt.json",
                                   lambda d: d.update(studyEpoch="teastore-candidate-pilot-sys-v1")),
    "otel receipt schemaVersion 2": ("otel", OT_NF, "receipt.json", lambda d: d.update(schemaVersion=2)),
    "otel other study epoch": ("otel", OT_NF, "receipt.json",
                               lambda d: d["runKey"].update(studyEpoch="otel-demo-offpath-v1")),
    "otel ledger extra key": ("otel", OT_NF, "request-ledger.json", lambda d: d.update(attempt=2)),
    "otel ledger row key": ("otel", OT_NF, "request-ledger.json", lambda d: d["requests"][0].pop("traceparent")),
    "otel intervention key": ("otel", OT_PAUSE, "intervention.json", lambda d: d.update(dockerEvents=[])),
    "otel declared timeout": ("otel", OT_NF, "request-ledger.json", lambda d: d.update(requestTimeoutSeconds=10.0)),
}


def check_schema_refused(tmp_path, label):
    system, regime, name, edit = SCHEMA_PLANTS[label]
    camp = _copy(TS_CAMP if system == "teastore" else OT_CAMP, tmp_path / ("s-" + hashlib.sha1(label.encode()).hexdigest()))
    _edit_json(_cell_dir(camp, regime) / name, edit)
    try:
        v2.run(camp, system=system)
    except v2.UnknownSchema:
        return True
    return False


def check_ts_bridge_schema(tmp_path):
    camp = _copy(TS_CAMP, tmp_path / "bridge")
    p = _cell_dir(camp, TS_NF) / "auth.log"
    p.write_text(p.read_text() + 'OBSERVABILITY_NATIVE_TRACE_BRIDGE {"token":"journey-x","nativeTraceId":"1",'
                                 '"service":"auth"}\n')
    try:
        v2.run(camp, system="teastore")
    except v2.UnknownSchema:
        return True
    return False


def check_not_scored(tmp_path):
    """A cell the harness did not validate is listed, never scored: TeaStore cellStatus blocked, a .blocked-evidence
    directory; OTel receipt state invalid."""
    camp = _copy(TS_CAMP, tmp_path / "nv-ts")
    _edit_json(_cell_dir(camp, TS_THROTTLE) / "candidate-validation.json", lambda d: d.update(cellStatus="blocked"))
    shutil.copytree(_cell_dir(camp, TS_NF), _cell_dir(camp, TS_NF).parent / "b01-13-full.blocked-evidence")
    Rr = v2.run(camp, system="teastore")
    bad = {(c["regime"], c["reason"].split(" (")[0].split(",")[0]) for c in Rr["cells"] if not c["valid"]}
    camp2 = _copy(OT_CAMP, tmp_path / "nv-ot")
    _edit_json(_cell_dir(camp2, OT_THROTTLE) / "receipt.json", lambda d: d.update(state="invalid", error="planted"))
    R2 = v2.run(camp2, system="otel")
    bad2 = [c["reason"] for c in R2["cells"] if not c["valid"]]
    return (bad == {(TS_THROTTLE, "candidate-validation verdict 'pass'"), (TS_NF, "blocked evidence")}
            and bad2 == ["receipt state 'invalid': planted"]
            and not any(e["regime"] == OT_THROTTLE for e in R2["results"]["primary"]["eps"]))


def test_unknown_system_and_context_restore():
    with pytest.raises(SystemExit):
        with v2.use_system("boutique"):
            pass
    before = (v2.SUT, v2.ENTRY, v2.FAULT_REGIMES, v2.EPISODES, v2.BINDING)
    with v2.use_system("otel"):
        assert (v2.SUT, v2.ENTRY, v2.NOFAULT) == ("otel", "frontendproxy", OT_NF) and v2.EPISODES == 4
    assert (v2.SUT, v2.ENTRY, v2.FAULT_REGIMES, v2.EPISODES, v2.BINDING) == before


# ----------------------------------------------------------------------------- checks, planted defects

CHECKS = {
    "ts-ledger": lambda p: check_ts_ledger(),
    "ts-bridge": lambda p: check_ts_bridge(),
    "ts-receipt": lambda p: check_ts_receipt(),
    "ts-clock-shift": check_ts_clock_shift,
    "ts-samples": lambda p: check_ts_samples(),
    "ts-family-m": lambda p: check_ts_family_m(),
    "ts-probe-trace": check_ts_probe_trace,
    "ts-p1": check_ts_p1,
    "ts-end-to-end": check_ts_end_to_end,
    "ot-ledger": lambda p: check_ot_ledger(),
    "ot-trace-tokens": lambda p: check_ot_trace_tokens(),
    "ot-logs": lambda p: check_ot_logs(),
    "ot-metrics-fault": lambda p: check_ot_metrics_and_fault(),
    "ot-probe-traces": lambda p: check_ot_probe_traces(),
    "ot-p1": lambda p: check_ot_p1(),
    "ot-route-graph": lambda p: check_ot_route_graph(),
    "ot-end-to-end": check_ot_end_to_end,
    "d57-systems": lambda p: check_d57_systems(),
    "ts-bridge-schema": check_ts_bridge_schema,
    "not-scored": check_not_scored,
    # v2.3 (the v2.2 review)
    "ts-loco": check_ts_loco,
    "ot-loco": check_ot_loco,
    "ts-bridge-drops": check_ts_bridge_drops,
    "json-stamp-unit": lambda p: check_json_stamp_unit(),
}


@pytest.mark.parametrize("name", sorted(CHECKS))
def test_check_passes(name, tmp_path):
    assert CHECKS[name](tmp_path), name


@pytest.mark.parametrize("label", sorted(SCHEMA_PLANTS))
def test_unknown_schema_stops_the_run(label, tmp_path):
    assert check_schema_refused(tmp_path, label), label


_REAL_SILENCE_TOKENS = v2.silence_tokens


def _own_token_only(c, ch, svc, tok, ender):
    """Planted defect: the silence-ending observation's own token only (no trace fallback)."""
    return _REAL_SILENCE_TOKENS(dict(c, spanTok={}, logTraceTok={}), ch, svc, tok, ender)


def _no_schema_check(doc, where, expect):
    """Planted defect: no schema check at all."""


MUTANTS = {   # label: (attribute, planted value, checks of which at least one must fail)
    "probe traces read (PROBE_TRACE_RULE)": ("PROBE_TRACE_FILTER", False, ["ts-probe-trace", "ot-probe-traces"]),
    "producer clock taken as the ledger's (CLOCK_RULE_TEASTORE)": ("RECEIPT_CLOCK_MAP", False, ["ts-clock-shift"]),
    "base-run call graph (ROUTE_GRAPH_RULE)": ("ROUTE_GRAPH", False, ["ot-route-graph"]),
    "a span's own token only, no trace fallback (decision 57)": ("silence_tokens", _own_token_only, ["d57-systems"]),
    "held-out quiet cell fitted on itself (H2, F8)": ("LOCO", False, ["ts-loco", "ot-loco"]),
    "json-line record's own stamp dropped (F3)": ("JSON_LINE_STAMP", False, ["ot-logs", "json-stamp-unit"]),
}


@pytest.mark.parametrize("label", sorted(MUTANTS))
def test_planted_reader_defect_is_caught(label, tmp_path, monkeypatch):
    attr, val, names = MUTANTS[label]
    monkeypatch.setattr(v2, attr, val)
    assert any(not CHECKS[n](tmp_path) for n in names), "planted defect not caught: %s" % label


def test_planted_schema_check_removal_is_caught(tmp_path, monkeypatch):
    monkeypatch.setattr(v2, "check_schema", _no_schema_check)
    assert not check_schema_refused(tmp_path, "teastore receipt schemaVersion 3")
    assert not check_schema_refused(tmp_path, "otel receipt schemaVersion 2")


def test_planted_error_answer_branch_off_is_caught(tmp_path, monkeypatch):
    """TeaStore's declared P1 alternative off: the 500-after-2-s episode fails P1."""
    monkeypatch.setitem(v2.P1_ERROR_ANSWER, "teastore", False)
    assert not check_ts_p1(tmp_path)


def test_system_registry_entries_declared_before_reading():
    reg = v2.REGISTRY
    names = ("SYSTEM_TEASTORE", "SYSTEM_OTEL", "CLIENT_TIMEOUT_S_TEASTORE", "CLIENT_TIMEOUT_S_OTEL",
             "ROUTE_SERVICES_TEASTORE", "ROUTE_SERVICES_OTEL", "ROUTE_GRAPH_RULE", "EPISODES_TEASTORE", "EPISODES_OTEL",
             "P2_DOBS_S_TEASTORE", "P2_DOBS_S_OTEL", "P1_ERROR_ANSWER_RULE", "ACTUATOR_READBACK_TEASTORE",
             "ACTUATOR_READBACK_OTEL", "P3_TRAFFIC_INDEPENDENT_TEASTORE", "P3_TRAFFIC_INDEPENDENT_OTEL",
             "AVAILABILITY_SOURCES_TEASTORE", "AVAILABILITY_SOURCES_OTEL", "FAMILY_CHANNELS", "LOG_LAYOUTS",
             "TOKEN_SOURCES", "PROBE_TRACE_RULE", "CLOCK_RULE_TEASTORE", "SCHEMAS", "LOG_TEXT_CHARS")
    for n in names:
        e = reg[n]
        assert e["status"] == "active" and e["origin_type"] != "unknown" and e["origin_ref"], n
        assert "DECLARED BEFORE ANY TeaStore OR OTel CELL IS READ" in e["origin_ref"], n
    for system in ("teastore", "otel"):
        with v2.use_system(system):
            pass
    assert set(names) <= set(v2.PARAMS_USED)         # each is read through param(): the registry, never a literal
    assert reg["SYSTEM_TEASTORE"]["value"]["faultTargets"] == {TS_PAUSE: ["auth", "pause"],
                                                               TS_THROTTLE: ["persistence", "degradation"]}
    assert reg["SYSTEM_OTEL"]["value"]["faultTargets"] == {OT_PAUSE: ["frontend", "pause"],
                                                           OT_THROTTLE: ["productcatalogservice", "degradation"]}
    assert reg["CLIENT_TIMEOUT_S_TEASTORE"]["value"] == reg["CLIENT_TIMEOUT_S_OTEL"]["value"] == 15.0
