"""research/ontology: TBox, SHACL shapes, spec schema + converter, citation checker, competency questions.

Every architecture here is SYNTHETIC (a toy written by this test into a throwaway git repo under pytest's tmp_path):
it exercises the machinery and encodes no fact about any SUT. Each guard is shown failing on a planted defect.
"""
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

ONT = Path(__file__).parents[1] / "research" / "ontology"


def _load(name):
    spec = importlib.util.spec_from_file_location("ontology_" + name, ONT / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(m)
    return m


s2t = _load("spec_to_ttl")
cc = _load("check_citations")
q = _load("query")
EV, OPS = s2t.EV, s2t.OPS


# ============================================================================ synthetic fixture

class Src:
    """Collects one source line per fact, so every fact cites a real (file, line, token)."""

    def __init__(self, repo="toy", file="system.txt"):
        self.repo, self.file, self.lines = repo, file, ["# synthetic source for tests/test_ontology.py"]

    def f(self, value, token=None):
        token = token or str(value)
        self.lines.append("  filler before")
        self.lines.append("line declares %s here" % token)
        self.lines.append("  filler after")
        return {"value": value, "repo": self.repo, "sourceFile": self.file, "line": len(self.lines) - 1,
                "quotedToken": token}


def _git_repo(path, files):
    path.mkdir(parents=True)
    for name, text in files.items():
        (path / name).write_text(text)
    g = ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(g + ["add", "."], check=True)
    subprocess.run(g + ["commit", "-q", "-m", "fixture"], check=True)
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()


def toy_spec(s):
    f = s.f
    svc = lambda name, role="microservice", **kw: dict({"name": f(name, "svc " + name), "role": f(role, "role " + role),
                                                         "container": f("toy-%s-1" % name, "ctr " + name)}, **kw)
    reg_live = {"mechanism": f("heartbeat", "hb-schedule"), "monitors": [f("front", "mon front"), f("back", "mon back")],
                "heartbeatIntervalSeconds": f(2.5, "interval 2500"), "failureTimeoutSeconds": f(10, "alive 10000"),
                "cleanupIntervalSeconds": f(2.5, "cleanup 2500"),
                "heartbeatThreadIndependentOfWork": f(True, "scheduled-executor"),
                "healthCheckConfigured": f(True, "heartbeat-endpoint")}
    k_live = {"mechanism": f("session", "group-session"), "monitors": [f("worker", "mon worker")],
              "heartbeatIntervalSeconds": f(3, "hb 3000"),
              "failureTimeoutSeconds": {"value": 45, "basis": "documented-default",
                                        "sourceUrl": "https://example.invalid/docs#session.timeout.ms",
                                        "note": "client sets no session timeout (synthetic)"},
              "heartbeatThreadIndependentOfWork": f(True, "background-hb-thread")}
    k_live2 = {"mechanism": f("session", "group-session-2"), "monitors": [f("worker2", "mon worker2")],
               "failureTimeoutSeconds": f(30, "timeout 30000"),
               "heartbeatThreadIndependentOfWork": f(False, "hb-in-poll-loop")}
    disc_live = {"mechanism": f("registration", "register-no-check"), "monitors": [f("lonely", "mon lonely")],
                 "failureTimeoutSeconds": f(0, "no-check-timeout"), "healthCheckConfigured": f(False, "Check: nil")}
    return {
        "schemaVersion": 1, "sut": "toy", "sources": {"toy": {"path": "PLACEHOLDER", "commit": "0" * 40}},
        "architecture": {"name": f("toy", "arch toy")},
        "host": {"id": f("hostA", "host hostA")},
        "services": [
            svc("front", registersWith=[f("reg", "register reg")], emits=[{"kind": "span", "id": f("span-front")}]),
            svc("back", registersWith=[f("reg", "register reg 2")], publishesTo=[f("orders", "produce orders")]),
            svc("worker", consumes=[{"topic": f("orders", "consume orders"), "group": f("g1", "group.id g1")}],
                emits=[{"kind": "log", "id": f("log-worker")}]),
            svc("worker2", consumes=[{"topic": f("orders", "consume orders 2"), "group": f("g2", "group.id g2")}]),
            svc("lonely", registersWith=[f("disc", "register disc")]),
            svc("solo"),
            svc("broker", role="broker", exportsTelemetryTo=[f("collector", "otlp collector")],
                emits=[{"kind": "metric", "id": f("lag-g1"), "measuresLagOf": f("g1", "lag of g1")}]),
            svc("registry", role="registry", emits=[{"kind": "log", "id": f("log-removed")}]),
            svc("discovery", role="registry"),
            svc("collector", role="collector", replicas=f(1, "replicas 1")),
        ],
        "syncEdges": [f({"caller": "front", "callee": "back"}, "call back")],
        "topics": [{"name": f("orders", "topic orders"), "broker": f("broker", "bootstrap broker")}],
        "consumerGroups": [{"name": f("g1", "declare g1"), "coordinator": f("kcoord", "coord g1")},
                           {"name": f("g2", "declare g2"), "coordinator": f("kcoord", "coord g2")}],
        "coordinators": [
            {"name": f("reg", "registry reg"), "type": f("ServiceRegistry", "type registry"),
             "hostedBy": f("registry", "hosted registry"), "liveness": [reg_live]},
            {"name": f("kcoord", "group coordinator"), "type": f("ConsumerGroupCoordinator", "type gc"),
             "hostedBy": f("broker", "hosted broker"), "liveness": [k_live, k_live2]},
            {"name": f("disc", "discovery disc"), "type": f("DiscoveryService", "type disc"),
             "hostedBy": f("discovery", "hosted discovery"), "liveness": [disc_live]},
        ],
    }


def nocoord_spec(s):
    f = s.f
    return {"schemaVersion": 1, "sut": "toy2", "sources": {"toy": {"path": "PLACEHOLDER", "commit": "0" * 40}},
            "architecture": {"name": f("toy2", "arch toy2")}, "host": {"id": f("hostB", "host hostB")},
            "services": [{"name": f("x", "svc x"), "role": f("microservice", "role x"), "container": f("toy2-x-1", "ctr x")}],
            "syncEdges": []}


@pytest.fixture(scope="module")
def fixture(tmp_path_factory):
    s = Src()
    spec, spec2 = toy_spec(s), nocoord_spec(s)
    repo = tmp_path_factory.mktemp("ontology") / "toyrepo"
    sha = _git_repo(repo, {s.file: "\n".join(s.lines) + "\n"})
    for sp in (spec, spec2):
        sp["sources"]["toy"] = {"path": str(repo), "commit": sha}
    return {"spec": spec, "spec2": spec2, "repo": repo, "sha": sha}


def _abox(spec):
    return s2t.spec_to_graph(spec)


def _iri(sut, kind, name):
    return URIRef("http://obsplacement.example/sut/%s#%s-%s" % (sut, kind, name))


# ============================================================================ TBox and shapes

def test_tbox_shapes_and_cqs_parse():
    g = q.tbox()
    assert (OPS.callsSync, URIRef("http://www.w3.org/2000/01/rdf-schema#subPropertyOf"),
            URIRef("http://www.semanticweb.org/ontologyOfMicroservicesArchitecture#interactsWith")) in g
    Graph().parse(q.SHAPES, format="turtle")
    for name in q.CQS:
        q.run_cq(name, g)          # parses and runs on the TBox alone (no architecture -> no rows)


def test_omsac_vendor_provenance_digests_match():
    import hashlib
    prov = json.loads((ONT / "vendor" / "omsac" / "PROVENANCE.json").read_text())
    missing = [n for n in prov["sha256"] if not (ONT / "vendor" / "omsac" / n).exists()]
    if missing:  # the BenchSOC artifact keeps only PROVENANCE.json; the vendored third-party files are withheld
        pytest.skip("vendored OMSAC files withheld: %d of %d absent" % (len(missing), len(prov["sha256"])))
    for name, digest in prov["sha256"].items():
        assert hashlib.sha256((ONT / "vendor" / "omsac" / name).read_bytes()).hexdigest() == digest, name
    assert prov["commit"] == "92ca7f766f8164cf130d34756fbd04d113e13781"


# ============================================================================ schema + converter

def test_schema_accepts_fixture_and_rejects_bad_facts(fixture):
    s2t.validate_spec(fixture["spec"])
    bad = copy.deepcopy(fixture["spec"])
    bad["host"]["id"] = {"value": "hostA"}                                         # no provenance
    with pytest.raises(jsonschema.ValidationError):
        s2t.validate_spec(bad)
    bad = copy.deepcopy(fixture["spec"])
    bad["host"]["id"]["sourceUrl"] = "https://example.invalid"                    # both cited and default
    with pytest.raises(jsonschema.ValidationError):
        s2t.validate_spec(bad)


def test_conversion_is_deterministic(fixture):
    assert s2t.spec_to_turtle(fixture["spec"]) == s2t.spec_to_turtle(copy.deepcopy(fixture["spec"]))


def test_shacl_conforms_on_fixture(fixture):
    for sp in (fixture["spec"], fixture["spec2"]):
        ok, text = q.validate(_abox(sp))
        assert ok, text


def test_shacl_planted_consumer_without_group(fixture):
    sp = copy.deepcopy(fixture["spec"])
    w2 = next(x for x in sp["services"] if x["name"]["value"] == "worker2")
    del w2["consumes"][0]["group"]
    ok, text = q.validate(_abox(sp))
    assert not ok and "memberOf" in text and "svc-worker2" in text


def test_shacl_planted_fact_without_evidence(fixture):
    g = _abox(fixture["spec"])
    s, p, o = _iri("toy", "svc", "front"), OPS.callsSync, _iri("toy", "svc", "back")
    assert (s, p, o) in g
    for e in list(g.subjects(EV.aboutSubject, s)):
        if (e, EV.aboutPredicate, p) in g:
            g.remove((e, None, None))
    ok, text = q.validate(g)
    assert not ok and "without an ev:Evidence" in text


def test_shacl_planted_liveness_without_timeout_and_two_containers(fixture):
    sp = copy.deepcopy(fixture["spec"])
    del sp["coordinators"][0]["liveness"][0]["failureTimeoutSeconds"]
    ok, text = q.validate(_abox(sp))
    assert not ok and "failureTimeoutSeconds" in text
    g = _abox(fixture["spec"])
    extra = _iri("toy", "ctr", "second")
    f = {"repo": "toy", "sourceFile": "system.txt", "line": 2, "quotedToken": "x"}
    b = s2t.Builder(fixture["spec"])
    b.g = g
    b.fact(extra, RDF.type, OPS.Container, f)
    b.fact(extra, OPS.placedOn, _iri("toy", "host", "hostA"), f)
    b.fact(_iri("toy", "svc", "front"), OPS.runsIn, extra, f)
    ok, text = q.validate(g)
    assert not ok and "runsIn" in text


def test_shacl_planted_dangling_group_reference(fixture):
    sp = copy.deepcopy(fixture["spec"])
    sp["consumerGroups"] = [c for c in sp["consumerGroups"] if c["name"]["value"] != "g2"]
    ok, text = q.validate(_abox(sp))
    assert not ok and "group-g2" in text


# ============================================================================ citation checker

def test_citations_ok_on_fixture(fixture):
    res = cc.check_spec(fixture["spec"])
    assert res["ok"], [r for r in res["rows"] if r["status"] == "fail"]
    assert res["counts"].get("unchecked-default") == 1          # the documented 45 s default is never reported ok
    assert res["counts"]["ok"] == res["facts"] - 1


def test_citation_tolerance_is_plus_minus_two(fixture):
    sp = copy.deepcopy(fixture["spec"])
    sp["host"]["id"]["line"] += 2
    assert cc.check_spec(sp)["ok"]


@pytest.mark.parametrize("plant", ["line+5", "token", "file", "commit", "repo"])
def test_citation_planted_defects_fail(fixture, plant):
    sp = copy.deepcopy(fixture["spec"])
    f = sp["host"]["id"]
    if plant == "line+5":
        f["line"] += 5
    elif plant == "token":
        f["quotedToken"] = "host hostZ"
    elif plant == "file":
        f["sourceFile"] = "missing.txt"
    elif plant == "commit":
        sp["sources"]["toy"]["commit"] = "1" * 40
    elif plant == "repo":
        f["repo"] = "nope"
    res = cc.check_spec(sp)
    assert not res["ok"]
    assert any(r["status"] == "fail" and r["path"] == "$.host.id" for r in res["rows"])


def test_citation_reads_the_pinned_commit_not_the_worktree(fixture, tmp_path):
    sp = copy.deepcopy(fixture["spec"])
    s = Src()
    toy_spec(s)
    repo = tmp_path / "moved"
    sha = _git_repo(repo, {s.file: "\n".join(s.lines) + "\n"})
    (repo / s.file).write_text("rewritten after the commit\n")             # working tree no longer has the tokens
    sp["sources"]["toy"] = {"path": str(repo), "commit": sha}
    assert cc.check_spec(sp)["ok"]


# ============================================================================ competency questions

@pytest.fixture(scope="module")
def graph(fixture):
    return q.load(_abox(fixture["spec"]), _abox(fixture["spec2"]))


def _c1(graph, target, kind):
    rows = q.run_cq("C1", graph, target, kind)
    assert len(rows) == 1, rows
    return rows[0]["class"]


@pytest.mark.parametrize("target,kind,expected", [
    ("front", "pause", "tracked"),
    ("front", "crash", "tracked"),
    ("front", "cpuThrottle", "heartbeat-stays-alive"),
    ("front", "netDelay", "heartbeat-stays-alive"),
    ("worker", "pause", "tracked"),
    ("worker", "cpuThrottle", "heartbeat-stays-alive"),
    ("worker2", "cpuThrottle", "heartbeat-coupled-to-work"),
    ("worker2", "pause", "tracked"),
    ("lonely", "pause", "no-liveness-check"),
    ("solo", "pause", "not-a-member"),
    ("x", "pause", "no-coordinator"),
])
def test_cq_c1_classes(graph, target, kind, expected):
    assert _c1(graph, target, kind) == expected


def test_cq_c1_enumerates_every_member_and_kind(graph):
    rows = q.run_cq("C1", graph)
    assert len(rows) == (10 + 1) * 4                     # (toy services + toy2 services) x 4 fault kinds


def test_cq_l2_windows(graph):
    (r,) = q.run_cq("L2", graph, "front", "pause")
    assert (float(r["low"]), float(r["high"]), float(r["phaseLow"])) == (10.0, 12.5, 7.5)
    (r,) = q.run_cq("L2", graph, "worker", "pause")
    assert (float(r["low"]), float(r["high"]), float(r["phaseLow"])) == (45.0, 45.0, 42.0)
    assert q.run_cq("L2", graph, "front", "cpuThrottle") == []     # no heartbeat-stopping kind -> no window
    assert q.run_cq("L2", graph, "lonely", "pause") == []          # registration without a check -> no window


def test_cq_l1_lanes_and_consistency_with_c1(graph):
    (r,) = q.run_cq("L1", graph, "worker", "pause")
    assert (r["ownLane"], r["coordinatorLane"], r["coordinatorEmits"], r["lagLane"]) == (True, True, True, True)
    (r,) = q.run_cq("L1", graph, "worker2", "pause")
    assert (r["ownLane"], r["lagLane"]) == (False, False)          # emits nothing; g2 has no lag metric
    c1 = {(r["target"], r["kind"]): r["class"] for r in q.run_cq("C1", graph)}
    for r in q.run_cq("L1", graph):
        assert r["coordinatorLane"] == (c1[(r["target"], r["kind"])] == "tracked"), r


def test_cq_b1_blast_radius(graph):
    got = {(r["effect"], r["affected"]) for r in q.run_cq("B1", graph, "back")}
    assert got == {("sync-caller", "svc-front"), ("starved", "svc-worker"), ("starved", "svc-worker2")}
    assert {(r["effect"], r["affected"]) for r in q.run_cq("B1", graph, "worker")} == {("backlog", "group-g1")}
    assert {(r["effect"], r["affected"]) for r in q.run_cq("B1", graph, "broker")} == {
        ("broker-client", "svc-back"), ("broker-client", "svc-worker"), ("broker-client", "svc-worker2")}


def test_cq_s1_shared_fate(graph):
    groups = {}
    for r in q.run_cq("S1", graph):
        groups.setdefault((r["anchorType"], r["anchor"]), set()).add(r["member"])
    assert len(groups[("Host", "host-hostA")]) == 10 and groups[("Host", "host-hostB")] == {"svc-x"}
    assert groups[("Collector", "svc-collector")] == {"svc-broker"}
    assert groups[("Broker", "svc-broker")] == {"svc-back", "svc-worker", "svc-worker2"}
    assert groups[("Coordinator", "coord-reg")] == {"svc-front", "svc-back"}
    assert groups[("Coordinator", "coord-kcoord")] == {"svc-worker", "svc-worker2"}
