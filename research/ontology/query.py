"""Validate an ABox against shapes.ttl and run the competency questions in cq/ against it.

Usage:
  uv run python research/ontology/query.py validate ABOX.ttl [ABOX.ttl ...]
  uv run python research/ontology/query.py cq C1|L1|L2|B1|S1 ABOX.ttl [...] [--target NAME] [--kind pause|crash|cpuThrottle|netDelay] [--json]
  uv run python research/ontology/query.py spec SPEC.json [--cq C1 ...]     (convert a spec in memory, validate, then query)

The TBox (omsac.ttl + ops.ttl) is always loaded; an ABox is any Turtle produced by spec_to_ttl.py. --target is a
service name; it is resolved against the ABox's sut namespace(s) by local name `svc-<name>`.
"""
import argparse
import json
import sys
from pathlib import Path

from pyshacl import validate as shacl_validate
from rdflib import Graph, Literal, Namespace, URIRef

HERE = Path(__file__).resolve().parent
TBOX = (HERE / "omsac.ttl", HERE / "ops.ttl")
SHAPES = HERE / "shapes.ttl"
CQ_DIR = HERE / "cq"
OPS = Namespace("http://obsplacement.example/ops#")
CQS = {"C1": "CQ-C1_coordinator_class.rq", "L1": "CQ-L1_lanes.rq", "L2": "CQ-L2_coordinator_window.rq",
       "B1": "CQ-B1_blast_radius.rq", "S1": "CQ-S1_shared_fate.rq"}
KINDS = {"pause": OPS.pause, "crash": OPS.crash, "cpuThrottle": OPS.cpuThrottle, "cpu-throttle": OPS.cpuThrottle,
         "netDelay": OPS.netDelay, "net-delay": OPS.netDelay}


def tbox():
    g = Graph()
    for p in TBOX:
        g.parse(p, format="turtle")
    return g


def load(*aboxes):
    """TBox + the given ABoxes (paths or rdflib Graphs) in one graph."""
    g = tbox()
    for a in aboxes:
        if isinstance(a, Graph):
            g += a
        else:
            g.parse(a, format="turtle")
    return g


def validate(abox):
    """-> (conforms, results text). abox: a Graph (ABox only). The TBox is the ontology graph (subclass-aware targets)."""
    shapes = Graph().parse(SHAPES, format="turtle")
    conforms, _, text = shacl_validate(abox, shacl_graph=shapes, ont_graph=tbox(), inference="none",
                                       advanced=True, allow_warnings=False)
    return bool(conforms), text


def _py(v):
    if v is None:
        return None
    if isinstance(v, Literal):
        return v.toPython()
    s = str(v)
    return s.rsplit("#", 1)[-1] if "#" in s else s


def resolve_target(g, name):
    """Service IRIs whose local name is svc-<name> (one per sut namespace)."""
    return sorted({s for s in g.subjects() if isinstance(s, URIRef) and str(s).endswith("#svc-" + name)})


def run_cq(name, g, target=None, kind=None):
    """Rows (dicts, local names for IRIs) of competency question `name` on graph g (TBox included)."""
    q = (CQ_DIR / CQS[name]).read_text()
    targets = resolve_target(g, target) if target else [None]
    if target and not targets:
        raise SystemExit("target %r not found (expected an IRI ending in #svc-%s)" % (target, target))
    rows = []
    for t in targets:
        b = {}
        if t is not None:
            b["target"] = t
        if kind is not None and name != "B1" and name != "S1":
            b["kind"] = KINDS[kind] if isinstance(kind, str) else kind
        res = g.query(q, initBindings=b)
        for r in res:
            rows.append({str(v): _py(r[v]) for v in res.vars})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("aboxes", nargs="+")
    c = sub.add_parser("cq")
    c.add_argument("name", choices=sorted(CQS))
    c.add_argument("aboxes", nargs="+")
    s = sub.add_parser("spec")
    s.add_argument("spec")
    s.add_argument("--cq", choices=sorted(CQS))
    for p in (c, s):
        p.add_argument("--target")
        p.add_argument("--kind", choices=sorted(KINDS))
        p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "validate":
        ab = Graph()
        for p in a.aboxes:
            ab.parse(p, format="turtle")
        ok, text = validate(ab)
        print(text)
        sys.exit(0 if ok else 1)

    if a.cmd == "spec":
        sys.path.insert(0, str(HERE))
        import spec_to_ttl
        ab = spec_to_ttl.spec_to_graph(json.loads(Path(a.spec).read_text()))
        ok, text = validate(ab)
        print("SHACL conforms: %s" % ok)
        if not ok:
            print(text)
        if not a.cq:
            sys.exit(0 if ok else 1)
        g, name = load(ab), a.cq
    else:
        g, name = load(*a.aboxes), a.name
    rows = run_cq(name, g, a.target, a.kind)
    if a.json:
        print(json.dumps(rows, indent=1, default=str))
    else:
        if rows:
            cols = list(rows[0])
            print("\t".join(cols))
            for r in rows:
                print("\t".join("" if r[k] is None else str(r[k]) for k in cols))
        print("%d rows" % len(rows))


if __name__ == "__main__":
    main()
