"""Amendment 3 library module: merge the library extractions, attach library facts to systems, build run2 stage 3.

Usage:  uv run python research/ontology/library_merge.py stage3 RUN2_DIR --from RUN1_DIR
        uv run python research/ontology/library_merge.py stage45 RUN2_DIR    (after the judge: apply, attach, Turtle, SHACL)

1. Library merge (same rules as services, merge.py steps 1-4): every extractor output is validated against
   RUN2/library_fragment.schema.json (invalid -> contributes nothing), its `sources` replaced by the pinned vendor
   commit, every fact citation-checked (check_citations, +-2 lines; a fail is dropped and counted). Key =
   (<library>@<version>|<subject>, library:<kind>, <value>): subject (config key, timeout key, class, component) and
   string values stripped and lower-cased, numbers compared as floats, booleans as booleans; unit/scope/signal are not
   part of the key. Agreed iff extractors A and B both report the key, else contested (judge packet).
2. Attachment rule (ATTACH): a library fact reaches a system only through an accepted uses-fact "service S uses
   library L at version V" (libraries.json; build-file facts, citation-checked, deterministic). For a library of the
   kafka-client family and a service S using it, and for every accepted (system) pair consumes(S, T) + onBroker(T, B)
   with B a compose service, the coordinator entity C = B/consumer-group-session (Change 2 key) receives:
   - from an accepted failure-detector fact with value `group-coordinator` (subject = its timeout key K):
     coordinator(C), coordinatorType(C, ConsumerGroupCoordinator), hostedBy(C, B), liveness(C), monitors(C, S), and
     consumerGroup(G) + coordinatedBy(G, C) for every accepted consumesWithGroup(S, [T, G]);
   - from an accepted config-default fact whose subject is K: failureTimeoutSeconds(C) = value in seconds;
   - from an accepted config-default fact whose subject matches /heartbeat[._]?interval/i: heartbeatIntervalSeconds;
   - from an accepted heartbeat-thread-independent fact: heartbeatThreadIndependentOfWork.
   Seconds: unit `ms` or a subject ending in `.ms` -> /1000; unit `s` -> as is; otherwise the fact does not attach
   (logged). No other library family attaches (registry and discovery clients have no rule: their facts reach no
   system unless a later amendment states one; TeaStore's ribbon facts do not name the TeaStore registry).
   A library default does not attach where an accepted system fact already states the same (subject, relation): the
   system's own configuration wins (an override is logged).
   Attachments are computed at stage 3 from candidate requirements and resolved at stage 4 (resolve()): an attached
   fact enters only when its uses-fact, every library group it derives from and every system group it requires are
   accepted. Attached facts are labelled acceptance `library`; their provenance is the library fact's citation
   (repo key `libvendor` = the vendor commit).
3. Stage 3 for each system: merge.merge with identifier normalisation, run1's stage-1 and extractor outputs reused
   unchanged (canonical sha256 checked against run1's merge log), judge packets for every contested fact; run1 answers
   reused where (id, packetDigest) is unchanged; new or changed packets written in chunks of <= 25 to
   RUN2/<system>/judge/ and, for libraries, RUN2/library/<lib>@<version>/judge/; RUN2/stage4_chunks.json lists them.
"""
import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import check_citations  # noqa: E402
import judge_inputs  # noqa: E402
import merge as mg  # noqa: E402

KAFKA_FAMILY = "kafka-client"
CHUNK = 25


def _sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def _lnorm(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return repr(float(v))
    return str(v).strip().lower()

# ============================================================================================ 1. library merge


def merge_library(name, a_specs, b_specs, schema, sources, root=ROOT, labels=None):
    """-> merge-result dict in merge.merge's layout (agreed/contested groups with instances) for one library."""
    v = jsonschema.Draft202012Validator(schema)
    reader = check_citations.SourceReader(sources, root)
    log = {"inputs": [], "schemaRejected": [], "sourcesReplaced": [], "dropped": [],
           "droppedCount": {"A": 0, "B": 0}, "checkedCount": {"A": 0, "B": 0}}
    groups = {}
    for origin, specs in (("A", a_specs), ("B", b_specs)):
        for i, sp in enumerate(specs):
            label = (labels or {}).get((origin, i), str(sp))
            spec = copy.deepcopy(json.loads(Path(sp).read_text()) if not isinstance(sp, dict) else sp)
            log["inputs"].append({"origin": origin, "input": label,
                                  "sha256": _sha(json.dumps(spec, sort_keys=True))})
            errs = list(v.iter_errors(spec))
            if errs or "%s@%s" % (spec.get("library"), spec.get("version")) != name:
                log["schemaRejected"].append({"origin": origin, "input": label,
                                              "errors": [e.message[:300] for e in errs[:10]] or ["library/version"]})
                continue
            if spec["sources"] != sources:
                log["sourcesReplaced"].append({"origin": origin, "input": label, "had": spec["sources"]})
            for j, f in enumerate(spec["facts"]):
                log["checkedCount"][origin] += 1
                r = check_citations.check_fact(reader, f)
                path = "$.facts[%d]" % j
                if r["status"] != "ok":
                    log["droppedCount"][origin] += 1
                    log["dropped"].append({"origin": origin, "input": label, "path": path, "fact": f, "check": r})
                    continue
                subj = "%s|%s" % (name, _lnorm(f.get("subject", "")))
                key = json.dumps([subj, "library:" + f["kind"], _lnorm(f["value"])], sort_keys=True)
                g = groups.setdefault(key, {"key": json.loads(key), "relation": "library:" + f["kind"],
                                            "library": name, "instances": []})
                g["instances"].append({"origin": origin, "input": label, "path": path, "subject": f.get("subject"),
                                       "object": f["value"], "slots": ["const", "const"], "fact": f, "check": "ok"})
    agreed, contested = [], []
    for k in sorted(groups):
        g = groups[k]
        g["origins"] = sorted({i["origin"] for i in g["instances"]})
        g["id"] = mg.fact_digest(k)
        (agreed if g["origins"] == ["A", "B"] else contested).append(g)
    by = {}
    for st, gs in (("agreed", agreed), ("contested", contested)):
        for g in gs:
            by.setdefault(g["relation"], {"agreed": 0, "contested": 0})[st] += 1
    n = len(agreed) + len(contested)
    return {"mergeVersion": 2, "system": "library:" + name, "library": name, "sources": sources, "aliases": {},
            "agreement": {"agreed": len(agreed), "contested": len(contested),
                          "agreement": len(agreed) / n if n else None, "byRelation": by},
            "log": log, "agreed": agreed, "contested": contested, "deterministic": []}

# ============================================================================================ 2. attachment


def _seconds(f):
    unit = f.get("unit")
    v = f.get("value")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        try:
            v = float(str(v).strip())
        except ValueError:
            return None
    if unit == "ms" or (unit in (None, "none") and str(f.get("subject", "")).lower().endswith(".ms")):
        return v / 1000.0
    if unit == "s":
        return float(v)
    return None


def _first(g):
    return sorted(g["instances"], key=lambda i: i["origin"])[0]["fact"]


def attach(system_mr, uses_facts, library_mrs, families):
    """Candidate attachments for one system. uses_facts: libraries.json facts of this system with citation ok.
    library_mrs: {lib@ver: library merge result}. families: {lib: family}. -> (attachments, log)."""
    aliases = system_mr["aliases"]
    services = set(aliases.values())
    sysg = {}
    for cls in ("agreed", "contested", "deterministic"):
        for g in system_mr.get(cls, []):
            sysg.setdefault(g["relation"], []).append(g)
    out, log = [], {"skipped": [], "noRule": []}

    def add(key, relation, value_fact, lib_ids, sys_ids, use, slots, note):
        """key = [subject, relation, raw object]; normalised exactly as merge.key_of so ids coincide."""
        rec = {"subject": key[0], "relation": relation, "object": key[2], "slots": slots}
        k = mg.key_of(rec, aliases)
        f = {"value": key[2]}
        f.update({x: value_fact[x] for x in ("sourceFile", "line", "quotedToken") if x in value_fact})
        f["repo"] = "libvendor"
        f["note"] = ("Amendment 3 attachment (library_merge.py ATTACH): %s; via uses-fact %s:%s %s@%s; %s" % (
            relation, use["sourceFile"], use["line"], use["value"]["library"], use["value"]["version"], note))
        out.append({"id": mg.fact_digest(k), "key": json.loads(k), "relation": relation,
                    "requires": {"uses": "%s:%s:%s" % (use["repo"], use["sourceFile"], use["line"]),
                                 "library": sorted(set(lib_ids)), "system": sorted(set(sys_ids))},
                    "instance": {"origin": "library", "input": "library:%s" % ",".join(sorted(set(lib_ids))),
                                 "path": "attachment", "subject": key[0], "object": key[2], "slots": slots,
                                 "fact": f, "check": "ok"}})

    for use in uses_facts:
        lib, ver, svc = use["value"]["library"], use["value"]["version"], use["value"]["service"]
        name = "%s@%s" % (lib, ver)
        fam = families.get(lib, use["value"].get("family", ""))
        libs = [name] + (["librdkafka@%s" % ver] if lib == "Confluent.Kafka" else [])
        if not fam.startswith(KAFKA_FAMILY):
            log["noRule"].append({"service": svc, "library": name, "family": fam})
            continue
        lgroups = [g for n in libs if n in library_mrs for cls in ("agreed", "contested") for g in library_mrs[n][cls]]
        det = [g for g in lgroups if g["relation"] == "library:failure-detector" and g["key"][2] == "group-coordinator"]
        if not det:
            log["skipped"].append({"service": svc, "library": name, "reason": "no group-coordinator failure-detector fact"})
            continue
        s = mg.norm_name(svc, aliases, True)
        for cg in sysg.get("consumes", []):
            if cg["key"][0] != s:
                continue
            t = cg["key"][2]
            for bg in sysg.get("onBroker", []):
                if bg["key"][0] != t or bg["key"][2] not in services:
                    continue
                b = bg["key"][2]
                C, mech = "%s/consumer-group-session" % b, "consumer-group-session"
                base_sys = [cg["id"], bg["id"]]
                for dg in det:
                    K = dg["key"][0].split("|", 1)[1]
                    df = _first(dg)
                    ids = [dg["id"]]
                    add([C, "coordinator", C], "coordinator", df, ids, base_sys, use, ["name", "name"], "detector " + K)
                    add([C, "coordinatorType", "ConsumerGroupCoordinator"], "coordinatorType", df, ids, base_sys, use,
                        ["name", "enum"], "detector " + K)
                    add([C, "hostedBy", b], "hostedBy", df, ids, base_sys, use, ["name", "hostedBy"], "broker of %s" % t)
                    add([[C, mech], "liveness", mech], "liveness", df, ids, base_sys, use, ["pair", "name"], K)
                    add([[C, mech], "monitors", s], "monitors", df, ids, base_sys, use, ["pair", "monitors"], K)
                    for wg in sysg.get("consumesWithGroup", []):
                        if wg["key"][0] == s and wg["key"][2][0] == t:
                            G = wg["key"][2][1]
                            add([G, "consumerGroup", G], "consumerGroup", df, ids, base_sys + [wg["id"]], use,
                                ["name", "name"], "group of %s" % s)
                            add([G, "coordinatedBy", C], "coordinatedBy", df, ids, base_sys + [wg["id"]], use,
                                ["name", "name"], "group of %s" % s)
                    for g in lgroups:
                        subj = g["key"][0].split("|", 1)[1]
                        f = _first(g)
                        if g["relation"] == "library:config-default" and subj == K:
                            sec = _seconds(f)
                            if sec is None:
                                log["skipped"].append({"library": g["library"], "id": g["id"], "reason": "no unit"})
                                continue
                            add([[C, mech], "failureTimeoutSeconds", sec], "failureTimeoutSeconds", f,
                                ids + [g["id"]], base_sys, use, ["pair", "number"], "default of %s" % K)
                        elif g["relation"] == "library:config-default" and re.search(r"heartbeat[._]?interval", subj):
                            sec = _seconds(f)
                            if sec is None:
                                log["skipped"].append({"library": g["library"], "id": g["id"], "reason": "no unit"})
                                continue
                            add([[C, mech], "heartbeatIntervalSeconds", sec], "heartbeatIntervalSeconds", f,
                                ids + [g["id"]], base_sys, use, ["pair", "number"], "default of %s" % subj)
                        elif g["relation"] == "library:heartbeat-thread-independent" and isinstance(g["key"][2], bool):
                            add([[C, mech], "heartbeatThreadIndependentOfWork", g["key"][2]],
                                "heartbeatThreadIndependentOfWork", f, ids + [g["id"]], base_sys, use,
                                ["pair", "bool"], "heartbeat thread %s" % subj)
    # one attachment record per (key, requirement set)
    seen, uniq = set(), []
    for a in out:
        k = json.dumps([a["key"], a["requires"]], sort_keys=True)
        if k not in seen:
            seen.add(k)
            uniq.append(a)
    return uniq, log


def resolve(system_mr, system_accepted, library_accepted, uses_ok=True):
    """Attachments whose requirements are all accepted and that no accepted system fact overrides.
    -> (pseudo-groups for merge.rebuild(attached=...), log)."""
    acc_keys = {}
    for cls in ("agreed", "contested", "deterministic"):
        for g in system_mr.get(cls, []):
            if g["id"] in system_accepted:
                acc_keys.setdefault((json.dumps(g["key"][0]), g["relation"]), set()).add(json.dumps(g["key"][2]))
    groups, log = {}, {"accepted": 0, "unmet": [], "overridden": [], "alreadyAccepted": 0}
    for a in system_mr.get("attachments", []):
        r = a["requires"]
        miss = [i for i in r["library"] if i not in library_accepted] + \
               [i for i in r["system"] if i not in system_accepted] + ([] if uses_ok else [r["uses"]])
        if miss:
            log["unmet"].append({"id": a["id"], "relation": a["relation"], "missing": miss})
            continue
        sk = (json.dumps(a["key"][0]), a["relation"])
        if a["id"] in system_accepted:
            log["alreadyAccepted"] += 1
            continue
        if a["relation"] in mg.LIVENESS_NUM + mg.LIVENESS_BOOL and sk in acc_keys:
            log["overridden"].append({"id": a["id"], "relation": a["relation"], "system": sorted(acc_keys[sk])})
            continue
        g = groups.setdefault(a["id"], {"id": a["id"], "key": a["key"], "relation": a["relation"],
                                        "origins": ["library"], "instances": []})
        g["instances"].append(a["instance"])
        log["accepted"] += 1
    return list(groups.values()), log

# ============================================================================================ 3. run2 stage 3


def _chunks(packets, d, prefix=""):
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for n in range(0, len(packets), CHUNK):
        part = packets[n:n + CHUNK]
        p = d / ("%spackets_%02d.jsonl" % (prefix, n // CHUNK))
        if p.exists():
            raise SystemExit("refusing to overwrite %s" % p)
        p.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in part))
        rows.append({"packets": str(p), "answers": str(d / ("%sanswers_%02d.jsonl" % (prefix, n // CHUNK))),
                     "n": len(part)})
    return rows


def _write(p, obj):
    if p.exists():
        raise SystemExit("refusing to overwrite %s" % p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj, indent=1, default=str) + "\n")


def stage3(run2, run1, systems=("teastore", "hotel", "otel")):
    import inputs
    import run_record
    run_record.check_prompt()
    run2, run1 = Path(run2).resolve(), Path(run1).resolve()
    rec = json.loads((run2 / "library_record.json").read_text())
    if _sha((run2 / "library_prompt.txt").read_bytes()) != rec["libraryPromptSha256"]:
        raise SystemExit("library prompt changed since its record")
    schema = json.loads((run2 / "library_fragment.schema.json").read_text())
    vend = {"obsplacement": {"path": ".", "commit": rec["vendorCommit"]}}
    libjson = json.loads((run2 / "libraries.json").read_text())
    families = {}
    for f in libjson["facts"]:
        families[f["value"]["library"]] = f["value"]["family"]
    families.setdefault("librdkafka", "kafka-client (librdkafka)")
    chunks, summary = [], {"libraries": {}, "systems": {}}
    # 1. libraries
    lib_mrs = {}
    for p in sorted((run2 / "library" / "A").glob("*.json")):
        name = p.stem
        b = run2 / "library" / "B" / p.name
        rel = lambda x: str(x.relative_to(ROOT))
        mr = merge_library(name, [str(p)], [str(b)], schema, vend,
                           labels={("A", 0): rel(p), ("B", 0): rel(b)})
        lib_mrs[name] = mr
        d = run2 / "library" / name
        _write(d / "merge.json", mr)
        ps = judge_inputs.packets(mr)
        for row in _chunks(ps, d / "judge"):
            chunks.append(dict(system="library:" + name, **row))
        summary["libraries"][name] = {"agreed": mr["agreement"]["agreed"], "contested": mr["agreement"]["contested"],
                                      "agreement": mr["agreement"]["agreement"], "dropped": mr["log"]["droppedCount"],
                                      "schemaRejected": len(mr["log"]["schemaRejected"]), "packets": len(ps)}
    # 2. systems
    for s in systems:
        om = json.loads((run1 / s / "merge.json").read_text())
        s1p = run1 / s / "stage1.json"
        reuse = {"stage1": {"path": str(s1p.relative_to(ROOT)), "sha256": _sha(s1p.read_bytes())}, "extractors": []}
        for i in om["log"]["inputs"]:
            p = ROOT / i["input"] if i["origin"] != "stage1" else s1p
            if _sha(json.dumps(json.loads(p.read_text()), sort_keys=True)) != i["sha256"]:
                raise SystemExit("input changed since run1: %s" % p)
            if i["origin"] != "stage1":
                reuse["extractors"].append({"origin": i["origin"], "path": i["input"], "sha256": _sha(p.read_bytes())})
        a = [i["input"] for i in om["log"]["inputs"] if i["origin"] == "A"]
        b = [i["input"] for i in om["log"]["inputs"] if i["origin"] == "B"]
        aliases = {k.lower(): v for k, v in inputs.Compose(s, inputs.open_repos(s)).aliases().items()}
        labels = {("A", n): x for n, x in enumerate(a)}
        labels.update({("B", n): x for n, x in enumerate(b)})
        mr = mg.merge(str(s1p), [str(ROOT / x) for x in a], [str(ROOT / x) for x in b], aliases, labels=labels,
                      normalise_ids=True)
        uses = [f for f in libjson["facts"] if f["system"] == s and f.get("citation") == "ok"]
        att, alog = attach(mr, uses, lib_mrs, families)
        mr["attachments"], mr["attachmentLog"] = att, alog
        mr["usesFacts"] = [{k: f[k] for k in ("service", "value", "repo", "sourceFile", "line", "quotedToken")}
                           for f in uses]
        mr["sources"] = dict(mr["sources"], libvendor=vend["obsplacement"])
        d = run2 / s
        _write(d / "merge.json", mr)
        ps = judge_inputs.packets(mr)
        old = {}
        for x in (run1 / s / "judge" / "answers_all.jsonl").read_text().splitlines():
            if x.strip():
                r = json.loads(x)
                old[(r["id"], r["packetDigest"])] = r
        reused = [old[(p["id"], p["packetDigest"])] for p in ps if (p["id"], p["packetDigest"]) in old]
        new = [p for p in ps if (p["id"], p["packetDigest"]) not in old]
        _write(d / "answers_reused.jsonl", "".join(json.dumps(r, sort_keys=True) + "\n" for r in reused))
        _write(d / "judge_packets.jsonl", "".join(json.dumps(p, sort_keys=True) + "\n" for p in ps))
        for row in _chunks(new, d / "judge"):
            chunks.append(dict(system=s, **row))
        reuse["answers"] = {"from": str((run1 / s / "judge" / "answers_all.jsonl").relative_to(ROOT)),
                            "reused": len(reused), "new": len(new), "newIds": sorted(p["id"] for p in new)}
        _write(d / "reuse.json", reuse)
        ag = mr["agreement"]
        summary["systems"][s] = {
            "agreed": ag["agreed"], "deterministic": ag["deterministic"], "contested": ag["contested"],
            "agreementAll": ag["agreement"], "agreementReportable": ag["reportable"]["agreement"],
            "unmappedIdentifiers": len(mr["log"].get("unmappedIdentifiers", [])),
            "usesFacts": len(uses), "attachmentCandidates": len(att),
            "attachmentByRelation": {r: sum(1 for x in att if x["relation"] == r) for r in sorted({x["relation"] for x in att})},
            "attachmentNoRule": len(alog["noRule"]), "attachmentSkipped": alog["skipped"],
            "packets": len(ps), "reused": len(reused), "new": len(new)}
    _write(run2 / "stage4_chunks.json", chunks)
    _write(run2 / "stage3_summary.json", summary)
    return summary, chunks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s3 = sub.add_parser("stage3")
    s3.add_argument("run2")
    s3.add_argument("--from", dest="run1", required=True)
    s4 = sub.add_parser("stage45")
    s4.add_argument("run2")
    a = ap.parse_args(argv)
    if a.cmd == "stage45":
        print(json.dumps(stage45(a.run2), indent=1, default=str))
        return
    summary, chunks = stage3(a.run2, a.run1)
    print(json.dumps(summary, indent=1))
    print(json.dumps([{k: (str(Path(v).relative_to(ROOT)) if k in ("packets", "answers") else v)
                       for k, v in c.items()} for c in chunks], indent=1))



# ============================================================================================ 4-5. run2 stages 4-5


def stage45(run2, judge="opus (Opus 5.5), judge prompt b1c5099d"):
    """apply_judge per library and per system (run ids run2-20261014-<set>), resolve attachments, final specs,
    Turtle, SHACL. Libraries: accepted = agreed + supported (no spec is rebuilt; library_accepted.json lists them)."""
    import apply_judge
    import query
    import spec_to_ttl
    run2 = Path(run2).resolve()
    rid = run2.name
    out = {"libraries": {}, "systems": {}}

    def collect(d, names):
        rows = []
        for n in names:
            p = d / n
            if p.exists():
                rows += [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
        return rows

    lib_acc = set()
    for d in sorted(p for p in (run2 / "library").iterdir() if p.is_dir() and (p / "merge.json").exists()):
        mr = json.loads((d / "merge.json").read_text())
        packets = collect(d / "judge", sorted(x.name for x in (d / "judge").glob("packets_*.jsonl")))
        answers = collect(d / "judge", sorted(x.name for x in (d / "judge").glob("answers_*.jsonl")))
        _write(d / "answers_all.jsonl", "".join(json.dumps(a, sort_keys=True) + "\n" for a in answers))
        _write(d / "packets_all.jsonl", "".join(json.dumps(p, sort_keys=True) + "\n" for p in packets))
        accepted, decisions = apply_judge.decide(mr, packets, answers)
        apply_judge.append_log(apply_judge.LOG, "%s-%s" % (rid, mr["library"]), mr["system"], judge,
                               {"merge": _sha((d / "merge.json").read_bytes()),
                                "packets": _sha((d / "packets_all.jsonl").read_bytes()),
                                "answers": _sha((d / "answers_all.jsonl").read_bytes())}, decisions)
        acc = {g["id"]: ("agreed" if g in mr["agreed"] else "supported")
               for g in mr["agreed"] + mr["contested"] if g["id"] in accepted}
        _write(d / "library_accepted.json", {
            "library": mr["library"], "accepted": [
                {"id": g["id"], "acceptance": acc[g["id"]], "key": g["key"],
                 "fact": sorted(g["instances"], key=lambda i: i["origin"])[0]["fact"]}
                for g in mr["agreed"] + mr["contested"] if g["id"] in acc]})
        lib_acc |= set(acc)
        out["libraries"][mr["library"]] = {
            "agreed": sum(v == "agreed" for v in acc.values()), "supported": sum(v == "supported" for v in acc.values()),
            "decisions": {v: sum(x["verdict"] == v for x in decisions) for v in sorted({x["verdict"] for x in decisions})}}
    for s in ("teastore", "hotel", "otel"):
        d = run2 / s
        mr = json.loads((d / "merge.json").read_text())
        packets = collect(d, ["judge_packets.jsonl"])
        answers = collect(d, ["answers_reused.jsonl"]) + collect(d / "judge", sorted(
            x.name for x in (d / "judge").glob("answers_*.jsonl")))
        _write(d / "answers_all.jsonl", "".join(json.dumps(a, sort_keys=True) + "\n" for a in answers))
        accepted, decisions = apply_judge.decide(mr, packets, answers)
        attached, rlog = resolve(mr, accepted, lib_acc)
        spec, blog = mg.rebuild(mr, accepted, attached=attached, extraction={
            "stage": "final", "procedure": "research/ontology/EXTRACTION_PROTOCOL.md (Amendments 1-3)",
            "runId": "%s-%s" % (rid, s), "judge": judge})
        errs = mg.validate(spec)
        counts = {}
        for f in check_citations.iter_facts(spec):
            a = f[1].get("acceptance")
            counts[a] = counts.get(a, 0) + 1
        spec["extraction"].update(rebuildLog=blog, attachmentResolution=rlog, factsByAcceptance=counts,
                                  acceptedKeys={"agreed": len(mr["agreed"]), "deterministic": len(mr["deterministic"]),
                                                "supported": sum(x["verdict"] == "supported" for x in decisions),
                                                "libraryAttached": len(attached)})
        apply_judge.append_log(apply_judge.LOG, "%s-%s" % (rid, s), s, judge,
                               {"merge": _sha((d / "merge.json").read_bytes()),
                                "packets": _sha((d / "judge_packets.jsonl").read_bytes()),
                                "answers": _sha((d / "answers_all.jsonl").read_bytes())}, decisions)
        _write(d / "final_spec.json", spec)
        res = {"schemaErrors": errs, "factsByAcceptance": counts, "acceptedKeys": spec["extraction"]["acceptedKeys"],
               "attachment": {k: (v if isinstance(v, int) else len(v)) for k, v in rlog.items()},
               "decisions": {v: sum(x["verdict"] == v for x in decisions) for v in sorted({x["verdict"] for x in decisions})},
               "rebuild": {k: len(v) for k, v in blog.items()}}
        if not errs:
            g = spec_to_ttl.spec_to_graph(spec)
            _write(run2 / ("%s.ttl" % s), g.serialize(format="turtle"))
            ok, text = query.validate(g)
            _write(run2 / ("%s.shacl.txt" % s), "conforms: %s\n\n%s" % (ok, text))
            res.update(shaclConforms=ok, triples=len(g),
                       shaclViolations=sum(1 for x in text.splitlines() if x.startswith("Constraint Violation")))
        out["systems"][s] = res
    _write(run2 / "stage45_summary.json", out)
    return out


if __name__ == "__main__":
    main()
