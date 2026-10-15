"""Convert one extracted SUT spec (extraction.schema.json) to a Turtle ABox over omsac.ttl + ops.ttl.

Usage:  uv run python research/ontology/spec_to_ttl.py SPEC.json [-o OUT.ttl]

Deterministic: the same spec gives byte-identical Turtle (sorted serialisation, evidence IRIs are content hashes).
Every triple derived from a fact gets one ev:Evidence record carrying that fact's provenance (shapes.ttl
FactEvidenceShape requires it). The spec is validated against the JSON schema first; references between entities are
not resolved here (a dangling name becomes an untyped node, which SHACL rejects).

Engineering defaults (recorded 2026-10-14): IRIs are <http://obsplacement.example/sut/<sut>#<kind>-<slug>>; a
service's role maps to a class as ROLE_CLASS says (a registry server is an omsac:Microservice: it is deployed like one;
its coordinator role is a separate ops:ServiceRegistry individual hostedBy it).
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import jsonschema
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

HERE = Path(__file__).resolve().parent
SCHEMA = HERE / "extraction.schema.json"
OPS = Namespace("http://obsplacement.example/ops#")
EV = Namespace("http://obsplacement.example/evidence#")
OMSAC = Namespace("http://www.semanticweb.org/ontologyOfMicroservicesArchitecture#")

ROLE_CLASS = {"microservice": OMSAC.Microservice, "registry": OMSAC.Microservice, "loadgen": OMSAC.Microservice,
              "broker": OPS.Broker, "collector": OPS.Collector, "datastore": OMSAC.Database, "cache": OMSAC.Cache,
              "telemetry-backend": OMSAC.Technology, "other": OMSAC.Technology}
SENSOR_CLASS = {"log": OPS.LogTemplate, "span": OPS.Span, "metric": OPS.Metric}
LIVENESS_NUM = ("heartbeatIntervalSeconds", "failureTimeoutSeconds", "cleanupIntervalSeconds")
LIVENESS_BOOL = ("heartbeatThreadIndependentOfWork", "healthCheckConfigured")


def slug(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s))


def validate_spec(spec):
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(spec)


class Builder:
    def __init__(self, spec):
        self.spec = spec
        self.ns = Namespace("http://obsplacement.example/sut/%s#" % spec["sut"])
        self.g = Graph()
        for p, n in (("ops", OPS), ("ev", EV), ("omsac", OMSAC), ("sut", self.ns)):
            self.g.bind(p, n)

    def iri(self, kind, name):
        return self.ns["%s-%s" % (kind, slug(name))]

    def fact(self, s, p, o, f):
        """Add (s, p, o) and its evidence record from fact f."""
        self.g.add((s, p, o))
        src = self.spec["sources"].get(f.get("repo", ""), {})
        key = json.dumps([str(s), str(p), str(o), f.get("repo"), f.get("sourceFile"), f.get("line"),
                          f.get("quotedToken"), f.get("sourceUrl")], sort_keys=True)
        e = self.ns["ev-" + hashlib.sha256(key.encode()).hexdigest()[:16]]
        g = self.g
        g.add((e, RDF.type, EV.Evidence))
        g.add((e, EV.aboutSubject, s))
        g.add((e, EV.aboutPredicate, p))
        g.add((e, EV.aboutObject, o))
        if "sourceFile" in f:
            g.add((e, EV.basis, Literal("cited")))
            g.add((e, EV.sourceRepo, Literal(f["repo"])))
            g.add((e, EV.sourceCommit, Literal(src.get("commit", ""))))
            g.add((e, EV.sourceFile, Literal(f["sourceFile"])))
            g.add((e, EV.sourceLine, Literal(int(f["line"]), datatype=XSD.integer)))
            g.add((e, EV.quotedToken, Literal(f["quotedToken"])))
        else:
            g.add((e, EV.basis, Literal("documented-default")))
            g.add((e, EV.sourceUrl, Literal(f["sourceUrl"])))
        if f.get("note"):
            g.add((e, EV.note, Literal(f["note"])))
        if f.get("acceptance"):
            g.add((e, EV.acceptance, Literal(f["acceptance"])))

    def build(self):
        S = self.spec
        arch = self.iri("arch", S["architecture"]["name"]["value"])
        self.fact(arch, RDF.type, OMSAC.MicroserviceArchitecture, S["architecture"]["name"])
        hostf = S["host"]["id"]
        host = self.iri("host", hostf["value"])
        self.fact(host, RDF.type, OPS.Host, hostf)

        for sv in S["services"]:
            name = sv["name"]["value"]
            s = self.iri("svc", name)
            self.fact(arch, OMSAC.isComposedOf, s, sv["name"])
            self.fact(s, RDF.type, ROLE_CLASS[sv["role"]["value"]], sv["role"])
            c = self.iri("ctr", sv["container"]["value"])
            self.fact(c, RDF.type, OPS.Container, sv["container"])
            self.fact(s, OPS.runsIn, c, sv["container"])
            self.fact(c, OPS.placedOn, host, hostf)
            if "replicas" in sv:
                rs = self.iri("rs", name)
                self.fact(rs, RDF.type, OPS.ReplicaSet, sv["replicas"])
                self.fact(rs, OPS.replicaSetOf, s, sv["replicas"])
                self.fact(rs, OPS.replicaCount, Literal(sv["replicas"]["value"], datatype=XSD.nonNegativeInteger),
                          sv["replicas"])
            for f in sv.get("exportsTelemetryTo", []):
                self.fact(s, OPS.exportsTelemetryTo, self.iri("svc", f["value"]), f)
            for f in sv.get("registersWith", []):
                self.fact(s, OPS.registersWith, self.iri("coord", f["value"]), f)
            for f in sv.get("publishesTo", []):
                self.fact(s, OPS.publishesTo, self.iri("topic", f["value"]), f)
            for cons in sv.get("consumes", []):
                self.fact(s, OPS.consumesFrom, self.iri("topic", cons["topic"]["value"]), cons["topic"])
                if "group" in cons:
                    self.fact(s, OPS.memberOf, self.iri("group", cons["group"]["value"]), cons["group"])
            for se in sv.get("emits", []):
                x = self.iri("sensor", se["id"]["value"])
                self.fact(x, RDF.type, SENSOR_CLASS[se["kind"]], se["id"])
                self.fact(s, OPS.emits, x, se["id"])
                if "measuresLagOf" in se:
                    self.fact(x, OPS.measuresLagOf, self.iri("group", se["measuresLagOf"]["value"]), se["measuresLagOf"])

        for f in S.get("syncEdges", []):
            v = f["value"]
            self.fact(self.iri("svc", v["caller"]), OPS.callsSync, self.iri("svc", v["callee"]), f)

        for t in S.get("topics", []):
            ti = self.iri("topic", t["name"]["value"])
            self.fact(ti, RDF.type, OPS.Topic, t["name"])
            self.fact(ti, OPS.onBroker, self.iri("svc", t["broker"]["value"]), t["broker"])

        for gr in S.get("consumerGroups", []):
            gi = self.iri("group", gr["name"]["value"])
            self.fact(gi, RDF.type, OPS.ConsumerGroup, gr["name"])
            self.fact(gi, OPS.coordinatedBy, self.iri("coord", gr["coordinator"]["value"]), gr["coordinator"])

        for co in S.get("coordinators", []):
            cname = co["name"]["value"]
            ci = self.iri("coord", cname)
            self.fact(ci, RDF.type, OPS[co["type"]["value"]], co["type"])
            self.fact(ci, OPS.hostedBy, self.iri("svc", co["hostedBy"]["value"]), co["hostedBy"])
            for i, lv in enumerate(co.get("liveness", [])):
                li = self.iri("live", "%s-%d" % (cname, i))
                self.fact(li, RDF.type, OPS.LivenessMechanism, lv["mechanism"])
                self.fact(li, OPS.enforcedBy, ci, lv["mechanism"])
                for m in lv["monitors"]:
                    self.fact(li, OPS.monitors, self.iri("svc", m["value"]), m)
                for k in LIVENESS_NUM:
                    if k in lv:
                        self.fact(li, OPS[k], Literal(str(lv[k]["value"]), datatype=XSD.decimal), lv[k])
                for k in LIVENESS_BOOL:
                    if k in lv:
                        self.fact(li, OPS[k], Literal(bool(lv[k]["value"])), lv[k])
        return self.g


def spec_to_graph(spec, validate=True):
    if validate:
        validate_spec(spec)
    return Builder(spec).build()


def spec_to_turtle(spec, validate=True):
    return spec_to_graph(spec, validate).serialize(format="turtle")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec")
    ap.add_argument("-o", "--out")
    a = ap.parse_args(argv)
    ttl = spec_to_turtle(json.loads(Path(a.spec).read_text()))
    if a.out:
        if Path(a.out).exists():
            sys.exit("refusing to overwrite %s (new evidence gets a new path)" % a.out)
        Path(a.out).write_text(ttl)
    else:
        sys.stdout.write(ttl)


if __name__ == "__main__":
    main()
