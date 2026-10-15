"""Stage 3 of the extraction procedure: citation check, then merge into agreed / contested. EXTRACTION_PROTOCOL.md.

Usage:  uv run python research/ontology/merge.py SYSTEM --stage1 S1.json [--a A1.json ...] [--b B1.json ...] -o MERGE.json

Inputs are specs in extraction.schema.json: stage 1 (one file) and any number of files per extractor (one per service
is expected). Steps, all mechanical:
1. Every input's `sources` is replaced by the pinned sources of the stage-1 spec (an extractor cannot choose the
   commit it is checked at; a difference is logged). A file that fails the JSON schema contributes no facts (logged):
   stage 1 against extraction.schema.json, an extractor file against fragment_schema() (no architecture/host/role
   required, since the fixed prompt does not ask for them; every present fact validated as in the full schema).
2. Every fact is flattened to (subject, relation, object) (FLATTEN below) and checked by check_citations.check_fact
   at the pinned commit (+-2 lines). A `fail` is dropped and logged with its count per origin; a documented default
   is kept as `unchecked-default` (never `ok`).
3. Normalisation (engineering default, recorded 2026-10-14): a name is stripped and lower-cased; for a name in a
   service-valued slot (service, caller, callee, exportsTelemetryTo, hostedBy, monitors, broker) the host part of a
   `scheme://user@host:port/path` form is taken first. A name that is a compose alias (service key, container_name,
   hostname, network alias: inputs.Compose.aliases) becomes that compose service name; no other alias is resolved.
   Numbers compare as floats, booleans as booleans, enums exactly.
4. A key reported by both extractors A and B is **agreed**; every other key (one extractor only, stage 1 only, or
   stage 1 plus one extractor) is **contested**. Agreement = agreed / (agreed + contested), per system and per
   relation.
4a. Amendment 2 (2026-10-14): a stage-1 fact produced by one of the five documented rules (deterministic_rule():
   architecture name = system id; host from research/host-topology.json; role from the image-name lookup D1;
   container = compose service key D2; replicas 1 when unset D3) whose citation check passes (`ok`; for the D3
   documented default, which cites a URL, `unchecked-default`) and that is not agreed is **deterministic**: it enters
   the final spec without the judge, labelled `acceptance: deterministic`. Every other stage-1 fact is unchanged
   (agreed only if A and B report it, else contested). Agreement is reported over all facts as in run1
   (agreed / all keys) and over extractor-reportable facts only (relations other than architecture name, host id,
   role, which the fixed prompt does not ask for).
4b. Amendment 3, Change 2 (identifier normalisation, normalise_ids=True): coordinator, liveness and consumer-group
   references are keyed by (coordinator service name as in the compose file, mechanism type) with the type from the
   fixed list MECHANISM (ConsumerGroupCoordinator -> consumer-group-session, ServiceRegistry -> registry-heartbeat,
   DiscoveryService -> discovery-registration), written `<service>/<type>`, never by extractor free text. A
   coordinator maps when its hostedBy resolves to a compose service (alias table) and its type is in the list; its
   liveness records become (key, type), so differently named records of one coordinator merge. A coordinatedBy /
   registersWith name maps through a coordinator of the same input file of that name, else (consumer groups) to
   (compose service, consumer-group-session) if the name is a compose alias, else (registersWith) to the compose
   service's single coordinator type seen in any input. An identifier that maps to none keeps its free-text key, is
   logged (log.unmappedIdentifiers) and its key is always contested (never agreed or deterministic).
5. The final spec is rebuilt from accepted keys only (rebuild()): agreed, deterministic, plus contested keys a judge
   marked `supported` (apply_judge.py); each fact carries its `acceptance`. An entity whose required facts were not all accepted (a service needs name, role,
   container; a topic name + broker; a group name + coordinator; a coordinator name + type + hostedBy; a liveness
   mechanism + >= 1 monitored member) is not emitted, and every fact attached to it is logged as orphaned. Provenance
   of an accepted key: the first passing instance in origin order A, B, stage1, cited before documented-default.
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
sys.path.insert(0, str(HERE))
import check_citations  # noqa: E402

SCHEMA = json.loads((HERE / "extraction.schema.json").read_text())


def fragment_schema(schema=SCHEMA):
    """The schema an extractor output (one service's facts) is validated against: extraction.schema.json with the
    top level requiring only schemaVersion, sut, sources and a service requiring only its name. The fixed prompt
    does not ask for the architecture, the host or a service's role, so requiring them would reject every extractor
    output; every fact that is present is still validated exactly as in the full schema. The final spec is validated
    against the full schema."""
    f = copy.deepcopy(schema)
    f["required"] = ["schemaVersion", "sut", "sources"]
    f["$defs"]["service"]["required"] = ["name"]
    return f


FRAGMENT = fragment_schema()
ORIGINS = ("A", "B", "stage1")
SERVICE_SLOTS = {"service", "caller", "callee", "exportsTelemetryTo", "hostedBy", "monitors", "broker"}
LIVENESS_NUM = ("heartbeatIntervalSeconds", "failureTimeoutSeconds", "cleanupIntervalSeconds")
LIVENESS_BOOL = ("heartbeatThreadIndependentOfWork", "healthCheckConfigured")
PROV_KEYS = ("basis", "repo", "sourceFile", "line", "quotedToken", "note", "sourceUrl")
# relations the fixed stage-2 prompt does not ask for (Amendment 1.1): excluded from the reportable-only agreement
NOT_REPORTABLE = {"name", "id", "role"}
MECHANISM = {"ConsumerGroupCoordinator": "consumer-group-session", "ServiceRegistry": "registry-heartbeat",
             "DiscoveryService": "discovery-registration"}
COORD_SUBJECT_RELS = {"coordinator", "coordinatorType", "hostedBy"}
LIVENESS_RELS = {"liveness", "monitors", "heartbeatIntervalSeconds", "failureTimeoutSeconds", "cleanupIntervalSeconds",
                 "heartbeatThreadIndependentOfWork", "healthCheckConfigured"}


def _coord_table(spec, aliases):
    """{normalised coordinator name: canonical key or None} for the coordinators of one spec."""
    out = {}
    for co in spec.get("coordinators", []):
        svc = norm_name(co["hostedBy"]["value"], aliases, True)
        mech = MECHANISM.get(co["type"]["value"])
        key = "%s/%s" % (svc, mech) if svc in set(aliases.values()) and mech else None
        out[norm_name(co["name"]["value"], aliases, False)] = key
    return out


def canonicalise(rec, local, global_types, aliases):
    """Rewrite a flattened record's coordinator/liveness/group identifiers to canonical keys (step 4b).
    -> None if mapped or not applicable, else the reason it could not be mapped."""
    rel = rec["relation"]
    services = set(aliases.values())

    def ref(name, group):
        n = norm_name(name, aliases, False)
        if local.get(n):
            return local[n]
        svc = norm_name(name, aliases, True)
        if svc in services:
            if group:
                return "%s/consumer-group-session" % svc
            types = global_types.get(svc, set())
            if len(types) == 1:
                return "%s/%s" % (svc, next(iter(types)))
        return None

    if rel in COORD_SUBJECT_RELS:
        k = local.get(norm_name(rec["subject"], aliases, False))
        if not k:
            return "coordinator %r: hostedBy not a compose service or type not in MECHANISM" % rec["subject"]
        rec["subject"] = k
        if rel == "coordinator":
            rec["object"] = k
        return None
    if rel in LIVENESS_RELS:
        k = local.get(norm_name(rec["subject"][0], aliases, False))
        if not k:
            return "liveness of coordinator %r: coordinator does not map" % rec["subject"][0]
        mech = k.split("/", 1)[1]
        rec["subject"] = [k, mech]
        if rel == "liveness":
            rec["object"] = mech
        return None
    if rel == "coordinatedBy":
        k = ref(rec["object"], True)
        if not k:
            return "coordinatedBy %r maps to no compose coordinator" % rec["object"]
        rec["object"] = k
        return None
    if rel == "registersWith":
        k = ref(rec["object"], False)
        if not k:
            return "registersWith %r maps to no compose coordinator" % rec["object"]
        rec["object"] = k
        return None
    return None


def deterministic_rule(origin, rec, sut):
    """Name of the Amendment-2 rule that produced this stage-1 fact, or None (then it is an ordinary fact)."""
    if origin != "stage1":
        return None
    p, f = rec["path"], rec["fact"]
    note = f.get("note", "")
    if p == "$.architecture.name" and f.get("value") == sut and note.startswith("architecture = the services of"):
        return "architecture-name"
    if p == "$.host.id" and str(f.get("sourceFile", "")).endswith("research/host-topology.json") and \
            f.get("quotedToken") == '"hostId": "%s"' % f.get("value"):
        return "host-topology"
    if re.fullmatch(r"\$\.services\[\d+\]\.role", p) and note.startswith("stage-1 rule D1"):
        return "role-image-lookup"
    if re.fullmatch(r"\$\.services\[\d+\]\.container", p) and note.startswith("stage-1 rule D2") and \
            f.get("value") == rec["subject"] and f.get("quotedToken") == "%s:" % rec["subject"]:
        return "container-service-key"
    if re.fullmatch(r"\$\.services\[\d+\]\.replicas", p) and note.startswith("stage-1 rule D3") and \
            f.get("basis") == "documented-default" and f.get("value") == 1:
        return "replicas-default-1"
    return None

# ============================================================================================ flatten


def _prov(f):
    return {k: f[k] for k in PROV_KEYS if k in f}


def flatten(spec):
    """-> [dict(subject, relation, object, slots, fact, path)]. `slots` names the kind of subject/object for
    normalisation; `fact` is the provenance-bearing object (its value is the object or the subject)."""
    out = []

    def add(subj, rel, obj, fact, path, sslot, oslot):
        out.append({"subject": subj, "relation": rel, "object": obj, "fact": fact, "path": path,
                    "slots": [sslot, oslot]})

    if "architecture" in spec:
        f = spec["architecture"]["name"]
        add("architecture", "name", f["value"], f, "$.architecture.name", "const", "name")
    if "host" in spec:
        f = spec["host"]["id"]
        add("host", "id", f["value"], f, "$.host.id", "const", "name")
    for i, sv in enumerate(spec.get("services", [])):
        p = "$.services[%d]" % i
        n = sv["name"]["value"]
        add(n, "service", n, sv["name"], p + ".name", "service", "service")
        if "role" in sv:
            add(n, "role", sv["role"]["value"], sv["role"], p + ".role", "service", "enum")
        if "container" in sv:
            add(n, "container", sv["container"]["value"], sv["container"], p + ".container", "service", "name")
        if "replicas" in sv:
            add(n, "replicas", sv["replicas"]["value"], sv["replicas"], p + ".replicas", "service", "number")
        for k, slot in (("exportsTelemetryTo", "exportsTelemetryTo"), ("registersWith", "name"),
                        ("publishesTo", "name")):
            for j, f in enumerate(sv.get(k, [])):
                add(n, k, f["value"], f, "%s.%s[%d]" % (p, k, j), "service", slot)
        for j, c in enumerate(sv.get("consumes", [])):
            t = c["topic"]["value"]
            add(n, "consumes", t, c["topic"], "%s.consumes[%d].topic" % (p, j), "service", "name")
            if "group" in c:
                add(n, "consumesWithGroup", [t, c["group"]["value"]], c["group"], "%s.consumes[%d].group" % (p, j),
                    "service", "pair")
        for j, se in enumerate(sv.get("emits", [])):
            add(n, "emits:" + se["kind"], se["id"]["value"], se["id"], "%s.emits[%d].id" % (p, j), "service", "name")
            if "measuresLagOf" in se:
                add([n, se["id"]["value"]], "measuresLagOf", se["measuresLagOf"]["value"], se["measuresLagOf"],
                    "%s.emits[%d].measuresLagOf" % (p, j), "pair-svc", "name")
    for i, f in enumerate(spec.get("syncEdges", [])):
        add(f["value"]["caller"], "callsSync", f["value"]["callee"], f, "$.syncEdges[%d]" % i, "caller", "callee")
    for i, t in enumerate(spec.get("topics", [])):
        n = t["name"]["value"]
        add(n, "topic", n, t["name"], "$.topics[%d].name" % i, "name", "name")
        add(n, "onBroker", t["broker"]["value"], t["broker"], "$.topics[%d].broker" % i, "name", "broker")
    for i, g in enumerate(spec.get("consumerGroups", [])):
        n = g["name"]["value"]
        add(n, "consumerGroup", n, g["name"], "$.consumerGroups[%d].name" % i, "name", "name")
        add(n, "coordinatedBy", g["coordinator"]["value"], g["coordinator"], "$.consumerGroups[%d].coordinator" % i,
            "name", "name")
    for i, co in enumerate(spec.get("coordinators", [])):
        n, p = co["name"]["value"], "$.coordinators[%d]" % i
        add(n, "coordinator", n, co["name"], p + ".name", "name", "name")
        add(n, "coordinatorType", co["type"]["value"], co["type"], p + ".type", "name", "enum")
        add(n, "hostedBy", co["hostedBy"]["value"], co["hostedBy"], p + ".hostedBy", "name", "hostedBy")
        for j, lv in enumerate(co.get("liveness", [])):
            lp = "%s.liveness[%d]" % (p, j)
            L = [n, lv["mechanism"]["value"]]
            add(L, "liveness", lv["mechanism"]["value"], lv["mechanism"], lp + ".mechanism", "pair", "name")
            for k, m in enumerate(lv["monitors"]):
                add(L, "monitors", m["value"], m, "%s.monitors[%d]" % (lp, k), "pair", "monitors")
            for k in LIVENESS_NUM:
                if k in lv:
                    add(L, k, lv[k]["value"], lv[k], "%s.%s" % (lp, k), "pair", "number")
            for k in LIVENESS_BOOL:
                if k in lv:
                    add(L, k, lv[k]["value"], lv[k], "%s.%s" % (lp, k), "pair", "bool")
    return out

# ============================================================================================ normalisation


def _host(s):
    p = re.sub(r"^[A-Za-z][A-Za-z0-9+.-]*://", "", s.strip())
    p = p.split("@")[-1]
    return re.split(r"[:/]", p, maxsplit=1)[0]


def norm_name(x, aliases, service_slot):
    s = str(x).strip().lower()
    if service_slot:
        h = _host(s)
        if h in aliases:
            return aliases[h]
    return aliases.get(s, s)


def norm(x, slot, aliases):
    if slot == "number":
        return repr(float(x))
    if slot == "bool":
        return bool(x)
    if slot in ("enum", "const"):
        return str(x)
    if slot in ("pair", "pair-svc"):
        return [norm_name(v, aliases, slot == "pair-svc" and i == 0) for i, v in enumerate(x)]
    return norm_name(x, aliases, slot in SERVICE_SLOTS)


def key_of(rec, aliases):
    s = norm(rec["subject"], rec["slots"][0], aliases)
    o = norm(rec["object"], rec["slots"][1], aliases)
    return json.dumps([s, rec["relation"], o], sort_keys=True)


def fact_digest(key):
    return hashlib.sha256(key.encode()).hexdigest()[:16]

# ============================================================================================ merge


def _load(p):
    return json.loads(Path(p).read_text()) if not isinstance(p, dict) else p


def merge(stage1, a_specs=(), b_specs=(), aliases=None, root=check_citations.ROOT, labels=None, normalise_ids=True):
    """-> merge result dict. stage1 / a_specs / b_specs: paths or dicts. aliases: {alias: service} (compose)."""
    s1 = _load(stage1)
    pinned = s1["sources"]
    aliases = aliases or {}
    reader = check_citations.SourceReader(pinned, root)
    validators = {"stage1": jsonschema.Draft202012Validator(SCHEMA), "A": jsonschema.Draft202012Validator(FRAGMENT),
                  "B": jsonschema.Draft202012Validator(FRAGMENT)}
    log = {"inputs": [], "schemaRejected": [], "sourcesReplaced": [], "dropped": [],
           "droppedCount": {o: 0 for o in ORIGINS}, "checkedCount": {o: 0 for o in ORIGINS},
           "uncheckedDefaultCount": {o: 0 for o in ORIGINS}}
    groups = {}
    valid = []
    for origin, specs in (("A", a_specs), ("B", b_specs), ("stage1", [s1])):
        for i, sp in enumerate(specs):
            name = sp if isinstance(sp, str) else (labels or {}).get((origin, i), "%s[%d]" % (origin, i))
            spec = copy.deepcopy(_load(sp))
            raw = json.dumps(spec, sort_keys=True).encode()
            log["inputs"].append({"origin": origin, "input": str(name), "sha256": hashlib.sha256(raw).hexdigest()})
            errs = sorted(validators[origin].iter_errors(spec), key=lambda e: list(e.path))
            if errs:
                log["schemaRejected"].append({"origin": origin, "input": str(name),
                                              "errors": [e.message[:300] for e in errs[:10]]})
                continue
            if spec.get("sources") != pinned:
                log["sourcesReplaced"].append({"origin": origin, "input": str(name), "had": spec.get("sources")})
                spec["sources"] = pinned
            if spec.get("sut") != s1["sut"]:
                log["schemaRejected"].append({"origin": origin, "input": str(name),
                                              "errors": ["sut %r != %r" % (spec.get("sut"), s1["sut"])]})
                continue
            valid.append((origin, name, spec))
    global_types = {}
    if normalise_ids:
        log["unmappedIdentifiers"] = []
        for _, _, spec in valid:
            for k in _coord_table(spec, aliases).values():
                if k:
                    svc, mech = k.split("/", 1)
                    global_types.setdefault(svc, set()).add(mech)
    for origin, name, spec in valid:
        local = _coord_table(spec, aliases) if normalise_ids else {}
        for rec in flatten(spec):
            r = check_citations.check_fact(reader, rec["fact"])
            log["checkedCount"][origin] += 1
            if r["status"] == "fail":
                log["droppedCount"][origin] += 1
                log["dropped"].append({"origin": origin, "input": str(name), "path": rec["path"],
                                       "relation": rec["relation"], "fact": rec["fact"], "check": r})
                continue
            if r["status"] == "unchecked-default":
                log["uncheckedDefaultCount"][origin] += 1
            unmapped = canonicalise(rec, local, global_types, aliases) if normalise_ids else None
            if unmapped:
                log["unmappedIdentifiers"].append({"origin": origin, "input": str(name), "path": rec["path"],
                                                   "relation": rec["relation"], "reason": unmapped})
            k = key_of(rec, aliases)
            inst = {"origin": origin, "input": str(name), "path": rec["path"], "subject": rec["subject"],
                    "object": rec["object"], "slots": rec["slots"], "fact": rec["fact"], "check": r["status"]}
            if unmapped:
                inst["unmappedIdentifier"] = unmapped
            rule = deterministic_rule(origin, rec, s1["sut"])
            if rule and (r["status"] == "ok" or (rule == "replicas-default-1" and r["status"] == "unchecked-default")):
                inst["deterministicRule"] = rule
            g = groups.setdefault(k, {"key": json.loads(k), "relation": rec["relation"], "instances": []})
            g["instances"].append(inst)
    agreed, contested, deterministic = [], [], []
    for k in sorted(groups):
        g = groups[k]
        origins = sorted({i["origin"] for i in g["instances"]}, key=ORIGINS.index)
        g["origins"] = origins
        g["id"] = fact_digest(k)
        if any(i.get("unmappedIdentifier") for i in g["instances"]):
            g["unmappedIdentifier"] = True
            contested.append(g)
        elif "A" in origins and "B" in origins:
            agreed.append(g)
        elif any(i.get("deterministicRule") for i in g["instances"]):
            g["deterministicRule"] = next(i["deterministicRule"] for i in g["instances"] if i.get("deterministicRule"))
            deterministic.append(g)
        else:
            contested.append(g)
    by_rel = {}
    for status, gs in (("agreed", agreed), ("contested", contested), ("deterministic", deterministic)):
        for g in gs:
            d = by_rel.setdefault(g["relation"], {"agreed": 0, "contested": 0, "deterministic": 0})
            d[status] += 1
    for d in by_rel.values():
        n = d["agreed"] + d["contested"] + d["deterministic"]
        d["agreement"] = d["agreed"] / n if n else None
    allk = agreed + contested + deterministic
    rep = [g for g in allk if g["relation"] not in NOT_REPORTABLE]
    rep_a = sum(1 for g in rep if g in agreed)
    return {
        "mergeVersion": 2, "system": s1["sut"], "sources": pinned, "aliases": aliases,
        "normalisation": "merge.py docstring step 3", "amendment": "EXTRACTION_PROTOCOL Amendment 2 (step 4a)",
        "identifierNormalisation": "Amendment 3 change 2 (step 4b)" if normalise_ids else None,
        "agreement": {"agreed": len(agreed), "contested": len(contested), "deterministic": len(deterministic),
                      "agreement": len(agreed) / len(allk) if allk else None,
                      "definition": "agreed / all keys (agreed + contested + deterministic), as in run1",
                      "reportable": {"agreed": rep_a, "keys": len(rep), "agreement": rep_a / len(rep) if rep else None,
                                     "definition": "over relations the prompt asks for (not %s)" %
                                                   ", ".join(sorted(NOT_REPORTABLE))},
                      "byRelation": by_rel},
        "log": log, "agreed": agreed, "contested": contested, "deterministic": deterministic,
    }

# ============================================================================================ rebuild


def _choose(g):
    """Provenance-bearing instance of an accepted group: origin order A, B, stage1; cited before defaults. A
    deterministic group's provenance is its rule-derived stage-1 instance."""
    if g.get("deterministicRule"):
        return next(i for i in g["instances"] if i.get("deterministicRule"))
    inst = sorted(g["instances"], key=lambda i: ((ORIGINS + ("library",)).index(i["origin"]), i["check"] != "ok"))
    return inst[0]


def _val(g, which, aliases):
    """Canonical subject/object value for references: the compose service name if the alias table resolved it,
    else the chosen instance's own value."""
    i = _choose(g)
    raw, slot = i[which], i["slots"][0 if which == "subject" else 1]
    if slot in ("pair", "pair-svc"):
        return [_val1(v, aliases, slot == "pair-svc" and n == 0) for n, v in enumerate(raw)]
    if slot in ("number", "bool", "enum", "const"):
        return raw
    return _val1(raw, aliases, slot in SERVICE_SLOTS)


def _val1(raw, aliases, service_slot):
    n = norm_name(raw, aliases, service_slot)
    return n if n in aliases.values() else str(raw).strip()


def acceptance_of(merge_result, accepted_ids):
    """{id: agreed|deterministic|supported} for the accepted ids."""
    out = {}
    for g in merge_result["agreed"]:
        out[g["id"]] = "agreed"
    for g in merge_result.get("deterministic", []):
        out[g["id"]] = "deterministic"
    for g in merge_result["contested"]:
        out[g["id"]] = "supported"
    return {k: v for k, v in out.items() if k in accepted_ids}


def rebuild(merge_result, accepted_ids, sut=None, extraction=None, attached=()):
    """Final spec from accepted group ids. -> (spec, log). Each fact carries `acceptance`. `attached`: pseudo-groups
    accepted only through an Amendment-3 library attachment (library_merge.resolve); acceptance `library`. A key
    accepted by the system procedure keeps that acceptance and provenance."""
    aliases = merge_result["aliases"]
    acc = acceptance_of(merge_result, accepted_ids)
    groups = [g for g in merge_result["agreed"] + merge_result.get("deterministic", []) + merge_result["contested"]
              if g["id"] in accepted_ids]
    for g in attached:
        if g["id"] not in acc:
            acc[g["id"]] = "library"
            groups.append(g)
    by_rel = {}
    for g in groups:
        by_rel.setdefault(g["relation"], []).append(g)
    log = {"incomplete": [], "orphaned": []}

    def fact(g, value):
        f = {"value": value}
        f.update(_prov(_choose(g)["fact"]))
        f["acceptance"] = acc[g["id"]]
        return f

    def keyed(rel):
        out = {}
        for g in by_rel.get(rel, []):
            out.setdefault(json.dumps(g["key"][0]), []).append(g)
        return out

    spec = {"schemaVersion": 1, "sut": sut or merge_result["system"], "sources": merge_result["sources"]}
    if extraction:
        spec["extraction"] = extraction
    used = set()
    for rel, field, sub in (("name", "architecture", "name"), ("id", "host", "id")):
        gs = [g for g in by_rel.get(rel, []) if g["key"][0] == field]
        if gs:
            spec[field] = {sub: fact(gs[0], _val(gs[0], "object", aliases))}
            used.update(g["id"] for g in gs[:1])
            if len(gs) > 1:
                log["incomplete"].append({"entity": field, "reason": "several accepted values; first by key kept",
                                          "ids": [g["id"] for g in gs]})
        else:
            log["incomplete"].append({"entity": field, "reason": "no accepted fact"})

    names, roles, ctrs = keyed("service"), keyed("role"), keyed("container")
    services = []
    for sk in sorted(set(names) | set(roles) | set(ctrs) | set(keyed("replicas"))):
        if not (names.get(sk) and roles.get(sk) and ctrs.get(sk)):
            log["incomplete"].append({"entity": "service", "subject": json.loads(sk),
                                      "missing": [r for r, d in (("name", names), ("role", roles),
                                                                 ("container", ctrs)) if not d.get(sk)]})
            continue
        ng = names[sk][0]
        sname = _val(ng, "subject", aliases)
        sv = {"name": fact(ng, sname), "role": fact(roles[sk][0], _val(roles[sk][0], "object", aliases)),
              "container": fact(ctrs[sk][0], _val(ctrs[sk][0], "object", aliases))}
        used.update([ng["id"], roles[sk][0]["id"], ctrs[sk][0]["id"]])
        for rel in ("role", "container"):
            for extra in keyed(rel)[sk][1:]:
                log["incomplete"].append({"entity": "service", "subject": sname, "reason": "second %s dropped" % rel,
                                          "id": extra["id"]})
        rp = keyed("replicas").get(sk, [])
        if rp:
            sv["replicas"] = fact(rp[0], int(_val(rp[0], "object", aliases)))
            used.add(rp[0]["id"])
        for rel in ("exportsTelemetryTo", "registersWith", "publishesTo"):
            gs = keyed(rel).get(sk, [])
            if gs:
                sv[rel] = [fact(g, _val(g, "object", aliases)) for g in gs]
                used.update(g["id"] for g in gs)
        cons = keyed("consumes").get(sk, [])
        if cons:
            sv["consumes"] = []
            withg = keyed("consumesWithGroup").get(sk, [])
            for g in cons:
                t = _val(g, "object", aliases)
                c = {"topic": fact(g, t)}
                gg = [x for x in withg if json.dumps(x["key"][2][0]) == json.dumps(g["key"][2])]
                if gg:
                    c["group"] = fact(gg[0], _val(gg[0], "object", aliases)[1])
                    used.add(gg[0]["id"])
                sv["consumes"].append(c)
                used.add(g["id"])
        em = []
        for rel in ("emits:log", "emits:span", "emits:metric"):
            for g in keyed(rel).get(sk, []):
                e = {"kind": rel.split(":")[1], "id": fact(g, _val(g, "object", aliases))}
                lag = [x for x in by_rel.get("measuresLagOf", [])
                       if json.dumps(x["key"][0]) == json.dumps([json.loads(sk), g["key"][2]])]
                if lag:
                    e["measuresLagOf"] = fact(lag[0], _val(lag[0], "object", aliases))
                    used.add(lag[0]["id"])
                em.append(e)
                used.add(g["id"])
        if em:
            sv["emits"] = em
        services.append(sv)
    spec["services"] = services

    edges = [fact(g, {"caller": _val(g, "subject", aliases), "callee": _val(g, "object", aliases)})
             for g in by_rel.get("callsSync", [])]
    used.update(g["id"] for g in by_rel.get("callsSync", []))
    if edges:
        spec["syncEdges"] = edges

    def entity(rel_name, rel_other, out_field, other_field):
        a, b = keyed(rel_name), keyed(rel_other)
        res = []
        for sk in sorted(set(a) | set(b)):
            if not (a.get(sk) and b.get(sk)):
                log["incomplete"].append({"entity": out_field, "subject": json.loads(sk),
                                          "missing": [r for r, d in ((rel_name, a), (rel_other, b)) if not d.get(sk)]})
                continue
            res.append({"name": fact(a[sk][0], _val(a[sk][0], "subject", aliases)),
                        other_field: fact(b[sk][0], _val(b[sk][0], "object", aliases))})
            used.update([a[sk][0]["id"], b[sk][0]["id"]])
        return res

    topics = entity("topic", "onBroker", "topics", "broker")
    if topics:
        spec["topics"] = topics
    cgs = entity("consumerGroup", "coordinatedBy", "consumerGroups", "coordinator")
    if cgs:
        spec["consumerGroups"] = cgs

    nm, ty, hb = keyed("coordinator"), keyed("coordinatorType"), keyed("hostedBy")
    coords = []
    for sk in sorted(set(nm) | set(ty) | set(hb)):
        if not (nm.get(sk) and ty.get(sk) and hb.get(sk)):
            log["incomplete"].append({"entity": "coordinator", "subject": json.loads(sk),
                                      "missing": [r for r, d in (("name", nm), ("type", ty), ("hostedBy", hb))
                                                  if not d.get(sk)]})
            continue
        cname = _val(nm[sk][0], "subject", aliases)
        co = {"name": fact(nm[sk][0], cname), "type": fact(ty[sk][0], _val(ty[sk][0], "object", aliases)),
              "hostedBy": fact(hb[sk][0], _val(hb[sk][0], "object", aliases))}
        used.update([nm[sk][0]["id"], ty[sk][0]["id"], hb[sk][0]["id"]])
        lvs = []
        for g in by_rel.get("liveness", []):
            if json.dumps(g["key"][0][0]) != sk:
                continue
            L = json.dumps(g["key"][0])
            mons = [x for x in by_rel.get("monitors", []) if json.dumps(x["key"][0]) == L]
            if not mons:
                log["incomplete"].append({"entity": "liveness", "subject": g["key"][0], "missing": ["monitors"]})
                continue
            lv = {"mechanism": fact(g, _val(g, "object", aliases)),
                  "monitors": [fact(x, _val(x, "object", aliases)) for x in mons]}
            used.add(g["id"])
            used.update(x["id"] for x in mons)
            for k in LIVENESS_NUM + LIVENESS_BOOL:
                xs = [x for x in by_rel.get(k, []) if json.dumps(x["key"][0]) == L]
                if xs:
                    lv[k] = fact(xs[0], _val(xs[0], "object", aliases))
                    used.add(xs[0]["id"])
            lvs.append(lv)
        if lvs:
            co["liveness"] = lvs
        coords.append(co)
    if coords:
        spec["coordinators"] = coords

    for g in groups:
        if g["id"] not in used:
            log["orphaned"].append({"id": g["id"], "key": g["key"]})
    return spec, log


def validate(spec):
    errs = list(jsonschema.Draft202012Validator(SCHEMA).iter_errors(spec))
    return [e.message[:300] for e in errs]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("system")
    ap.add_argument("--stage1", required=True)
    ap.add_argument("--a", nargs="*", default=[])
    ap.add_argument("--b", nargs="*", default=[])
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args(argv)
    import inputs
    repos = inputs.open_repos(a.system)
    aliases = inputs.Compose(a.system, repos).aliases()
    res = merge(a.stage1, a.a, a.b, {k.lower(): v for k, v in aliases.items()})
    if Path(a.out).exists():
        sys.exit("refusing to overwrite %s" % a.out)
    Path(a.out).write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({"agreement": res["agreement"], "dropped": res["log"]["droppedCount"],
                      "schemaRejected": len(res["log"]["schemaRejected"])}, indent=1))


if __name__ == "__main__":
    main()
