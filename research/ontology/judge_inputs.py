"""Stage 4 input: one judge packet per contested fact (EXTRACTION_PROTOCOL.md, "Stage 4").

Usage:  uv run python research/ontology/judge_inputs.py MERGE.json -o PACKETS.jsonl

Each line is one contested key: the fact (subject, relation, object), its id and digest, and every instance that
reported it (origin, cited file:line, quotedToken, note) with the cited lines +-10 read at the pinned commit (a
documented default carries its URL instead). The judge answers, per id, exactly one of `supported`,
`not supported`, `not decidable from these lines`, with a one-sentence reason (apply_judge.py reads the answers).
Nothing in a packet tells the judge which answer is expected.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_citations  # noqa: E402

CONTEXT = 10
INSTRUCTION = ("Decide from the cited lines only whether they state the fact. Answer exactly one of: supported / "
               "not supported / not decidable from these lines, with a one-sentence reason.")
VERDICTS = ("supported", "not supported", "not decidable")


def packet_digest(p):
    """Digest over the packet's fact and evidence (not its own digest field)."""
    q = {k: v for k, v in p.items() if k != "packetDigest"}
    return hashlib.sha256(json.dumps(q, sort_keys=True).encode()).hexdigest()


def packets(merge_result, root=check_citations.ROOT):
    reader = check_citations.SourceReader(merge_result["sources"], root)
    out = []
    for g in merge_result["contested"]:
        ev = []
        for i in g["instances"]:
            f = i["fact"]
            e = {"origin": i["origin"], "path": i["path"], "value": f.get("value")}
            if "sourceFile" in f:
                lines, err = reader.lines(f["repo"], f["sourceFile"])
                lo, hi = max(1, f["line"] - CONTEXT), f["line"] + CONTEXT
                e.update(repo=f["repo"], sourceFile=f["sourceFile"], line=f["line"], quotedToken=f["quotedToken"],
                         commit=merge_result["sources"][f["repo"]]["commit"],
                         context=[] if err else [{"n": n, "text": lines[n - 1]} for n in range(lo, min(hi, len(lines)) + 1)])
            else:
                e.update(basis="documented-default", sourceUrl=f.get("sourceUrl"))
            if f.get("note"):
                e["note"] = f["note"]
            ev.append(e)
        p = {"id": g["id"], "system": merge_result["system"], "subject": g["key"][0], "relation": g["relation"],
             "object": g["key"][2], "reportedBy": g["origins"], "instruction": INSTRUCTION, "evidence": ev}
        p["packetDigest"] = packet_digest(p)
        out.append(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("merge")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args(argv)
    if Path(a.out).exists():
        sys.exit("refusing to overwrite %s" % a.out)
    ps = packets(json.loads(Path(a.merge).read_text()))
    Path(a.out).write_text("".join(json.dumps(p, sort_keys=True) + "\n" for p in ps))
    print("%d packets -> %s" % (len(ps), a.out))


if __name__ == "__main__":
    main()
