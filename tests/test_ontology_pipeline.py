"""research/ontology pipeline: inputs, stage 1, merge (stage 3), judge packets / application (stage 4), run record.

Synthetic fixtures (throwaway git repos under pytest's tmp_path) exercise the machinery; each guard is shown failing
on a planted defect. The last tests read the real pinned SUT trees in the sibling worktrees and are skipped when those
are absent; they assert only machinery properties (every stage-1 citation checks), never an ontology fact.
"""
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ONT = Path(__file__).parents[1] / "research" / "ontology"
sys.path.insert(0, str(ONT))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ONT / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


inputs = _load("inputs")
cc = _load("check_citations")
s1 = _load("extract_stage1")
mg = _load("merge")
ji = _load("judge_inputs")
aj = _load("apply_judge")
rr = _load("run_record")


def _git_repo(path, files):
    path.mkdir(parents=True)
    for name, text in files.items():
        p = path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    g = ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(g + ["add", "."], check=True)
    subprocess.run(g + ["commit", "-q", "-m", "fixture"], check=True)
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()

# ============================================================================ synthetic spec fixture


COMPOSE = """services:
  front:
    image: toy/front
    environment:
      BACK_ADDR: "back:9000"
  back:
    image: toy/back
    container_name: toy-back
  queue:
    image: toy/queue
"""
CODE = """// synthetic
conn = dial("back:9000")      // line 2
publish("orders")             // line 3
heartbeat(2500)               // line 4
// filler 5
// filler 6
// filler 7
// filler 8
// filler 9
"""


@pytest.fixture()
def toy(tmp_path):
    commit = _git_repo(tmp_path / "toy", {"compose.yml": COMPOSE, "src/front.txt": CODE})
    src = {"toy": {"path": str(tmp_path / "toy"), "commit": commit}}

    def c(value, file, line, token, **kw):
        return dict(value=value, repo="toy", sourceFile=file, line=line, quotedToken=token, **kw)

    def svc(name, line, ctr):
        return {"name": c(name, "compose.yml", line, name + ":"), "role": c("microservice", "compose.yml", line + 1,
                                                                             "image:"),
                "container": c(ctr, "compose.yml", line, name + ":")}

    base = {"schemaVersion": 1, "sut": "toy", "sources": src,
            "architecture": {"name": c("toy", "compose.yml", 1, "services:")},
            "host": {"id": c("hostx", "compose.yml", 1, "services:")},
            "services": [svc("front", 2, "front"), svc("back", 6, "toy-back")]}
    stage1 = copy.deepcopy(base)
    stage1["syncEdges"] = [c({"caller": "front", "callee": "back"}, "compose.yml", 5, 'BACK_ADDR: "back:9000"')]
    A = copy.deepcopy(base)
    A["syncEdges"] = [c({"caller": "front", "callee": "back:9000"}, "src/front.txt", 2, 'dial("back:9000")')]
    A["services"][0]["publishesTo"] = [c("orders", "src/front.txt", 3, 'publish("orders")')]
    B = copy.deepcopy(base)
    B["syncEdges"] = [c({"caller": "front", "callee": "toy-back"}, "src/front.txt", 2, "dial")]
    aliases = {"front": "front", "back": "back", "toy-back": "back", "queue": "queue"}
    return {"root": tmp_path, "stage1": stage1, "A": A, "B": B, "aliases": aliases, "c": c}


def _merge(t, A=None, B=None):
    return mg.merge(t["stage1"], [A if A is not None else t["A"]], [B if B is not None else t["B"]], t["aliases"],
                    root=t["root"])


def _ids(mr, rel):
    return {g["id"]: g for g in mr["agreed"] + mr["contested"] if g["relation"] == rel}

# ============================================================================ stage 3: citations + merge


def test_merge_agrees_across_alias_forms_and_contests_singletons(toy):
    mr = _merge(toy)
    edges = _ids(mr, "callsSync")
    assert len(edges) == 1, "back, back:9000 and toy-back must normalise to the compose service 'back'"
    g = next(iter(edges.values()))
    assert g["origins"] == ["A", "B", "stage1"] and g in mr["agreed"]
    pub = _ids(mr, "publishesTo")
    assert [x["origins"] for x in pub.values()] == [["A"]] and next(iter(pub.values())) in mr["contested"]
    assert mr["log"]["droppedCount"] == {"A": 0, "B": 0, "stage1": 0}
    by = mr["agreement"]["byRelation"]
    assert by["publishesTo"] == {"agreed": 0, "contested": 1, "deterministic": 0, "agreement": 0.0}
    assert by["callsSync"]["agreement"] == 1.0


def test_planted_wrong_line_is_dropped_and_counted(toy):
    A = copy.deepcopy(toy["A"])
    A["services"][0]["publishesTo"][0]["line"] = 8  # the token is on line 3, the planted line 8 is +-2 of 6..10
    mr = _merge(toy, A=A)
    assert mr["log"]["droppedCount"]["A"] == 1
    assert [d["relation"] for d in mr["log"]["dropped"]] == ["publishesTo"]
    assert not _ids(mr, "publishesTo"), "a dropped fact must not reach the merge"
    # control: the unplanted fact is kept
    assert _ids(_merge(toy), "publishesTo")


def test_planted_wrong_token_and_wrong_commit_are_dropped(toy):
    A = copy.deepcopy(toy["A"])
    A["syncEdges"][0]["quotedToken"] = "connect(back)"
    mr = _merge(toy, A=A)
    assert mr["log"]["droppedCount"]["A"] == 1
    # an extractor that names another commit is re-checked at the pinned one, not trusted
    B = copy.deepcopy(toy["B"])
    B["sources"] = {"toy": {"path": B["sources"]["toy"]["path"], "commit": "0" * 40}}
    mr2 = _merge(toy, B=B)
    assert mr2["log"]["sourcesReplaced"] and mr2["log"]["droppedCount"]["B"] == 0


def test_schema_invalid_extractor_output_contributes_nothing(toy):
    B = copy.deepcopy(toy["B"])
    B["services"][0]["role"]["value"] = "wizard"
    mr = _merge(toy, B=B)
    assert len(mr["log"]["schemaRejected"]) == 1
    assert all("B" not in g["origins"] for g in mr["agreed"] + mr["contested"])


def test_extractor_fragment_without_architecture_host_role_is_accepted(toy):
    frag = {"schemaVersion": 1, "sut": "toy", "sources": toy["A"]["sources"],
            "services": [{"name": toy["A"]["services"][0]["name"],
                          "publishesTo": toy["A"]["services"][0]["publishesTo"]}]}
    mr = _merge(toy, A=frag, B=copy.deepcopy(frag))
    assert not mr["log"]["schemaRejected"]
    assert [g["origins"] for g in _ids(mr, "publishesTo").values()] == [["A", "B"]]
    # planted: the same fragment with an invalid fact is still rejected
    bad = copy.deepcopy(frag)
    bad["services"][0]["publishesTo"][0].pop("quotedToken")
    assert len(_merge(toy, A=bad)["log"]["schemaRejected"]) == 1
    # a fragment is not a final spec
    assert mg.validate(frag)


def test_empty_extractors_leave_everything_contested(toy):
    mr = mg.merge(toy["stage1"], [], [], toy["aliases"], root=toy["root"])
    assert mr["agreement"]["agreed"] == 0 and mr["agreement"]["contested"] > 0
    spec, log = mg.rebuild(mr, {g["id"] for g in mr["agreed"]})
    assert spec["services"] == [] and mg.validate(spec), "nothing agreed -> no valid ontology spec"

# ============================================================================ stage 4: judge


def _packets_answers(toy, verdict_for):
    mr = _merge(toy)
    ps = ji.packets(mr, root=toy["root"])
    ans = []
    for p in ps:
        v = verdict_for(p)
        if v is not None:
            ans.append({"id": p["id"], "packetDigest": p["packetDigest"], "verdict": v, "reason": "synthetic."})
    return mr, ps, ans


def _write(tmp, name, obj):
    p = tmp / name
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj))
    return p


def _jsonl(tmp, name, rows):
    return _write(tmp, name, "".join(json.dumps(r) + "\n" for r in rows))


def test_packets_carry_cited_context(toy):
    mr = _merge(toy)
    ps = ji.packets(mr, root=toy["root"])
    assert {p["id"] for p in ps} == {g["id"] for g in mr["contested"]}
    pub = next(p for p in ps if p["relation"] == "publishesTo")
    ev = pub["evidence"][0]
    assert ev["line"] == 3 and any(c["n"] == 3 and 'publish("orders")' in c["text"] for c in ev["context"])
    assert "expected" not in json.dumps(pub).lower()


@pytest.mark.parametrize("verdict", ["not supported", "not decidable", None])
def test_contested_fact_needs_supported_to_enter_final_spec(toy, tmp_path, verdict):
    mr, ps, ans = _packets_answers(toy, lambda p: verdict)
    d = tmp_path / ("j-%s" % (verdict or "none").replace(" ", "_"))
    d.mkdir()
    out = d / "final.json"
    spec, dec, errs = aj.apply(_write(d, "merge.json", mr), _jsonl(d, "p.jsonl", ps), _jsonl(d, "a.jsonl", ans),
                               "synthetic-judge", "t-run", out, d / "LOG.md")
    assert "publishesTo" not in json.dumps(spec["services"]), "contested fact entered without a 'supported'"
    assert all(d_["verdict"] == (verdict or "no answer") for d_ in dec)
    # the agreed facts (A and B both) are in
    assert spec.get("syncEdges") and "architecture" in spec and errs == []


def test_supported_contested_fact_enters_and_log_is_append_only(toy, tmp_path):
    mr, ps, ans = _packets_answers(toy, lambda p: "supported")
    files = (_write(tmp_path, "merge.json", mr), _jsonl(tmp_path, "p.jsonl", ps), _jsonl(tmp_path, "a.jsonl", ans))
    log = tmp_path / "LOG.md"
    spec, dec, errs = aj.apply(*files, "synthetic-judge", "run-1", tmp_path / "f1.json", log)
    front = next(x for x in spec["services"] if x["name"]["value"] == "front")
    assert errs == [] and front["publishesTo"][0]["value"] == "orders"
    first = log.read_text()
    with pytest.raises(SystemExit, match="already in"):
        aj.apply(*files, "synthetic-judge", "run-1", tmp_path / "f2.json", log)
    assert log.read_text() == first, "a refused run must not touch the log"
    aj.apply(*files, "synthetic-judge", "run-2", tmp_path / "f3.json", log)
    assert log.read_text().startswith(first), "append-only: the earlier section is a prefix"
    with pytest.raises(SystemExit, match="overwrite"):
        aj.apply(*files, "synthetic-judge", "run-3", tmp_path / "f3.json", log)


@pytest.mark.parametrize("defect", ["digest", "unknown-id", "verdict", "duplicate", "edited-packet", "reason"])
def test_judge_answer_defects_refuse(toy, tmp_path, defect):
    mr, ps, ans = _packets_answers(toy, lambda p: "supported")
    if defect == "digest":
        ans[0]["packetDigest"] = "f" * 64
    elif defect == "unknown-id":
        ans[0]["id"] = "0" * 16
    elif defect == "verdict":
        ans[0]["verdict"] = "probably"
    elif defect == "duplicate":
        ans.append(dict(ans[0]))
    elif defect == "edited-packet":
        ps[0]["evidence"][0]["quotedToken"] = "something else"
    elif defect == "reason":
        ans[0]["reason"] = " "
    log = tmp_path / "LOG.md"
    with pytest.raises(SystemExit):
        aj.apply(_write(tmp_path, "m.json", mr), _jsonl(tmp_path, "p.jsonl", ps), _jsonl(tmp_path, "a.jsonl", ans),
                 "j", "r", tmp_path / "f.json", log)
    assert not log.exists() and not (tmp_path / "f.json").exists()

# ============================================================================ run record: prompt pin


def test_prompt_pin_matches_protocol_and_changed_prompt_refuses():
    text = rr.PROTOCOL.read_text()
    assert rr.check_prompt(text) == rr.PROMPT_SHA256
    block = rr.prompt_block(text)
    assert block.startswith("You extract facts about one service") and "```" not in block
    for planted in (text.replace("Do not infer from names alone.", "Infer freely."),
                    text.replace("(5) where it", "(5)  where it"),
                    text.replace("```\nYou extract", "```\n\nYou extract")):
        assert planted != text
        with pytest.raises(SystemExit, match="REFUSING"):
            rr.check_prompt(planted)
    # text outside the block may change without refusing (it is hashed separately into run.json)
    assert rr.check_prompt(text.replace("## Stage 3", "## Stage 3 ")) == rr.PROMPT_SHA256

# ============================================================================ inputs / stage 1 units


def test_dockerfile_sources_and_from():
    df = """FROM golang:1.22 AS b
COPY ["/src/svc/", "Svc/"]
COPY --from=b /out /app
COPY ./a ./b* ./
ADD https://example.invalid/x.jar /x.jar
RUN --mount=type=cache,target=/c \\
    --mount=type=bind,source=./src/svc/go.mod,target=go.mod \\
    go build
COPY $X /y
FROM alpine
"""
    srcs, froms = inputs.copy_sources(df)
    assert [s for s, _ in srcs] == ["/src/svc/", "./a", "./b*", "./src/svc/go.mod"]
    assert [f for f, _ in froms] == ["golang:1.22", "alpine"]


def test_interpolation_and_unresolved():
    env = {"HOST": ("otelcol", 3), "PORT": ("4317", 4), "EP": ("http://${HOST}:${PORT}", 5)}
    v, used, unres = inputs.interpolate("${EP}/x ${MISSING:?set it} ${D:-dflt} $$", env)
    assert v == "http://otelcol:4317/x ${MISSING:?set it} dflt $"
    assert unres == ["MISSING"] and ("HOST", 3) in used


def test_exclusion_rules(tmp_path):
    commit = _git_repo(tmp_path / "r", {
        "a/x_test.go": "package a", "a/x.pb.go": "package a", "a/y.go": "// Code generated by protoc. DO NOT EDIT.\n",
        "a/z.go": "package a", "vendor/m/m.go": "package m", "README.md": "", "s/src/test/T.java": "",
        "k/key.pem": "-----", "w/lib.js": "x", "w/lib.min.js": "x", "w/app.js": "x", "go.sum": "", ".eslintrc": ""})
    r = inputs.Repo("r", str(tmp_path / "r"), commit)
    got = {p: inputs.exclusion(r, p) for p in r.tree()}
    assert got == {"a/x_test.go": "test", "a/x.pb.go": "generated-stub", "a/y.go": "generated-stub", "a/z.go": None,
                   "vendor/m/m.go": "vendored", "README.md": "doc", "s/src/test/T.java": "test",
                   "k/key.pem": "key-material", "w/lib.js": "vendored", "w/lib.min.js": "vendored", "w/app.js": None,
                   "go.sum": "lockfile", ".eslintrc": "tooling-dotfile"}


def test_go_closure_follows_only_in_module_imports(tmp_path):
    files = {
        "go.mod": "module example.invalid/m\n\ngo 1.21\n",
        "cmd/a/main.go": 'package main\nimport (\n "example.invalid/m/lib"\n "fmt"\n)\nfunc main(){ lib.F(); fmt.Println() }\n',
        "cmd/b/main.go": 'package main\nimport "example.invalid/m/other"\nfunc main(){ other.G() }\n',
        "lib/lib.go": 'package lib\nimport "example.invalid/m/deep"\nfunc F(){ deep.H() }\n',
        "deep/d.go": "package deep\nfunc H(){}\n",
        "other/o.go": "package other\nfunc G(){}\n",
    }
    commit = _git_repo(tmp_path / "g", files)
    r = inputs.Repo("g", str(tmp_path / "g"), commit)
    keep, dirs, _ = inputs.go_closure(r, sorted(r.tree()), "cmd/a", "")
    assert keep == ["cmd/a/main.go", "deep/d.go", "lib/lib.go"]


def test_ast_hits_resolve_imports_and_constants(tmp_path):
    go = b'''package s
import (
  "google.golang.org/grpc"
  pb "example.invalid/m/proto"
  "os"
)
const name = "srv-x"
func f(name string) {
  conn, _ := grpc.Dial(os.Getenv("ADDR"), grpc.WithInsecure())
  _ = pb.NewThingClient(conn)
  g(name)
}
'''
    a = s1.FileAst("r", "s.go", "go", go)
    hs = {h["value"]: h for h in a.hits()}
    assert "grpc.Dial" in hs and hs["grpc.Dial"]["matches"][0]["match"] == "qualified"
    assert "os.Getenv" in hs and hs["os.Getenv"]["literals"][0]["value"] == '"ADDR"'
    assert "grpc.WithInsecure" not in hs, "not a catalogued call"
    assert "pb.NewThingClient" not in hs, "an unknown in-tree package is not a stub without its generated files"
    cs = b'''using Confluent.Kafka;
class C {
  private const string Topic = "orders";
  void M() { var c = new ConsumerBuilder<string, byte[]>(new ConsumerConfig { GroupId = "g1" }).Build();
             c.Subscribe(Topic); }
}
'''
    a = s1.FileAst("r", "C.cs", "csharp", cs)
    vals = {h["value"]: h for h in a.hits()}
    sub = next(h for v, h in vals.items() if v.endswith("Subscribe"))
    assert sub["literals"][0]["kind"] == "resolvedConstant" and sub["literals"][0]["value"] == '"orders"'
    # the inner ConsumerConfig construction is nested in the outer ConsumerBuilder call's arguments, so both are kept
    assert any("ConsumerConfig" in v for v in vals)
    # planted: the same Subscribe without the Kafka using-directive is not a hit
    a2 = s1.FileAst("r", "C.cs", "csharp", cs.replace(b"using Confluent.Kafka;", b""))
    assert not any(v.endswith("Subscribe") for v in (h["value"] for h in a2.hits()))


def test_parameter_shadows_same_file_constant():
    go = b'''package s
import "os"
const key = "CONST"
func f(key string) { os.Getenv(key) }
func g() { os.Getenv(key) }
'''
    hs = s1.FileAst("r", "s.go", "go", go).hits()
    lits = [h["literals"] for h in hs]
    assert lits[0] == [] and lits[1][0]["value"] == '"CONST"'

# ============================================================================ real pinned trees (skipped if absent)


SIBLINGS = all((inputs.ROOT / v["sources"]["upstream"]["path"]).exists() for v in inputs.SYSTEMS.values())


@pytest.mark.skipif(not SIBLINGS, reason="sibling runtime worktrees with the pinned SUT trees are absent")
@pytest.mark.parametrize("system", sorted(rr.DRY_RUN_SERVICES))
def test_stage1_citations_all_check_on_pinned_trees(system):
    spec = s1.build_stage1(system, [rr.DRY_RUN_SERVICES[system]])
    import spec_to_ttl
    spec_to_ttl.validate_spec(spec)
    facts = cc.check_spec(spec)
    obs = s1.check_observations(spec)
    assert facts["counts"].get("fail", 0) == 0 and obs["counts"].get("fail", 0) == 0
    assert facts["counts"].get("ok", 0) >= 5 and obs["facts"] > 0
    # planted: shift one fact off its line by 10 -> the same checker fails it
    bad = copy.deepcopy(spec)
    bad["services"][0]["name"]["line"] += 10
    assert cc.check_spec(bad)["counts"].get("fail", 0) == 1


@pytest.mark.skipif(not SIBLINGS, reason="sibling runtime worktrees with the pinned SUT trees are absent")
def test_manifest_hashes_match_git_blobs():
    m = inputs.build_manifest("otel")
    repos = inputs.open_repos("otel")
    for f in m["files"][:25]:
        assert inputs.sha256(repos[f["repo"]].read(f["path"])) == f["sha256"]
    assert all(len(v["commit"]) == 40 for v in m["sources"].values())
    b = m["services"]["accountingservice"]
    assert any(f["path"] == "pb/demo.proto" for f in b["files"]), "Dockerfile COPY of /pb/demo.proto (R3b)"
    assert not any(f["path"].endswith("README.md") for f in m["files"])

# ============================================================================ Amendment 2: deterministic stage-1 facts


HOSTS = '{\n "hosts": [\n  {\n   "hostId": "hostx",\n   "role": "toy host"\n  }\n ]\n}\n'


@pytest.fixture()
def det(tmp_path):
    commit = _git_repo(tmp_path / "toy", {"compose.yml": COMPOSE, "src/front.txt": CODE,
                                          "research/host-topology.json": HOSTS})
    src = {"toy": {"path": str(tmp_path / "toy"), "commit": commit}}

    def c(value, file, line, token, note=None):
        f = dict(value=value, repo="toy", sourceFile=file, line=line, quotedToken=token)
        if note:
            f["note"] = note
        return f

    D3 = {"value": 1, "basis": "documented-default", "sourceUrl": "https://docs.docker.com/reference/compose-file/deploy/#replicas",
          "note": "stage-1 rule D3: no deploy.replicas or scale; Compose default 1"}
    stage1 = {"schemaVersion": 1, "sut": "toy", "sources": src,
              "architecture": {"name": c("toy", "compose.yml", 1, "services:", "architecture = the services of compose.yml")},
              "host": {"id": c("hostx", "research/host-topology.json", 4, '"hostId": "hostx"', "one host per system")},
              "services": [
                  {"name": c("front", "compose.yml", 2, "front:"),
                   "role": c("microservice", "compose.yml", 3, "toy/front", "stage-1 rule D1: image-only service"),
                   "container": c("front", "compose.yml", 2, "front:", "stage-1 rule D2: container_name not set"),
                   "replicas": dict(D3)},
                  {"name": c("back", "compose.yml", 6, "back:"),
                   "role": c("other", "compose.yml", 7, "toy/back", "stage-1 rule D1: image-only service"),
                   "container": c("toy-back", "compose.yml", 8, "container_name: toy-back"),
                   "replicas": dict(D3)}],
              "syncEdges": [c({"caller": "front", "callee": "back"}, "compose.yml", 5, 'BACK_ADDR: "back:9000"',
                              "stage-1 rule D4: environment BACK_ADDR=back:9000")]}
    aliases = {"front": "front", "back": "back", "toy-back": "back", "queue": "queue"}
    return {"root": tmp_path, "stage1": stage1, "aliases": aliases}


def _rel_groups(mr, cls, rel):
    return [g for g in mr[cls] if g["relation"] == rel]


def test_rule_derived_stage1_facts_enter_as_deterministic_without_judge(det, tmp_path):
    mr = mg.merge(det["stage1"], [], [], det["aliases"], root=det["root"])
    rules = sorted(g["deterministicRule"] for g in mr["deterministic"])
    assert rules == ["architecture-name", "container-service-key", "host-topology", "replicas-default-1",
                     "replicas-default-1", "role-image-lookup", "role-image-lookup"]
    # not rule-derived: the env sync edge (D4), a container cited from container_name, and service existence
    assert _rel_groups(mr, "contested", "callsSync") and _rel_groups(mr, "contested", "container")
    assert {g["relation"] for g in mr["contested"]} == {"callsSync", "container", "service"}
    ps = ji.packets(mr, root=det["root"])
    assert {p["id"] for p in ps} == {g["id"] for g in mr["contested"]}, "deterministic facts get no packet"
    assert mr["agreement"]["agreement"] == 0.0 and mr["agreement"]["reportable"]["keys"] == 7
    # judge answers 'not supported' for everything contested: architecture/host still enter, edge does not
    ans = [{"id": p["id"], "packetDigest": p["packetDigest"], "verdict": "not supported", "reason": "x."} for p in ps]
    spec, dec, errs = aj.apply(_write(tmp_path, "m.json", mr), _jsonl(tmp_path, "p.jsonl", ps),
                               _jsonl(tmp_path, "a.jsonl", ans), "j", "det-1", tmp_path / "f.json", tmp_path / "L.md")
    assert spec["architecture"]["name"]["acceptance"] == "deterministic"
    assert spec["host"]["id"]["acceptance"] == "deterministic"
    assert "syncEdges" not in spec, "a non-rule stage-1 fact needs agreement or the judge"
    assert spec["services"] == [] and errs, "service existence is not a rule-derived fact"
    # with 'supported' for the service names and the cited container, the spec validates and carries labels
    ans2 = [{"id": p["id"], "packetDigest": p["packetDigest"],
             "verdict": "supported" if p["relation"] in ("service", "container") else "not supported", "reason": "x."}
            for p in ps]
    spec2, _, errs2 = aj.apply(_write(tmp_path, "m.json", mr), _jsonl(tmp_path, "p.jsonl", ps),
                               _jsonl(tmp_path, "a2.jsonl", ans2), "j", "det-2", tmp_path / "f2.json", tmp_path / "L.md")
    assert errs2 == []
    front = next(x for x in spec2["services"] if x["name"]["value"] == "front")
    assert front["role"]["acceptance"] == front["container"]["acceptance"] == front["replicas"]["acceptance"] == \
        "deterministic" and front["name"]["acceptance"] == "supported"
    import spec_to_ttl
    from rdflib import Literal
    g = spec_to_ttl.spec_to_graph(spec2)
    assert (None, spec_to_ttl.EV.acceptance, Literal("deterministic")) in g
    assert (None, spec_to_ttl.EV.acceptance, Literal("supported")) in g


def test_planted_rule_derived_fact_with_failing_citation_is_dropped(det):
    bad = copy.deepcopy(det["stage1"])
    bad["services"][0]["role"]["line"] = 9          # 'toy/front' is on line 3; +-2 of 9 misses it
    bad["host"]["id"]["quotedToken"] = '"hostId": "hosty"'   # token not in the file
    mr = mg.merge(bad, [], [], det["aliases"], root=det["root"])
    assert mr["log"]["droppedCount"]["stage1"] == 2
    rules = [g["deterministicRule"] for g in mr["deterministic"]]
    assert "host-topology" not in rules and rules.count("role-image-lookup") == 1
    assert not any(g["relation"] == "id" for g in mr["agreed"] + mr["contested"] + mr["deterministic"])


def test_planted_rule_label_outside_the_five_rules_stays_contested(det):
    bad = copy.deepcopy(det["stage1"])
    bad["syncEdges"][0]["note"] = "stage-1 rule D1: planted label on an edge"
    bad["architecture"]["name"]["value"] = "not-the-sut"          # rule requires value == system id
    bad["services"][1]["container"]["note"] = "stage-1 rule D2: planted on a container_name citation"
    mr = mg.merge(bad, [], [], det["aliases"], root=det["root"])
    rels = {g["relation"]: g for g in mr["deterministic"]}
    assert "callsSync" not in rels and "name" not in rels
    assert _rel_groups(mr, "contested", "callsSync") and _rel_groups(mr, "contested", "name")
    # a D2 note on a container_name citation is not the D2 rule (value must be the service key, cited on its key line)
    back_ctr = [g for g in mr["deterministic"] if g["relation"] == "container" and g["key"][0] == "back"]
    assert not back_ctr and any(g["key"][0] == "back" for g in _rel_groups(mr, "contested", "container"))


def test_agreed_beats_deterministic_and_reportable_agreement(det):
    A = {"schemaVersion": 1, "sut": "toy", "sources": det["stage1"]["sources"],
         "services": [{"name": det["stage1"]["services"][0]["name"],
                       "replicas": dict(det["stage1"]["services"][0]["replicas"])}]}
    mr = mg.merge(det["stage1"], [A], [copy.deepcopy(A)], det["aliases"], root=det["root"])
    assert {g["relation"] for g in mr["agreed"]} == {"service", "replicas"}
    assert [g["deterministicRule"] for g in mr["deterministic"]].count("replicas-default-1") == 1
    ag = mr["agreement"]
    assert ag["agreed"] == 2 and ag["reportable"]["agreed"] == 2
    assert ag["reportable"]["keys"] == ag["agreed"] + ag["contested"] + ag["deterministic"] - 4  # name, id, 2x role

# ============================================================================ Amendment 3: identifier normalisation

KCOMPOSE = COMPOSE + """  kafka:
    image: toy/kafka
    container_name: toy-kafka
"""
KCODE = """// synthetic kafka client
group.id = "g1"                          // line 2
session.timeout.ms default 45000         // line 3
heartbeat thread                         // line 4
coordinator = broker                     // line 5
registry = zk-ensemble                   // line 6
"""


@pytest.fixture()
def kz(tmp_path):
    commit = _git_repo(tmp_path / "toy", {"compose.yml": KCOMPOSE, "src/k.txt": KCODE})
    src = {"toy": {"path": str(tmp_path / "toy"), "commit": commit}}

    def c(value, line, token):
        return dict(value=value, repo="toy", sourceFile="src/k.txt", line=line, quotedToken=token)

    def coord(name, hosted, mech, timeout=45):
        return {"name": c(name, 5, "coordinator"), "type": c("ConsumerGroupCoordinator", 5, "coordinator"),
                "hostedBy": c(hosted, 5, "broker"),
                "liveness": [{"mechanism": c(mech, 4, "heartbeat"), "monitors": [c("front", 2, "group.id")],
                              "failureTimeoutSeconds": c(timeout, 3, "45000")}]}

    def ext(coordname, hosted, mech, group_coord):
        return {"schemaVersion": 1, "sut": "toy", "sources": src,
                "consumerGroups": [{"name": c("g1", 2, '"g1"'), "coordinator": c(group_coord, 5, "coordinator")}],
                "coordinators": [coord(coordname, hosted, mech)]}

    stage1 = {"schemaVersion": 1, "sut": "toy", "sources": src,
              "architecture": {"name": c("toy", 1, "synthetic")}, "host": {"id": c("h", 1, "synthetic")},
              "services": [{"name": c("front", 2, "group.id"), "role": c("microservice", 2, "group.id"),
                            "container": c("front", 2, "group.id")}]}
    aliases = {"front": "front", "back": "back", "toy-back": "back", "queue": "queue", "kafka": "kafka",
               "toy-kafka": "kafka"}
    return {"root": tmp_path, "stage1": stage1, "ext": ext, "c": c, "aliases": aliases, "coord": coord}


def test_free_text_coordinator_and_liveness_ids_merge_by_compose_service_and_mechanism(kz):
    A = kz["ext"]("kafka-group-coordinator", "kafka:9092", "session heartbeat", "kafka-group-coordinator")
    B = kz["ext"]("Kafka broker coordinator", "toy-kafka", "heartbeat", "kafka")
    mr = mg.merge(kz["stage1"], [A], [B], kz["aliases"], root=kz["root"])
    agreed = {g["relation"]: g for g in mr["agreed"]}
    for rel in ("coordinator", "coordinatorType", "hostedBy", "liveness", "monitors", "failureTimeoutSeconds",
                "coordinatedBy", "consumerGroup"):
        assert rel in agreed, rel
    assert agreed["coordinator"]["key"][0] == "kafka/consumer-group-session"
    assert agreed["coordinatedBy"]["key"][2] == "kafka/consumer-group-session"
    assert agreed["failureTimeoutSeconds"]["key"][0] == ["kafka/consumer-group-session", "consumer-group-session"]
    assert mr["log"]["unmappedIdentifiers"] == []
    # control: without the normalisation the same inputs do not merge
    old = mg.merge(kz["stage1"], [A], [B], kz["aliases"], root=kz["root"], normalise_ids=False)
    assert not any(g["relation"] in ("coordinator", "failureTimeoutSeconds") for g in old["agreed"])
    # the rebuilt spec references one coordinator and validates
    spec, log = mg.rebuild(mr, {g["id"] for g in mr["agreed"]})
    assert [c["name"]["value"] for c in spec["coordinators"]] == ["kafka/consumer-group-session"]
    assert spec["consumerGroups"][0]["coordinator"]["value"] == "kafka/consumer-group-session"
    assert spec["coordinators"][0]["liveness"][0]["failureTimeoutSeconds"]["value"] == 45


def test_planted_unmapped_free_text_id_stays_contested_and_is_logged(kz):
    # identical free text from both extractors, but hostedBy names no compose service: never agreed
    A = kz["ext"]("zk-registry", "zk-ensemble", "session", "zk-registry")
    B = copy.deepcopy(A)
    mr = mg.merge(kz["stage1"], [A], [B], kz["aliases"], root=kz["root"])
    rels = {g["relation"] for g in mr["agreed"]}
    assert not rels & {"coordinator", "coordinatorType", "hostedBy", "liveness", "monitors", "failureTimeoutSeconds",
                       "coordinatedBy"}
    um = [g for g in mr["contested"] if g.get("unmappedIdentifier")]
    assert {g["relation"] for g in um} >= {"coordinator", "liveness", "failureTimeoutSeconds", "coordinatedBy"}
    assert len(mr["log"]["unmappedIdentifiers"]) >= 8 and all(u["reason"] for u in mr["log"]["unmappedIdentifiers"])
    # the consumer group name itself is a literal, not an identifier to normalise: still agreed
    assert "consumerGroup" in rels
    ps = ji.packets(mr, root=kz["root"])
    assert {p["id"] for p in ps} >= {g["id"] for g in um}, "unmapped facts go to the judge"

# ============================================================================ Amendment 3: library merge + attachment

lm = _load("library_merge")
LIBSRC = """// synthetic kafka client library
session.timeout.ms = 45000   // line 2
heartbeat.interval.ms = 3000 // line 3
the group coordinator removes members whose session expired  // line 4
HeartbeatThread runs separately   // line 5
"""


@pytest.fixture()
def lib(tmp_path):
    commit = _git_repo(tmp_path / "lib", {"Lib.java": LIBSRC})
    sources = {"obsplacement": {"path": str(tmp_path / "lib"), "commit": commit}}
    schema = json.loads((ONT / "runs/run2-20261014/library_fragment.schema.json").read_text())
    # the fixture repo is not under vendor/libs: relax only the path pattern of the real schema for the test
    schema["$defs"]["cited"]["properties"]["sourceFile"] = {"type": "string"}
    schema["properties"]["sources"]["properties"]["obsplacement"]["properties"]["path"] = {"type": "string"}

    def f(kind, subject, value, line, token, **kw):
        return dict(kind=kind, subject=subject, value=value, repo="obsplacement", sourceFile="Lib.java", line=line,
                    quotedToken=token, **kw)

    facts = [f("config-default", "session.timeout.ms", 45000, 2, "45000", unit="ms", scope="liveness"),
             f("config-default", "heartbeat.interval.ms", 3000, 3, "3000", scope="liveness"),
             f("failure-detector", "session.timeout.ms", "group-coordinator", 4, "group coordinator"),
             f("heartbeat-thread-independent", "HeartbeatThread", True, 5, "HeartbeatThread")]
    spec = {"schemaVersion": 1, "library": "kc", "version": "1.0", "sources": sources, "facts": facts}
    mr = lm.merge_library("kc@1.0", [spec], [copy.deepcopy(spec)], schema, sources, root=tmp_path)

    def g(rel, s, o, gid):
        return {"id": gid, "key": [s, rel, o], "relation": rel, "instances": [], "origins": ["A", "B"]}

    sysmr = {"aliases": {"front": "front", "kafka": "kafka"}, "sources": {}, "system": "toy",
             "agreed": [g("consumes", "front", "orders", "c1"), g("onBroker", "orders", "kafka", "b1"),
                        g("consumesWithGroup", "front", ["orders", "g1"], "w1")],
             "contested": [], "deterministic": []}
    use = {"system": "toy", "service": "front", "repo": "upstream", "sourceFile": "pom.xml", "line": 7,
           "quotedToken": "<version>1.0</version>", "citation": "ok",
           "value": {"service": "front", "library": "kc", "version": "1.0", "family": "kafka-client"}}
    return {"mr": mr, "sys": sysmr, "use": use, "spec": spec, "schema": schema, "sources": sources, "root": tmp_path}


def test_library_merge_agrees_and_drops_bad_citation(lib):
    assert lib["mr"]["agreement"]["agreed"] == 4 and lib["mr"]["agreement"]["contested"] == 0
    bad = copy.deepcopy(lib["spec"])
    bad["facts"][0]["line"] = 5            # '45000' is on line 2
    mr = lm.merge_library("kc@1.0", [lib["spec"]], [bad], lib["schema"], lib["sources"], root=lib["root"])
    assert mr["log"]["droppedCount"]["B"] == 1 and mr["agreement"]["contested"] == 1


def test_library_facts_attach_only_through_a_uses_fact(lib):
    att, log = lm.attach(lib["sys"], [lib["use"]], {"kc@1.0": lib["mr"]}, {"kc": "kafka-client"})
    rels = {a["relation"]: a for a in att}
    assert set(rels) >= {"coordinator", "coordinatorType", "hostedBy", "liveness", "monitors", "consumerGroup",
                         "coordinatedBy", "failureTimeoutSeconds", "heartbeatIntervalSeconds",
                         "heartbeatThreadIndependentOfWork"}
    assert rels["failureTimeoutSeconds"]["key"] == [["kafka/consumer-group-session", "consumer-group-session"],
                                                    "failureTimeoutSeconds", "45.0"]
    assert rels["heartbeatIntervalSeconds"]["key"][2] == "3.0", "unit from the .ms suffix"
    # planted: no uses-fact (or one for another service) -> nothing attaches
    assert lm.attach(lib["sys"], [], {"kc@1.0": lib["mr"]}, {"kc": "kafka-client"})[0] == []
    other = copy.deepcopy(lib["use"])
    other["value"]["service"] = other["service"] = "back"
    assert lm.attach(lib["sys"], [other], {"kc@1.0": lib["mr"]}, {"kc": "kafka-client"})[0] == []
    # planted: a registry/discovery family has no rule
    att2, log2 = lm.attach(lib["sys"], [lib["use"]], {"kc@1.0": lib["mr"]}, {"kc": "discovery-client (x)"})
    assert att2 == [] and log2["noRule"]
    # planted: the service consumes nothing on a compose broker -> nothing attaches
    s2 = copy.deepcopy(lib["sys"])
    s2["agreed"] = [x for x in s2["agreed"] if x["relation"] != "onBroker"]
    assert lm.attach(s2, [lib["use"]], {"kc@1.0": lib["mr"]}, {"kc": "kafka-client"})[0] == []


def test_attachment_resolution_needs_every_requirement_and_yields_to_system_facts(lib):
    sysmr = copy.deepcopy(lib["sys"])
    sysmr["attachments"], _ = lm.attach(sysmr, [lib["use"]], {"kc@1.0": lib["mr"]}, {"kc": "kafka-client"})
    libacc = {g["id"] for g in lib["mr"]["agreed"]}
    groups, log = lm.resolve(sysmr, {"c1", "b1", "w1"}, libacc)
    assert {g["relation"] for g in groups} >= {"coordinator", "failureTimeoutSeconds", "coordinatedBy"}
    # library facts not accepted -> nothing
    groups, log = lm.resolve(sysmr, {"c1", "b1", "w1"}, set())
    assert groups == [] and log["unmet"]
    # the system's consumes fact not accepted -> nothing
    assert lm.resolve(sysmr, {"b1", "w1"}, libacc)[0] == []
    # an accepted system fact for the same liveness slot overrides the library default
    sysmr["agreed"].append({"id": "t30", "key": [["kafka/consumer-group-session", "consumer-group-session"],
                                                  "failureTimeoutSeconds", "30.0"],
                            "relation": "failureTimeoutSeconds", "instances": [], "origins": ["A", "B"]})
    groups, log = lm.resolve(sysmr, {"c1", "b1", "w1", "t30"}, libacc)
    assert "failureTimeoutSeconds" not in {g["relation"] for g in groups} and log["overridden"]
