#!/usr/bin/env python3
"""Validate and schedule Hotel Reservation campaigns before any executor runs."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "modules" / "hotel-reservation"
POSTURES = ("none", "sample-zero", "full")
FAULTS = ("search-pause", "reservation-pause")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class CampaignParameters:
    blocks: int = 3
    seed: int = 20260808
    warmup_seconds: float = 30.0
    measurement_seconds: float = 120.0
    requests_per_second: float = 10.0
    concurrency: int = 16
    postures: tuple[str, ...] = POSTURES
    scenario: str = "hotel-search"
    fault: str = "search-pause"
    fault_at_seconds: float = 45.0
    outage_seconds: float = 15.0
    base_url: str = "http://localhost:5000"

    def validate(self) -> None:
        if not isinstance(self.blocks, int) or isinstance(self.blocks, bool) or not 1 <= self.blocks <= 100:
            raise ValueError("blocks must be an integer from 1 through 100")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        finite = (self.warmup_seconds, self.measurement_seconds, self.requests_per_second,
                  self.fault_at_seconds, self.outage_seconds)
        if any(not math.isfinite(value) for value in finite):
            raise ValueError("all numeric campaign parameters must be finite")
        if (self.warmup_seconds < 0 or not 0 < self.measurement_seconds <= 86400 or
                not 0 < self.requests_per_second <= 10000):
            raise ValueError("warmup must be non-negative; duration and rate must be positive")
        if self.requests_per_second * self.measurement_seconds > 1_000_000:
            raise ValueError("one run may not offer more than 1,000,000 requests")
        if not isinstance(self.concurrency, int) or isinstance(self.concurrency, bool) or not 1 <= self.concurrency <= 1024:
            raise ValueError("concurrency must be an integer from 1 through 1024")
        if self.postures != POSTURES:
            raise ValueError(f"paired stock campaign postures must be exactly {POSTURES}")
        if self.scenario != "hotel-search":
            raise ValueError("only the source-audited hotel-search scenario is qualified")
        if self.fault not in FAULTS:
            raise ValueError(f"fault must be one of {FAULTS}")
        if self.fault_at_seconds < 0 or self.outage_seconds <= 0:
            raise ValueError("fault-at must be non-negative and outage positive")
        if self.fault_at_seconds + self.outage_seconds >= self.measurement_seconds:
            raise ValueError("fault and recovery must fit strictly inside the measurement window")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base-url must be HTTP(S)")


def configuration(parameters: CampaignParameters, source_proof: dict,
                  framework_commit: str) -> dict:
    parameters.validate()
    required_source = {"upstreamCommit", "upstreamTree", "materializedSourceSha256",
                       "sourceCheckoutClean"}
    missing = sorted(required_source - set(source_proof))
    if missing or source_proof.get("sourceCheckoutClean") is not True:
        raise ValueError(f"incomplete or unclean source proof: missing {missing}")
    if not framework_commit:
        raise ValueError("framework commit is required")
    return {
        "schemaVersion": 1, "sut": "hotel-reservation",
        "evidenceLabelCeiling": "smoke-validation",
        "claimBoundary": "none disables the tracer (NoopTracer) and sample-zero suppresses sampling; neither is source-off -- the middleware and interceptors are installed in all three postures",
        "parameters": {**asdict(parameters), "postures": list(parameters.postures)},
        "provenance": {"frameworkCommit": framework_commit, **source_proof},
        "configurationHashes": {
            "activationCatalogSha256": sha256(MODULE / "activation/catalog.json"),
            "goalSha256": sha256(MODULE / "goals/search-path.json"),
            "composeOverlaySha256": sha256(MODULE / "deployment/compose.observability-placement.yml"),
            "runnerSha256": sha256(Path(__file__)),
        },
    }


def schedule(parameters: CampaignParameters) -> list[dict]:
    parameters.validate()
    rng = random.Random(parameters.seed)
    rows = []
    for block in range(1, parameters.blocks + 1):
        order = list(parameters.postures)
        rng.shuffle(order)
        rows.extend({"block": block, "posture": posture,
                     "runId": f"b{block:02d}-{posture}"} for posture in order)
    return rows


def write_schedule(path: Path, config: dict, rows: list[dict]) -> dict:
    # Use the repository-wide campaign shape so the generic evidence validator,
    # MLflow importer, and module-specific executor agree on run identity.
    payload = {"configuration": config, "runs": rows}
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text() != encoded:
            raise RuntimeError(f"refusing to change existing schedule: {path}")
    else:
        path.write_text(encoded)
    return payload


class State(str, Enum):
    UNKNOWN = "unknown"
    INVENTORIED = "inventoried"
    QUARANTINED = "quarantined"
    PRE_RUN_STOPPED = "pre-run-stopped"
    MATERIALIZED = "materialized"
    DEPLOYED = "deployed"
    READY = "ready"
    POSTURE_PROVEN = "posture-proven"
    RUNNING = "running"
    COLLECTED = "collected"
    POST_RUN_STOPPED = "post-run-stopped"
    FETCHED = "fetched"
    VALIDATED = "validated"
    FAILED = "failed"


NEXT = {
    State.UNKNOWN: State.INVENTORIED,
    State.INVENTORIED: State.QUARANTINED,
    State.QUARANTINED: State.PRE_RUN_STOPPED,
    State.PRE_RUN_STOPPED: State.MATERIALIZED,
    State.MATERIALIZED: State.DEPLOYED,
    State.DEPLOYED: State.READY,
    State.READY: State.POSTURE_PROVEN,
    State.POSTURE_PROVEN: State.RUNNING,
    State.RUNNING: State.COLLECTED,
    State.COLLECTED: State.POST_RUN_STOPPED,
    State.POST_RUN_STOPPED: State.FETCHED,
    State.FETCHED: State.VALIDATED,
}


@dataclass
class Lifecycle:
    state: State = State.UNKNOWN

    def advance(self, target: State, receipt: dict) -> State:
        if receipt.get("successful") is not True:
            self.state = State.FAILED
            raise RuntimeError(f"failed lifecycle receipt for {target.value}")
        expected = NEXT.get(self.state)
        if target != expected:
            raise RuntimeError(f"invalid lifecycle transition {self.state.value} -> {target.value}; expected {expected}")
        self.state = target
        return self.state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-proof", required=True, type=Path)
    parser.add_argument("--framework-commit", required=True)
    parser.add_argument("--blocks", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260808)
    parser.add_argument("--warmup", type=float, default=30)
    parser.add_argument("--duration", type=float, default=120)
    parser.add_argument("--rate", type=float, default=10)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--fault", default="search-pause")
    parser.add_argument("--fault-at", type=float, default=45)
    parser.add_argument("--outage", type=float, default=15)
    parser.add_argument("--base-url", default="http://localhost:5000")
    args = parser.parse_args()
    parameters = CampaignParameters(
        blocks=args.blocks, seed=args.seed, warmup_seconds=args.warmup,
        measurement_seconds=args.duration, requests_per_second=args.rate,
        concurrency=args.concurrency, fault=args.fault,
        fault_at_seconds=args.fault_at, outage_seconds=args.outage,
        base_url=args.base_url,
    )
    try:
        payload = write_schedule(args.output,
                                 configuration(parameters, json.loads(args.source_proof.read_text()),
                                               args.framework_commit),
                                 schedule(parameters))
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"runs": len(payload["runs"]),
                      "evidenceLabelCeiling": payload["configuration"]["evidenceLabelCeiling"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
