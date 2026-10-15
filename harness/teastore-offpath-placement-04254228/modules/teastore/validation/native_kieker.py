#!/usr/bin/env python3
"""Validate the minimum native-Kieker evidence contract."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def validate(events: object) -> dict:
    blockers: list[str] = []
    if not isinstance(events, list) or not events:
        return {"verdict": "blocked", "blockers": ["no trace events"], "counts": {"events": 0}}
    sources = Counter(str(e.get("source")) for e in events if isinstance(e, dict))
    services = Counter(str(e.get("service")) for e in events if isinstance(e, dict))
    required = ("trace_id", "eoi", "ess", "message_sha1", "signature_sha1")
    missing = Counter()
    synthetic = 0
    for event in events:
        if not isinstance(event, dict):
            blockers.append("non-object trace event")
            continue
        for key in required:
            if event.get(key) in (None, ""):
                missing[key] += 1
        if str(event.get("trace_id", "")).startswith("scraped_"):
            synthetic += 1
    if set(sources) != {"kieker_native"}:
        blockers.append(f"unexpected sources: {dict(sources)}")
    if synthetic:
        blockers.append(f"{synthetic} scraper-generated trace IDs")
    if missing:
        blockers.append(f"missing required native fields: {dict(missing)}")
    if len([s for s in services if s and s != "unknown"]) < 2:
        blockers.append(f"insufficient service coverage: {dict(services)}")
    return {
        "verdict": "pass" if not blockers else "blocked",
        "blockers": blockers,
        "counts": {"events": len(events), "sources": dict(sources), "services": dict(services)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("traces", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate(json.loads(args.traces.read_text()))
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0 if report["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
