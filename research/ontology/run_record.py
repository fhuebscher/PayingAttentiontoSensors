"""Run record of the extraction procedure: research/ontology/runs/<run-id>/ (EXTRACTION_PROTOCOL.md, "Outputs").

Usage:
  uv run python research/ontology/run_record.py stage1 RUN_ID [--systems teastore,hotel,otel] [--services sys:svc,...]
  uv run python research/ontology/run_record.py merge RUN_ID SYSTEM [--a A.json ...] [--b B.json ...]
  uv run python research/ontology/run_record.py dryrun [--stamp YYYYMMDDTHHMMZ]
  uv run python research/ontology/run_record.py prompt          (print the stage-2 prompt block and its sha256)
  uv run python research/ontology/run_record.py rerun NEW_ID --from OLD_ID [--systems ...] [--apply]
      stages 3-5 again (Amendment 2): reuses OLD's stage1.json and extractor outputs unchanged (by path + sha256,
      checked against OLD's merge log), new merge + judge packets, OLD's answers reused where the packetDigest is
      unchanged; any new/changed packet stops the run before stage 4. With --apply (only if no new packets):
      apply_judge (run id NEW-<system>), spec_to_ttl -> NEW/<system>.ttl, SHACL report NEW/<system>.shacl.txt.

Every command first extracts the fenced prompt block of EXTRACTION_PROTOCOL.md ("Stage 2") and refuses to run if its
sha256 differs from PROMPT_SHA256 (a changed prompt is an amendment, committed alone, which also changes this pin).
Hash definition: UTF-8 bytes of the lines strictly between the opening ``` line and the closing ``` line of the first
fenced block after the "## Stage 2" heading, joined by "\\n", no trailing newline.

Layout (new paths only; nothing is overwritten):
  runs/<id>/run.json                       run metadata: label, prompt + protocol digests, tool file digests, package
                                           versions, tree-sitter grammar digests, checkout HEAD and dirty state
  runs/<id>/<system>/inputs_manifest.json  inputs.build_manifest (every file with sha256, commits, per-service bundles)
  runs/<id>/<system>/stage1.json           extract_stage1.build_stage1
  runs/<id>/<system>/stage1_citations.json check_citations over the schema facts, and over the observations
  runs/<id>/<system>/merge.json            merge.merge (stage 3) with the inputs it was given
  runs/<id>/<system>/judge_packets.jsonl   judge_inputs.packets (one per contested fact)
  runs/<id>/<system>/log.txt               what ran, counts
The dry run adds <system>/stage1.ttl and <system>/shacl_stage1.txt: the stage-1 spec converted and validated as a
check of the converter and the shapes, not an ontology (no fact of it has been agreed or judged).
"""
import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROTOCOL = HERE / "EXTRACTION_PROTOCOL.md"
RUNS = HERE / "runs"
PROMPT_SHA256 = "d29393e563c713440288700e6956dd33ec3c01b7e2a4d217cef08300edae00f7"
DRY_RUN_SERVICES = {"otel": "accountingservice", "teastore": "recommender", "hotel": "search"}
TOOLS = ("inputs.py", "extract_stage1.py", "check_citations.py", "merge.py", "judge_inputs.py", "apply_judge.py",
         "run_record.py", "spec_to_ttl.py", "query.py", "extraction.schema.json", "ops.ttl", "omsac.ttl", "shapes.ttl")
PACKAGES = ("tree-sitter", "tree-sitter-language-pack", "pyyaml", "jsonschema", "rdflib", "pyshacl")


def sha256(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def prompt_block(text):
    i = text.find("## Stage 2")
    if i < 0:
        raise SystemExit("protocol has no '## Stage 2' section")
    lines = text[i:].split("\n")
    try:
        a = next(n for n, s in enumerate(lines) if s.startswith("```"))
        b = next(n for n in range(a + 1, len(lines)) if lines[n].startswith("```"))
    except StopIteration:
        raise SystemExit("no fenced prompt block in the Stage 2 section")
    return "\n".join(lines[a + 1:b])


def check_prompt(text=None):
    """-> the prompt's sha256; SystemExit if it is not the pinned one."""
    text = PROTOCOL.read_text() if text is None else text
    h = sha256(prompt_block(text))
    if h != PROMPT_SHA256:
        raise SystemExit("REFUSING: the Stage 2 prompt block of EXTRACTION_PROTOCOL.md has sha256 %s, pinned %s. "
                         "A changed prompt is an amendment (commit it alone, re-pin, re-run every system)."
                         % (h, PROMPT_SHA256))
    return h


def _git(*a):
    r = subprocess.run(["git", "-C", str(HERE.parents[1])] + list(a), capture_output=True, text=True)
    return r.stdout.strip()


def _grammars(langs):
    try:
        from tree_sitter_language_pack import cache_dir
        d = Path(cache_dir())
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}
    out = {}
    for lang in sorted(langs):
        name = {"csharp": "c_sharp", "tsx": "tsx", "typescript": "typescript"}.get(lang, lang)
        for p in sorted(d.glob("*tree_sitter_%s.*" % name)):
            out[lang] = {"file": p.name, "sha256": sha256(p.read_bytes())}
    return out


def run_meta(run_id, label, prompt_sha, langs=()):
    vers = {}
    for p in PACKAGES:
        try:
            vers[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            vers[p] = None
    status = _git("status", "--porcelain", "--", "research/ontology", "pyproject.toml", "uv.lock")
    return {
        "runId": run_id, "label": label, "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "protocol": {"path": "research/ontology/EXTRACTION_PROTOCOL.md", "sha256": sha256(PROTOCOL.read_bytes()),
                     "lastCommit": _git("log", "-1", "--format=%H", "--", "research/ontology/EXTRACTION_PROTOCOL.md")},
        "promptSha256": prompt_sha, "promptSha256Pinned": PROMPT_SHA256,
        "checkout": {"head": _git("rev-parse", "HEAD"),
                     "ontologyDirty": [l for l in status.splitlines() if "research/ontology/runs/" not in l]},
        "tools": {t: sha256((HERE / t).read_bytes()) for t in TOOLS if (HERE / t).exists()},
        "python": platform.python_version(), "packages": vers, "grammars": _grammars(langs),
    }


def _new_dir(p):
    if p.exists():
        raise SystemExit("refusing to reuse %s (new evidence gets a new path)" % p)
    p.mkdir(parents=True)
    return p


def _write(p, obj):
    if p.exists():
        raise SystemExit("refusing to overwrite %s" % p)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj, indent=1, default=str) + "\n")


def do_stage1(run_dir, system, services=None):
    import extract_stage1
    import inputs
    import check_citations
    d = _new_dir(run_dir / system)
    log = []
    m = inputs.build_manifest(system)
    _write(d / "inputs_manifest.json", m)
    log.append("inputs: %d files, %d bytes; %d services; excluded %s; unresolved vars %d" % (
        m["fileCount"], m["bytes"], len(m["services"]), {k: v["count"] for k, v in m["excluded"].items()},
        len(m["unresolvedVariables"])))
    spec = extract_stage1.build_stage1(system, services)
    _write(d / "stage1.json", spec)
    facts = check_citations.check_spec(spec)
    obs = extract_stage1.check_observations(spec)
    _write(d / "stage1_citations.json", {"facts": facts, "observations": obs})
    log.append("stage1 services=%s: %d schema facts %s; %d observations+literals %s; AST %s" % (
        ",".join(spec["extraction"]["services"]), facts["facts"], facts["counts"], obs["facts"], obs["counts"],
        json.dumps({k: spec["extraction"]["astStats"][k] for k in ("filesParsed", "callSites", "byCategory")})))
    return d, spec, facts, obs, log


def do_merge(d, system, a=(), b=()):
    import inputs
    import judge_inputs
    import merge as merge_mod
    repos = inputs.open_repos(system)
    aliases = {k.lower(): v for k, v in inputs.Compose(system, repos).aliases().items()}
    labels = {("A", i): str(p) for i, p in enumerate(a)}
    labels.update({("B", i): str(p) for i, p in enumerate(b)})
    mr = merge_mod.merge(str(d / "stage1.json"), list(a), list(b), aliases, labels=labels)
    _write(d / "merge.json", mr)
    ps = judge_inputs.packets(mr)
    _write(d / "judge_packets.jsonl", "".join(json.dumps(p, sort_keys=True) + "\n" for p in ps))
    ag = mr["agreement"]
    return mr, ["merge: A files %d, B files %d; dropped %s; schema-rejected %d; agreed %d, contested %d, agreement %s;"
                " per relation %s; judge packets %d" % (
                    len(a), len(b), mr["log"]["droppedCount"], len(mr["log"]["schemaRejected"]), ag["agreed"],
                    ag["contested"], ag["agreement"],
                    json.dumps({r: "%d/%d" % (v["agreed"], v["agreed"] + v["contested"])
                                for r, v in sorted(ag["byRelation"].items())}), len(ps))]


def cmd_stage1(run_id, systems, services, label):
    h = check_prompt()
    run_dir = _new_dir(RUNS / run_id)
    langs, out = set(), {}
    for s in systems:
        d, spec, facts, obs, log = do_stage1(run_dir, s, services.get(s))
        langs.update(spec["extraction"]["astStats"]["languages"])
        _write(d / "log.txt", "\n".join(log) + "\n")
        out[s] = (d, spec, facts, obs, log)
    _write(run_dir / "run.json", run_meta(run_id, label, h, langs))
    return run_dir, out


def cmd_dryrun(stamp):
    import query
    import spec_to_ttl
    run_id = "dryrun-" + stamp
    run_dir, out = cmd_stage1(run_id, sorted(DRY_RUN_SERVICES), {k: [v] for k, v in DRY_RUN_SERVICES.items()},
                              "DRY RUN (protocol: 'built and dry-run on one service of each system'); stage 1 + "
                              "merge with empty extractor A/B + SHACL on the stage-1 spec; no model was run")
    summary = {}
    for s, (d, spec, facts, obs, log) in out.items():
        mr, mlog = do_merge(d, s)
        log += mlog
        g = spec_to_ttl.spec_to_graph(spec)
        _write(d / "stage1.ttl", g.serialize(format="turtle"))
        ok, text = query.validate(g)
        _write(d / "shacl_stage1.txt", "conforms: %s\n\n%s" % (ok, text))
        log.append("SHACL on the stage-1 spec (converter/shapes check, not an ontology): conforms=%s, %d triples" %
                   (ok, len(g)))
        (d / "log.txt").unlink()
        _write(d / "log.txt", "DRY RUN\n" + "\n".join(log) + "\n")
        summary[s] = {"service": DRY_RUN_SERVICES[s], "stage1Facts": facts["facts"], "factCitations": facts["counts"],
                      "observations": obs["facts"], "observationCitations": obs["counts"],
                      "astCallSites": spec["extraction"]["astStats"]["callSites"],
                      "agreed": mr["agreement"]["agreed"], "contested": mr["agreement"]["contested"],
                      "shaclConforms": ok}
    _write(run_dir / "summary.json", summary)
    return run_dir, summary


def _file_sha(p):
    return sha256(Path(p).read_bytes())


def cmd_rerun_stage3(new_id, old_id, systems):
    import inputs
    import judge_inputs
    import merge as merge_mod
    h = check_prompt()
    root = HERE.parents[1]
    old, new = RUNS / old_id, RUNS / new_id
    run_dir = new if new.exists() else _new_dir(new)
    report = {}
    for s in systems:
        d = _new_dir(run_dir / s)
        om = json.loads((old / s / "merge.json").read_text())
        s1p = old / s / "stage1.json"
        a = [i["input"] for i in om["log"]["inputs"] if i["origin"] == "A"]
        b = [i["input"] for i in om["log"]["inputs"] if i["origin"] == "B"]
        reuse = {"stage1": {"path": str(s1p.relative_to(root)), "sha256": _file_sha(s1p)}, "extractors": []}
        # unchanged inputs: the canonical digest the old merge logged must match the file as it is now
        for i in om["log"]["inputs"]:
            p = root / i["input"] if i["origin"] != "stage1" else s1p
            canon = sha256(json.dumps(json.loads(p.read_text()), sort_keys=True))
            if canon != i["sha256"]:
                raise SystemExit("input changed since %s: %s" % (old_id, p))
            if i["origin"] != "stage1":
                reuse["extractors"].append({"origin": i["origin"], "path": i["input"], "sha256": _file_sha(p),
                                            "canonicalSha256": canon})
        repos = inputs.open_repos(s)
        aliases = {k.lower(): v for k, v in inputs.Compose(s, repos).aliases().items()}
        if aliases != om["aliases"]:
            raise SystemExit("compose alias table differs from %s for %s" % (old_id, s))
        labels = {("A", n): x for n, x in enumerate(a)}
        labels.update({("B", n): x for n, x in enumerate(b)})
        mr = merge_mod.merge(str(s1p), [str(root / x) for x in a], [str(root / x) for x in b], aliases, labels=labels)
        _write(d / "merge.json", mr)
        ps = judge_inputs.packets(mr)
        _write(d / "judge_packets.jsonl", "".join(json.dumps(p, sort_keys=True) + "\n" for p in ps))
        old_ans = {}
        for x in (old / s / "judge" / "answers_all.jsonl").read_text().splitlines():
            if x.strip():
                r = json.loads(x)
                old_ans[(r["id"], r["packetDigest"])] = r
        reused = [old_ans[(p["id"], p["packetDigest"])] for p in ps if (p["id"], p["packetDigest"]) in old_ans]
        new_p = [{"id": p["id"], "relation": p["relation"], "subject": p["subject"], "object": p["object"]}
                 for p in ps if (p["id"], p["packetDigest"]) not in old_ans]
        _write(d / "answers_reused.jsonl", "".join(json.dumps(r, sort_keys=True) + "\n" for r in reused))
        reuse["answers"] = {"from": str((old / s / "judge" / "answers_all.jsonl").relative_to(root)),
                            "sha256": _file_sha(old / s / "judge" / "answers_all.jsonl"),
                            "reusedIds": sorted(r["id"] for r in reused), "newOrChangedPackets": new_p,
                            "oldAnswersNotNeeded": len(old_ans) - len(reused)}
        _write(d / "reuse.json", reuse)
        ag = mr["agreement"]
        log = ["rerun of %s stages 3-5 under Amendment 2; inputs reused unchanged (reuse.json)" % old_id,
               "merge: dropped %s; agreed %d, deterministic %d, contested %d; agreement all keys %.4f (%d/%d), "
               "reportable %.4f (%d/%d)" % (mr["log"]["droppedCount"], ag["agreed"], ag["deterministic"],
                                            ag["contested"], ag["agreement"], ag["agreed"],
                                            ag["agreed"] + ag["deterministic"] + ag["contested"],
                                            ag["reportable"]["agreement"], ag["reportable"]["agreed"],
                                            ag["reportable"]["keys"]),
               "judge packets %d: reused answers %d, new or changed %d" % (len(ps), len(reused), len(new_p))]
        _write(d / "log.txt", "\n".join(log) + "\n")
        report[s] = {"agreement": ag, "packets": len(ps), "reused": len(reused), "new": new_p}
    if not (run_dir / "run.json").exists():
        meta = run_meta(new_id, "stages 3-5 re-run of %s under EXTRACTION_PROTOCOL Amendment 2" % old_id, h)
        meta["reusesRun"] = old_id
        _write(run_dir / "run.json", meta)
    return report


def cmd_rerun_apply(new_id, systems, judge):
    import apply_judge
    import query
    import spec_to_ttl
    run_dir = RUNS / new_id
    out = {}
    for s in systems:
        d = run_dir / s
        reuse = json.loads((d / "reuse.json").read_text())
        if reuse["answers"]["newOrChangedPackets"]:
            raise SystemExit("%s: %d new or changed packets need the judge first" % (
                s, len(reuse["answers"]["newOrChangedPackets"])))
        spec, decisions, errs = apply_judge.apply(d / "merge.json", d / "judge_packets.jsonl",
                                                  d / "answers_reused.jsonl", judge, "%s-%s" % (new_id, s),
                                                  d / "final_spec.json")
        res = {"schemaErrors": errs, "accepted": spec["extraction"]["accepted"],
               "decisions": {v: sum(x["verdict"] == v for x in decisions) for v in sorted({x["verdict"] for x in decisions})},
               "rebuildLog": {k: len(v) for k, v in spec["extraction"]["rebuildLog"].items()}}
        if not errs:
            g = spec_to_ttl.spec_to_graph(spec)
            _write(run_dir / ("%s.ttl" % s), g.serialize(format="turtle"))
            ok, text = query.validate(g)
            _write(run_dir / ("%s.shacl.txt" % s), "conforms: %s\n\n%s" % (ok, text))
            res.update(shaclConforms=ok, triples=len(g),
                       shaclViolations=sum(1 for line in text.splitlines() if line.startswith("Constraint Violation")))
        with open(d / "log.txt", "a") as fh:
            fh.write("stage 4-5: %s\n" % json.dumps(res, sort_keys=True))
        out[s] = res
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("stage1")
    s1.add_argument("run_id")
    s1.add_argument("--systems", default="teastore,hotel,otel")
    s1.add_argument("--services", default="")
    s1.add_argument("--label", default="")
    mg = sub.add_parser("merge")
    mg.add_argument("run_id")
    mg.add_argument("system")
    mg.add_argument("--a", nargs="*", default=[])
    mg.add_argument("--b", nargs="*", default=[])
    dr = sub.add_parser("dryrun")
    dr.add_argument("--stamp", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ"))
    sub.add_parser("prompt")
    rr = sub.add_parser("rerun")
    rr.add_argument("run_id")
    rr.add_argument("--from", dest="old", required=True)
    rr.add_argument("--systems", default="teastore,hotel,otel")
    rr.add_argument("--apply", action="store_true")
    rr.add_argument("--judge", default="reused answers of the source run (opus, judge prompt b1c5099d)")
    a = ap.parse_args(argv)
    if a.cmd == "rerun":
        systems = a.systems.split(",")
        if a.apply:
            check_prompt()
            print(json.dumps(cmd_rerun_apply(a.run_id, systems, a.judge), indent=1, default=str))
        else:
            rep = cmd_rerun_stage3(a.run_id, a.old, systems)
            print(json.dumps({k: {"agreement": {x: v["agreement"][x] for x in ("agreed", "deterministic", "contested",
                                                                                "agreement")},
                                  "reportable": v["agreement"]["reportable"], "packets": v["packets"],
                                  "reused": v["reused"], "new": v["new"]} for k, v in rep.items()}, indent=1))
        return
    if a.cmd == "prompt":
        t = PROTOCOL.read_text()
        print(prompt_block(t))
        print("\nsha256 %s (pinned %s)" % (sha256(prompt_block(t)), PROMPT_SHA256))
        return
    if a.cmd == "stage1":
        svc = {}
        for x in filter(None, a.services.split(",")):
            k, v = x.split(":")
            svc.setdefault(k, []).append(v)
        run_dir, _ = cmd_stage1(a.run_id, a.systems.split(","), svc, a.label)
        print(run_dir)
    elif a.cmd == "merge":
        check_prompt()
        d = RUNS / a.run_id / a.system
        if not (d / "stage1.json").exists():
            raise SystemExit("no stage1.json in %s" % d)
        mr, log = do_merge(d, a.system, a.a, a.b)
        with open(d / "log.txt", "a") as fh:
            fh.write("\n".join(log) + "\n")
        print("\n".join(log))
    elif a.cmd == "dryrun":
        run_dir, summary = cmd_dryrun(a.stamp)
        print(run_dir)
        print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
