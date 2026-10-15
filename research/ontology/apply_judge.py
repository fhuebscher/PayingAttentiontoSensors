"""Stage 4 output: apply the judge's answers, log every decision, write the final spec (agreed + supported).

Usage:  uv run python research/ontology/apply_judge.py MERGE.json PACKETS.jsonl ANSWERS.jsonl --judge MODEL
                                                        --run-id ID -o FINAL_SPEC.json [--log ADJUDICATION_LOG.md]

ANSWERS.jsonl: one object per line, {"id", "packetDigest", "verdict", "reason"}; verdict is one of `supported`,
`not supported`, `not decidable` (an optional tail " from these lines" is accepted). Refusals (nothing is written):
an answer for an id that has no packet, a packetDigest that does not match the packet (the judge saw other
evidence), a duplicate id, an unknown verdict, an empty reason, or a packet file that does not match the merge.
A contested fact with no answer is not accepted and is logged as `no answer`. Deterministic facts (merge.py step 4a,
Amendment 2) are accepted without the judge and have no packet.
Every decision is appended to ADJUDICATION_LOG.md (append-only: the file is only ever opened in append mode, and a
run whose id already appears in it is refused). The final spec is rebuilt by merge.rebuild() from the agreed keys plus
the `supported` ones, validated against the JSON schema, and written to a new path only.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import judge_inputs  # noqa: E402
import merge as merge_mod  # noqa: E402

LOG = HERE / "ADJUDICATION_LOG.md"
LOG_HEADER = ("# Adjudication log (append-only)\n\nWritten only by research/ontology/apply_judge.py, one section per "
              "run, never edited. Protocol: EXTRACTION_PROTOCOL.md, Stage 4.\n")


def _sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def norm_verdict(v):
    s = re.sub(r"[\s_-]+", " ", str(v).strip().lower())
    s = re.sub(r" from these lines\.?$", "", s).rstrip(".")
    return s if s in judge_inputs.VERDICTS else None


def read_jsonl(p):
    return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]


def decide(merge_result, packets, answers):
    """-> (accepted ids, decisions list). Raises SystemExit on any refusal."""
    pk = {p["id"]: p for p in packets}
    contested = {g["id"] for g in merge_result["contested"]}
    if set(pk) != contested:
        raise SystemExit("packets do not match the merge's contested facts (%d packets, %d contested)" %
                         (len(pk), len(contested)))
    for p in packets:
        if judge_inputs.packet_digest(p) != p["packetDigest"]:
            raise SystemExit("packet %s was edited after it was written (digest mismatch)" % p["id"])
    seen, dec = set(), {}
    for a in answers:
        i = a.get("id")
        if i not in pk:
            raise SystemExit("answer for unknown id %r" % i)
        if i in seen:
            raise SystemExit("duplicate answer for %s" % i)
        seen.add(i)
        if a.get("packetDigest") != pk[i]["packetDigest"]:
            raise SystemExit("answer %s names packetDigest %r, packet has %s" % (i, a.get("packetDigest"),
                                                                                  pk[i]["packetDigest"]))
        v = norm_verdict(a.get("verdict"))
        if v is None:
            raise SystemExit("answer %s: unknown verdict %r" % (i, a.get("verdict")))
        if not str(a.get("reason", "")).strip():
            raise SystemExit("answer %s: empty reason" % i)
        dec[i] = {"id": i, "verdict": v, "reason": " ".join(str(a["reason"]).split())}
    decisions = []
    for i in sorted(pk):
        p = pk[i]
        d = dec.get(i, {"id": i, "verdict": "no answer", "reason": "-"})
        d.update(subject=p["subject"], relation=p["relation"], object=p["object"], reportedBy=p["reportedBy"])
        decisions.append(d)
    accepted = ({g["id"] for g in merge_result["agreed"]} | {g["id"] for g in merge_result.get("deterministic", [])} |
                {d["id"] for d in decisions if d["verdict"] == "supported"})
    return accepted, decisions


def _cell(x):
    s = x if isinstance(x, str) else json.dumps(x)
    return s.replace("|", "\\|").replace("\n", " ")


def append_log(log_path, run_id, system, judge, hashes, decisions):
    p = Path(log_path)
    if p.exists() and ("\n## run %s / %s\n" % (run_id, system)) in p.read_text():
        raise SystemExit("run %s / %s already in %s (append-only; a re-run needs a new run id)" % (run_id, system, p))
    counts = {}
    for d in decisions:
        counts[d["verdict"]] = counts.get(d["verdict"], 0) + 1
    lines = []
    if not p.exists():
        lines.append(LOG_HEADER)
    lines.append("\n## run %s / %s\n" % (run_id, system))
    lines.append("\n- appended %s by apply_judge.py; judge: %s" % (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                                    judge))
    for k, v in hashes.items():
        lines.append("\n- %s sha256 %s" % (k, v))
    lines.append("\n- decisions: %s\n" % json.dumps(counts, sort_keys=True))
    lines.append("\n| id | subject | relation | object | reported by | verdict | reason |\n|---|---|---|---|---|---|---|\n")
    for d in decisions:
        lines.append("| %s | %s | %s | %s | %s | %s | %s |\n" % (
            d["id"], _cell(d["subject"]), d["relation"], _cell(d["object"]), ",".join(d["reportedBy"]),
            d["verdict"], _cell(d["reason"])))
    with open(p, "a") as fh:  # append-only by construction
        fh.write("".join(lines))


def apply(merge_path, packets_path, answers_path, judge, run_id, out, log_path=LOG):
    mr = json.loads(Path(merge_path).read_text())
    packets, answers = read_jsonl(packets_path), read_jsonl(answers_path)
    if Path(out).exists():
        raise SystemExit("refusing to overwrite %s" % out)
    accepted, decisions = decide(mr, packets, answers)
    spec, rlog = merge_mod.rebuild(mr, accepted, extraction={
        "stage": "final", "procedure": "research/ontology/EXTRACTION_PROTOCOL.md", "runId": run_id, "judge": judge,
        "accepted": {"agreed": len(mr["agreed"]), "deterministic": len(mr.get("deterministic", [])),
                     "supported": sum(d["verdict"] == "supported" for d in decisions)},
        "rebuildLog": None})
    spec["extraction"]["rebuildLog"] = rlog
    errs = merge_mod.validate(spec)
    hashes = {"merge": _sha(Path(merge_path).read_bytes()), "packets": _sha(Path(packets_path).read_bytes()),
              "answers": _sha(Path(answers_path).read_bytes())}
    append_log(log_path, run_id, mr["system"], judge, hashes, decisions)
    Path(out).write_text(json.dumps(spec, indent=1) + "\n")
    return spec, decisions, errs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("merge")
    ap.add_argument("packets")
    ap.add_argument("answers")
    ap.add_argument("--judge", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--log", default=str(LOG))
    a = ap.parse_args(argv)
    spec, decisions, errs = apply(a.merge, a.packets, a.answers, a.judge, a.run_id, a.out, a.log)
    counts = {}
    for d in decisions:
        counts[d["verdict"]] = counts.get(d["verdict"], 0) + 1
    print(json.dumps({"decisions": counts, "schemaErrors": errs}, indent=1))
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
