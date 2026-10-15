#!/usr/bin/env python3
"""Compile the OpenTelemetry Demo candidate-pilot design, one study epoch at a time.

This module is construction-only. It can validate and materialize a frozen
18-cell schedule, but it has no Docker, SSH, subprocess, socket, executor, or
transport surface. Producing a schedule cannot realize a posture: the epoch
table below says what each frozen descriptor may claim, and a descriptor that
claims more than its epoch's contract fails closed.

Three study epochs are known. ``otel-demo-candidate-pilot-v1`` is the superseded,
byte-frozen design whose ``none``/``selected`` postures are ``unsupported`` under
the pre-D13 "no instrumentation loaded" reading; it is still compiled so its
18-cell UNSUPPORTED ledger replays bit-exactly. ``otel-demo-candidate-pilot-v2``
is the three-posture D13 design (``none`` means **no telemetry emitted**, the
four loaded-but-silenced services are a named claim boundary) that runs 1-3
executed; it is still compiled so its admission plan and run-3 plan replay.
``otel-demo-candidate-pilot-v3`` is the current design (main repo
``research/otel-postures/DECLARATION.md``, 6221145): four nested postures
``none`` < ``selected`` < ``async`` < ``full`` under the same D13 reading,
2 regimes x 3 blocks x 4 postures = 24 cells. Geometry (postures, codes, run
counts) is therefore per epoch, never global. Every descriptor is byte-identical
to its pinned digest; v1's and v2's bytes did not move when v3 was introduced.

Schedule: each block is one cyclic rotation of a base permutation, so a block
contains every posture once and no posture repeats an ordinal position within a
regime. With 3 postures and 3 blocks that is a Latin square; with v3's 4
postures and 3 blocks it is a 3x4 Latin RECTANGLE (each posture occupies 3 of
the 4 positions once each; one position per posture is unobserved per regime).
A full 4x4 square needs 4 blocks, which the declaration does not grant.

``otel-demo-offpath-v1`` (main repo ``research/otel-offpath/DECLARATION.md``,
8194d74; direction (c)) is the current design: the same four posture NAMES with
new closures (``selected`` = the synchronous checkout path, ``async`` = selected
+ kafka, frauddetectionservice, accountingservice), a checkout-journey workload,
and three regimes (no-fault, fraud-pause, frontend-pause) x 3 blocks x 4
postures = 36 cells, each regime a 3x4 Latin rectangle. Regimes are therefore
per epoch too; v1-v3 keep their two regimes and replay unchanged.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping, NoReturn


ROOT = Path(__file__).resolve().parents[3]
# The current study epoch this compiler serves by default, and the superseded
# one it still compiles for ledger replay. Admitting an epoch on the target is
# a separate governed edit (candidate_setup/candidate_remote
# ``ADMITTED_STUDY_EPOCHS``); nothing here grants runtime.
EPOCH = "otel-demo-offpath-v1"
FROZEN_EPOCH = "otel-demo-candidate-pilot-v1"
# v3's predecessor (derive_v3_descriptor's source); kept under its old name.
PREVIOUS_EPOCH = "otel-demo-candidate-pilot-v2"
V3_EPOCH = "otel-demo-candidate-pilot-v3"
# The offpath epoch's predecessor: its descriptor is derived from v3's bytes.
OFFPATH_PREDECESSOR_EPOCH = V3_EPOCH
MODULE = "otel-demo"
SUT_COMMIT = "2d4661e4897aa7b2d2ddbb5ef8c4824ca8a1b88d"
APPLICATION_FAMILY = "otel-demo"
CHANNEL = "compose-otel-collector"
# Per-epoch posture vocabularies. The code letters are the schedule's base-row
# alphabet; base rows are every permutation of the codes in posture order
# (itertools order), which for three postures is exactly the six rows v1 and v2
# were compiled from, so both replay unchanged.
THREE_POSTURES = ("none", "selected", "full")
THREE_POSTURE_CODES = {"N": "none", "S": "selected", "F": "full"}
FOUR_POSTURES = ("none", "selected", "async", "full")
FOUR_POSTURE_CODES = {"N": "none", "S": "selected", "A": "async", "F": "full"}
POSTURES = FOUR_POSTURES
POSTURE_CODES = FOUR_POSTURE_CODES
# Offpath fault scenarios the harness knows. ``action`` is what the target
# controller does to ``service`` for ``holdSeconds``; ``implemented`` False means
# the scenario is named (erratum 2, a candidate redesign) but selecting it fails
# closed at compile time until its controller exists. Adding a scenario here and
# naming it in OFFPATH_FAULT_DESIGN is how a fourth regime is added.
OFFPATH_FAULT_SCENARIOS: dict[str, dict[str, Any]] = {
    "fraud-pause": {
        "service": "frauddetectionservice", "action": "pause",
        "entryRouteDuringFault": "recorded-not-required", "implemented": True,
    },
    "frontend-pause": {
        "service": "frontend", "action": "pause",
        "entryRouteDuringFault": "must-be-unavailable", "implemented": True,
    },
    "email-stop": {
        "service": "emailservice", "action": "stop",
        "entryRouteDuringFault": "recorded-not-required", "implemented": True,
    },
    "kafka-queue-problems": {
        "service": "checkoutservice", "action": "feature-flag",
        "flag": "kafkaQueueProblems",
        "entryRouteDuringFault": "recorded-not-required", "implemented": False,
        "notImplementedBecause": (
            "flipping a flagd flag needs a writable flag-file overlay; the installed source tree "
            "is immutable and no controller writes it"
        ),
    },
}
# The declared design (DECLARATION.md 8194d74 and erratum 2: hold, scenario and
# export interval are parameters; these are the declared defaults until the
# user chooses a redesign). Regimes, timing and fault truth are derived from it.
OFFPATH_FAULT_DESIGN: dict[str, Any] = {
    "targetScenarios": ["fraud-pause"],
    "controlScenarios": ["frontend-pause"],
    "onsetSeconds": 45,
    "holdSeconds": 15,
    # None = upstream: the harness sets no OTEL_METRIC_EXPORT_INTERVAL, so every
    # SDK keeps its own default (60 s). A number is refused until the posture
    # overlay forwards it (a harness emission change for the user to approve).
    "metricExportIntervalMilliseconds": None,
}
OFFPATH_DECLARED_RUNS = 36


def offpath_regimes(design: Mapping[str, Any] = OFFPATH_FAULT_DESIGN) -> tuple[str, ...]:
    scenarios = list(design["targetScenarios"]) + list(design["controlScenarios"])
    return ("no-fault-cost",) + tuple(f"{scenario}-effect" for scenario in scenarios)


# Per-epoch regime sets, in execution order (the no-fault regime first, so the
# offpath workload-path check runs before any fault cell).
TWO_REGIMES = ("no-fault-cost", "frontend-pause-effect")
OFFPATH_REGIMES = offpath_regimes()
REGIMES = OFFPATH_REGIMES
REGIME_CONTRACTS = {
    "no-fault-cost": {
        "kind": "cost",
        "fault": None,
        "artifactRootClass": "cost",
    },
    "frontend-pause-effect": {
        "kind": "effect",
        "fault": "frontend-pause",
        "artifactRootClass": "effect/frontend-pause",
    },
}
for _scenario in OFFPATH_FAULT_SCENARIOS:
    REGIME_CONTRACTS.setdefault(
        f"{_scenario}-effect",
        {"kind": "effect", "fault": _scenario, "artifactRootClass": f"effect/{_scenario}"},
    )
BLOCKS_PER_REGIME = 3
RUNS_PER_BLOCK = len(POSTURES)
TOTAL_RUNS = len(REGIMES) * BLOCKS_PER_REGIME * RUNS_PER_BLOCK
if TOTAL_RUNS != OFFPATH_DECLARED_RUNS:  # a geometry edit must fail here first
    raise RuntimeError(f"offpath geometry differs from the declared {OFFPATH_DECLARED_RUNS} cells: {TOTAL_RUNS}")
# The attempt number is part of every runKey, so it is part of every runId and of
# the compiled-plan digest (never of the descriptor digest). Attempt 1 is the
# admission attempt: governance pins its plan digest, and it is SPENT -- the
# 2026-09-18 shakedown (OTEL_RUN1_SHAKEDOWN_DECLARATION.md) ran under it and its
# cells are unpromotable. A new attempt is chosen by the launcher through
# ATTEMPT_ENVIRONMENT, never by editing this file, so run 3 is attempt 3 with
# no code change. The driver path (candidate_runtime_adapter.inspect_campaign)
# refuses a spent attempt; the pure compiler does not, so the admission plan
# stays replayable.
DEFAULT_ATTEMPT = 1
ATTEMPT_ENVIRONMENT = "OTEL_CANDIDATE_ATTEMPT"
SCHEDULE_CONTEXT = "schedule-v1"
DESIGN_LABEL = "method-design-only"
MAXIMUM_EVIDENCE_LABEL = "candidate-evidence"
COMMON_ROOT_KEYS = frozenset(
    {
        "analysis", "design", "evidence", "groundTruth", "id", "missingness",
        "module", "outcomes", "postureRealization", "runIdentity", "schedule",
        "source", "status", "timing", "workflow",
    }
)
# D13 claim boundary: the identity fields the compiler checks structurally; the
# descriptor's prose around them is bound by the canonical digest.
D13_CLAIM_BOUNDARY_LABEL = "loaded-but-silenced-instrumentation-still-runs-and-still-costs"
D13_NONE_SEMANTICS = "no-telemetry-emitted"
D13_LOADED_BUT_SILENCED_SERVICES = ("emailservice", "flagd", "flagd-ui", "loadgenerator")
POSTURE_PROBE_TOOL = "modules/otel-demo/tools/posture_connection_probe.sh"
SETUP_PRECONDITION_IDS = (
    "posture-connection-probe-ok",
    "demo-stack-torn-down",
    "reserved-ports-free-and-lease-absent",
)
SRV6_TARGET = {
    "host": "fb14srv6",
    "transportUser": "root",
    "setupUser": "root",
    "executionUser": "stig",
    "executionUid": 1016,
    "executionGid": 1016,
    "dockerGid": 998,
    "allocationPath": "modules/otel-demo/execution/candidate-target-allocation.json",
    "leaseScope": "shared-srv6-host-exclusive-otel-then-online-boutique",
}
# Per-epoch contract: what a descriptor with this ``id`` must say, and the
# canonical digest its whole body must hash to. A descriptor whose id is not
# here is not a study epoch of this module.
EPOCHS: dict[str, dict[str, Any]] = {
    "otel-demo-candidate-pilot-v1": {
        "descriptor": ROOT / "pipelines/campaigns/otel-demo-candidate-pilot-v1.json",
        "expectedDescriptorSha256": (
            "daffe1cafc502bc0ff79da25d8233cd69c5882091628c2d83fb82e851be5307e"
        ),
        "rootKeys": COMMON_ROOT_KEYS,
        "postures": THREE_POSTURES,
        "postureCodes": THREE_POSTURE_CODES,
        "regimes": TWO_REGIMES,
        "postureRealization": {
            "none": "unsupported", "selected": "unsupported", "full": "implemented",
        },
        "noneControl": "legacy-source-off",
        "claimBoundaryRequired": False,
        "supersedes": None,
        "target": None,
        "setupPreconditionIds": None,
    },
    "otel-demo-candidate-pilot-v2": {
        "descriptor": ROOT / "pipelines/campaigns/otel-demo-candidate-pilot-v2.json",
        "expectedDescriptorSha256": (
            "c86874e0001544ae3c8289ba76cd54d3432112fcea2b01368775e27d9cc002b2"
        ),
        "rootKeys": COMMON_ROOT_KEYS | {"setupPreconditions", "supersedes", "target"},
        "postures": THREE_POSTURES,
        "postureCodes": THREE_POSTURE_CODES,
        "regimes": TWO_REGIMES,
        "postureRealization": {
            "none": "implemented", "selected": "implemented", "full": "implemented",
        },
        "noneControl": "materialized-posture-controls",
        "claimBoundaryRequired": True,
        "supersedes": {
            "studyEpoch": "otel-demo-candidate-pilot-v1",
            "descriptorPath": "pipelines/campaigns/otel-demo-candidate-pilot-v1.json",
            "descriptorByteSha256": (
                "fb43212b38ce0cd53538ee654b825574ee415dc4624fc2cc32bcc6d82504cbaa"
            ),
            "descriptorCanonicalSha256": (
                "daffe1cafc502bc0ff79da25d8233cd69c5882091628c2d83fb82e851be5307e"
            ),
            "unsupportedLedgerPath": "modules/otel-demo/execution/candidate-unsupported.json",
        },
        "target": SRV6_TARGET,
        "setupPreconditionIds": SETUP_PRECONDITION_IDS,
    },
    # The four-posture successor (main repo research/otel-postures/DECLARATION.md,
    # 6221145). Its descriptor is GENERATED by ``derive_v3_descriptor`` from the
    # byte-pinned v2 descriptor, never hand-edited; a test compares the file's
    # bytes with the derivation.
    "otel-demo-candidate-pilot-v3": {
        "descriptor": ROOT / "pipelines/campaigns/otel-demo-candidate-pilot-v3.json",
        "expectedDescriptorSha256": (
            "1231208d0ce21230804aea042569b7b8078e237be20a46f16fa763e10d3d7a28"
        ),
        "rootKeys": COMMON_ROOT_KEYS | {"setupPreconditions", "supersedes", "target"},
        "postures": FOUR_POSTURES,
        "postureCodes": FOUR_POSTURE_CODES,
        "regimes": TWO_REGIMES,
        "postureRealization": {
            "none": "implemented", "selected": "implemented",
            "async": "implemented", "full": "implemented",
        },
        "noneControl": "materialized-posture-controls",
        "claimBoundaryRequired": True,
        "supersedes": {
            "studyEpoch": "otel-demo-candidate-pilot-v2",
            "descriptorPath": "pipelines/campaigns/otel-demo-candidate-pilot-v2.json",
            "descriptorByteSha256": (
                "2fd3ee5501c3f65f3059b4adc55a650ee15643d9b6466f32d97ea9466df41299"
            ),
            "descriptorCanonicalSha256": (
                "c86874e0001544ae3c8289ba76cd54d3432112fcea2b01368775e27d9cc002b2"
            ),
        },
        "target": SRV6_TARGET,
        "setupPreconditionIds": SETUP_PRECONDITION_IDS,
    },
    # Direction (c) (main repo research/otel-offpath/DECLARATION.md, 8194d74).
    # GENERATED by ``derive_offpath_descriptor`` from the byte-pinned v3
    # descriptor, never hand-edited; a test compares the file's bytes.
    "otel-demo-offpath-v1": {
        "descriptor": ROOT / "pipelines/campaigns/otel-demo-offpath-v1.json",
        "expectedDescriptorSha256": (
            "1491657d8d3c2a3271aa37e837f28f73c4c4bad297e37cb899a28d9efd2742f6"
        ),
        "rootKeys": COMMON_ROOT_KEYS | {"faultDesign", "setupPreconditions", "supersedes", "target", "workload"},
        "postures": FOUR_POSTURES,
        "postureCodes": FOUR_POSTURE_CODES,
        "regimes": OFFPATH_REGIMES,
        "claimBoundarySilenced": {
            "none": ["emailservice", "flagd", "flagd-ui", "loadgenerator"],
            "selected": ["flagd-ui", "loadgenerator"],
            "async": ["flagd-ui", "loadgenerator"],
        },
        "postureRealization": {
            "none": "implemented", "selected": "implemented",
            "async": "implemented", "full": "implemented",
        },
        "noneControl": "materialized-posture-controls",
        "claimBoundaryRequired": True,
        "supersedes": {
            "studyEpoch": "otel-demo-candidate-pilot-v3",
            "descriptorPath": "pipelines/campaigns/otel-demo-candidate-pilot-v3.json",
            "descriptorByteSha256": (
                "f37fb9873f4dfdaf48951cda6fb27b91b1bab77967091e68d88190b8133bfd2e"
            ),
            "descriptorCanonicalSha256": (
                "1231208d0ce21230804aea042569b7b8078e237be20a46f16fa763e10d3d7a28"
            ),
        },
        "target": SRV6_TARGET,
        "setupPreconditionIds": SETUP_PRECONDITION_IDS,
    },
}


def epoch_postures(epoch: str) -> tuple[str, ...]:
    """The posture vocabulary of one study epoch, in design order."""
    if epoch not in EPOCHS:
        raise ProtocolError("unknown study epoch")
    return tuple(EPOCHS[epoch]["postures"])


def epoch_regimes(epoch: str) -> tuple[str, ...]:
    """The regime set of one study epoch, in execution order."""
    if epoch not in EPOCHS:
        raise ProtocolError("unknown study epoch")
    return tuple(EPOCHS[epoch]["regimes"])


def epoch_total_runs(epoch: str) -> int:
    return len(epoch_regimes(epoch)) * BLOCKS_PER_REGIME * len(epoch_postures(epoch))


DEFAULT_DESCRIPTOR = EPOCHS[EPOCH]["descriptor"]
EXPECTED_DESCRIPTOR_SHA256 = EPOCHS[EPOCH]["expectedDescriptorSha256"]
DESCRIPTOR_COPY = "campaign-descriptor.json"
PLAN_COPY = "compiled-plan.json"
RECEIPT_COPY = "construction-receipt.json"


class ProtocolError(ValueError):
    """The descriptor, plan, or retained construction bytes differ."""


def _reject_constant(value: str) -> NoReturn:
    raise ProtocolError(f"non-finite JSON value is forbidden: {value}")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_loads(value: str) -> Any:
    try:
        return json.loads(
            value,
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except ProtocolError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ProtocolError(f"invalid JSON: {exc}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"value is not canonical JSON: {exc}") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _pretty_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"value is not serializable JSON: {exc}") from exc


def _exact_keys(value: Any, expected: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        observed = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise ProtocolError(
            f"{where} keys differ: expected {sorted(expected)}, observed {observed}"
        )
    return value


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> dict[str, Any]:
    try:
        payload = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProtocolError(f"cannot read candidate descriptor: {exc}") from exc
    document = strict_json_loads(payload)
    validate_descriptor(document)
    return copy.deepcopy(document)


def epoch_contract(document: Any) -> dict[str, Any]:
    """The frozen contract for ``document``'s study epoch, or a ProtocolError."""
    if not isinstance(document, dict) or document.get("id") not in EPOCHS:
        raise ProtocolError("candidate descriptor identity or run geometry differs")
    return EPOCHS[document["id"]]


def validate_descriptor(document: Any) -> None:
    contract = epoch_contract(document)
    root = _exact_keys(document, set(contract["rootKeys"]), "candidate descriptor")
    postures = tuple(contract["postures"])
    if (
        root["module"] != MODULE
        or root["status"] != DESIGN_LABEL
        or root["source"].get("sutCommit") != SUT_COMMIT
        or root["source"].get("applicationFamily") != APPLICATION_FAMILY
        or root["source"].get("channel") != CHANNEL
        or root["design"].get("postures") != list(postures)
        or root["design"].get("blocksPerRegime") != BLOCKS_PER_REGIME
        or root["design"].get("runsPerBlock") != len(postures)
        or root["design"].get("totalRuns") != epoch_total_runs(root["id"])
        or root["schedule"].get("postureCodes") != contract["postureCodes"]
    ):
        raise ProtocolError("candidate descriptor identity or run geometry differs")
    regimes = root["design"].get("regimes")
    expected_regimes = [
        {"id": name, **REGIME_CONTRACTS[name]} for name in contract["regimes"]
    ]
    if regimes != expected_regimes:
        raise ProtocolError("cost/effect regime separation differs")
    realizations = root["postureRealization"]
    expected_statuses = contract["postureRealization"]
    if (
        set(realizations) != set(postures)
        or any(
            not isinstance(realizations[posture], dict)
            or realizations[posture].get("status") != expected_statuses[posture]
            for posture in postures
        )
        or realizations["none"].get("currentControl") != contract["noneControl"]
    ):
        raise ProtocolError("posture realization boundary differs")
    if contract["claimBoundaryRequired"]:
        # D13: every posture below full is implemented under the
        # no-telemetry-emitted reading and must name the loaded-but-silenced
        # services as its claim boundary; full has none.
        # The silenced set is the D13 four minus the posture's closure: the
        # offpath closures activate emailservice and flagd from selected up.
        silenced_by_posture = contract.get("claimBoundarySilenced") or {}
        for posture in postures[:-1]:
            boundary = realizations[posture].get("claimBoundary")
            expected_silenced = list(
                silenced_by_posture.get(posture, D13_LOADED_BUT_SILENCED_SERVICES)
            )
            if (
                not isinstance(boundary, dict)
                or boundary.get("label") != D13_CLAIM_BOUNDARY_LABEL
                or boundary.get("semantics") != D13_NONE_SEMANTICS
                or boundary.get("loadedButSilencedServices") != expected_silenced
            ):
                raise ProtocolError("D13 claim boundary differs")
        if realizations["full"].get("claimBoundary") is not None:
            raise ProtocolError("D13 claim boundary differs")
    workflow = root["workflow"]
    if (
        workflow.get("candidateExecutionEnabled") is not False
        or workflow.get("externalMutationAllowed") is not False
        or workflow.get("runtimeAuthorized") is not False
        or not isinstance(workflow.get("constructionBlockers"), list)
        or not workflow["constructionBlockers"]
    ):
        raise ProtocolError("construction/runtime denial differs")
    if root["groundTruth"]["fault"].get("independentOfScoredTelemetry") is not True:
        raise ProtocolError("fault truth is not independent of scored telemetry")
    path = root["groundTruth"]["path"]
    if (
        path.get("executedDenominator") != "application-side-request-witness"
        or path.get("crossTraceAssemblyAllowed") is not False
        or path.get("numericMissingValue", "missing") is not None
        or set(path.get("faultSpecificTruth", {}))
        != {REGIME_CONTRACTS[name]["fault"] for name in contract["regimes"]} - {None}
    ):
        raise ProtocolError("path/opportunity ground-truth contract differs")
    outcomes = root["outcomes"]
    if (
        outcomes.get("costRegimeOnly") != "no-fault-cost"
        or outcomes.get("effectResourcesAreCostEstimates") is not False
        or outcomes.get("offeredRequestsAreDenominator") is not True
    ):
        raise ProtocolError("cost/effect outcome boundary differs")
    if contract["supersedes"] is not None:
        supersedes = root.get("supersedes")
        if not isinstance(supersedes, dict) or any(
            supersedes.get(key) != value for key, value in contract["supersedes"].items()
        ):
            raise ProtocolError("supersession record differs from the frozen predecessor identity")
    if contract["target"] is not None and root.get("target") != contract["target"]:
        raise ProtocolError("target identity differs from the reviewed srv6 allocation")
    if contract["setupPreconditionIds"] is not None:
        preconditions = root.get("setupPreconditions")
        if not isinstance(preconditions, list) or not all(
            isinstance(item, dict) for item in preconditions
        ):
            raise ProtocolError("GATE-SETUP preconditions differ")
        if (
            [item.get("id") for item in preconditions] != list(contract["setupPreconditionIds"])
            or preconditions[0].get("tool") != POSTURE_PROBE_TOOL
            or preconditions[0].get("requiredOutput") != "PROBE OK"
        ):
            raise ProtocolError("GATE-SETUP preconditions differ")
    if "faultDesign" in contract["rootKeys"]:
        design = root["faultDesign"]
        if not isinstance(design, dict) or set(design) != set(OFFPATH_FAULT_DESIGN) | {"scenarios", "authority"}:
            raise ProtocolError("offpath fault design keys differ")
        validate_fault_design({key: design[key] for key in OFFPATH_FAULT_DESIGN})
        named = list(design["targetScenarios"]) + list(design["controlScenarios"])
        if design["scenarios"] != {name: OFFPATH_FAULT_SCENARIOS[name] for name in named}:
            raise ProtocolError("offpath fault scenario table differs from the harness's")
        if offpath_regimes(design) != tuple(contract["regimes"]):
            raise ProtocolError("offpath regimes differ from the fault design")
        if (
            root["timing"].get("faultOnsetSeconds") != design["onsetSeconds"]
            or root["timing"].get("interventionHoldSeconds") != design["holdSeconds"]
        ):
            raise ProtocolError("offpath timing differs from the fault design")
    if canonical_sha256(root) != contract["expectedDescriptorSha256"]:
        raise ProtocolError("candidate descriptor differs from the frozen design")


V3_ASYNC_ADDED_SERVICES = (
    "accountingservice", "checkoutservice", "frauddetectionservice", "kafka",
)
V3_AUTHORITY = (
    "main repo research/otel-postures/DECLARATION.md at 6221145 (user 2026-09-30: "
    "new run, four postures, same regimes; fourth override of OTEL_RUN2_STOPPING_RULE.md)"
)


def derive_v3_descriptor(v2_path: Path | None = None) -> dict[str, Any]:
    """Generate the v3 descriptor from the byte-pinned v2 descriptor.

    This function IS the v3 descriptor's source: the checked-in
    ``otel-demo-candidate-pilot-v3.json`` must equal ``_pretty_bytes`` of its
    result (tested), so the file is regenerated, never hand-edited. Every v2
    field is carried over unchanged except the posture geometry, the async
    posture's realization, the supersession record and the id.
    """
    path = Path(v2_path) if v2_path is not None else EPOCHS[PREVIOUS_EPOCH]["descriptor"]
    v2 = load_descriptor(path)
    if v2["id"] != PREVIOUS_EPOCH:
        raise ProtocolError("v3 is derived from the v2 descriptor only")
    document = copy.deepcopy(v2)
    document["id"] = V3_EPOCH
    document["design"]["postures"] = list(FOUR_POSTURES)
    document["design"]["runsPerBlock"] = len(FOUR_POSTURES)
    document["design"]["totalRuns"] = epoch_total_runs(V3_EPOCH)
    document["schedule"]["postureCodes"] = dict(FOUR_POSTURE_CODES)
    document["schedule"]["positionBalance"] = (
        f"latin-rectangle: {BLOCKS_PER_REGIME} blocks x {len(FOUR_POSTURES)} postures per regime; "
        "each posture occupies 3 of the 4 ordinal positions once and none twice; a full 4x4 "
        "Latin square would need 4 blocks, which the declaration does not grant"
    )
    selected = v2["postureRealization"]["selected"]
    document["postureRealization"]["async"] = {
        "claimBoundary": copy.deepcopy(selected["claimBoundary"]),
        "closureDecision": (
            "instrumentation is activated on the selected closure plus "
            + ", ".join(V3_ASYNC_ADDED_SERVICES)
            + " (the order path and its Kafka consumers); every other application service still "
            "runs in async, uninstrumented, exactly as under none and selected. Running is not the "
            "posture; instrumentation activation is, so the order path's dependencies (cartservice, "
            "currencyservice, emailservice, paymentservice, productcatalogservice, quoteservice, "
            "shippingservice) run but are not instrumented"
        ),
        "currentControl": "materialized-posture-controls-async-closure",
        "reason": None,
        "status": "implemented",
        "workloadCaveat": (
            "the offered request is /api/recommendations (frontendproxy, frontend, "
            "recommendationservice); it does not traverse checkout or Kafka, so the four added "
            "services are exercised only by their own background work in every regime"
        ),
    }
    document["supersedes"] = {
        "authority": V3_AUTHORITY,
        "descriptorByteSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "descriptorCanonicalSha256": canonical_sha256(v2),
        "descriptorPath": str(path.resolve().relative_to(ROOT)),
        "studyEpoch": PREVIOUS_EPOCH,
        "v2Disposition": (
            "runs 1-3 executed under v2; run 3 (attempt 3) is terminal-valid 18/18 and stays thesis "
            "material, not pooled with v3; the v2 descriptor's bytes are unchanged"
        ),
        "whatChanged": [
            "a fourth posture async (selected plus accountingservice, checkoutservice, "
            "frauddetectionservice, kafka) nested between selected and full",
            "runsPerBlock 3 -> 4 and totalRuns 18 -> 24; regimes, blocks, timing, ground truth and "
            "outcomes unchanged",
            "the schedule is a 3x4 Latin rectangle by position, not a square",
        ],
    }
    return document


# --- otel-demo-offpath-v1 (direction (c)) -----------------------------------
# The synchronous checkout path, in traversal order, from upstream 2d4661e code
# reading (see OFFPATH_PATH_DERIVATION) -- the posture literal the declaration
# says is "derived from the traced full paths of a no-fault cell". The harness
# checks it against the first no-fault ``full`` cell before any fault cell
# (candidate_remote.workload_path_check); a mismatch stops the campaign.
OFFPATH_SYNC_PATH = (
    "frontendproxy", "frontend", "cartservice", "checkoutservice",
    "productcatalogservice", "currencyservice", "shippingservice", "quoteservice",
    "paymentservice", "emailservice", "flagd",
)
OFFPATH_SELECTED_CLOSURE = tuple(sorted(OFFPATH_SYNC_PATH))
# The asynchronous order consumers and their broker (DECLARATION.md: async =
# selected + kafka + frauddetection + accounting).
OFFPATH_ASYNC_ADDED_SERVICES = ("accountingservice", "frauddetectionservice", "kafka")
OFFPATH_ASYNC_CLOSURE = tuple(sorted(OFFPATH_SELECTED_CLOSURE + OFFPATH_ASYNC_ADDED_SERVICES))
OFFPATH_AUTHORITY = (
    "main repo research/otel-offpath/DECLARATION.md at 8194d74 (user 2026-10-01: direction (c), "
    "off-path consumer pause; fifth override of OTEL_RUN2_STOPPING_RULE.md; no launch until the "
    "user approves the built harness and the declaration)"
)
OFFPATH_PATH_DERIVATION = [
    "frontendproxy -> frontend: Envoy routes /api/* to the Next.js frontend (src/frontendproxy/envoy.tmpl.yaml)",
    "add-to-cart: src/frontend/pages/api/cart.ts POST -> CartGateway.addItem + getCart (cartservice)",
    "place-order: src/frontend/pages/api/checkout.ts POST -> CheckoutGateway.placeOrder (checkoutservice), "
    "then ProductCatalogService.getProduct per item (productcatalogservice)",
    "src/checkoutservice/main.go PlaceOrder: cartservice GetCart, productcatalogservice GetProduct, "
    "currencyservice Convert, shippingservice GetQuote (-> quoteservice), paymentservice Charge, "
    "shippingservice ShipOrder, cartservice EmptyCart, emailservice POST /send_order_confirmation "
    "(an error is logged and swallowed), then sendToPostProcessor (Kafka produce with RequiredAcks = "
    "sarama.NoResponse, src/checkoutservice/kafka/producer.go:24; erratum 2: no broker acknowledgement)",
    "flagd: checkoutservice (paymentServiceUnreachable, kafkaQueueProblems), paymentservice, cartservice "
    "and productcatalogservice evaluate feature flags through flagd on the request; measured: 600 of 600 "
    "offered-request traces of v3r1 no-fault-cost/b01-01-full contain flagd (and productcatalogservice), "
    "so flagd is on the traced synchronous path although the declaration's parenthetical list omits it",
    "kafka, frauddetectionservice, accountingservice: consumers of the orders topic "
    "(src/frauddetectionservice/.../main.kt poll loop, src/accountingservice/Consumer.cs); excluded from "
    "the synchronous comparison and added by async",
]
OFFPATH_ASYNC_FRAMING = (
    "checkout produces with RequiredAcks = NoResponse (producer.go:24, erratum 2) and "
    "frauddetectionservice and accountingservice consume asynchronously in separate consumer groups, "
    "so a consumer fault cannot reach the order response (code reading, method)"
)


def validate_fault_design(design: Any) -> dict[str, Any]:
    """The offpath fault parameters: known, implemented scenarios, sane timing."""
    if not isinstance(design, dict) or set(design) != set(OFFPATH_FAULT_DESIGN):
        raise ProtocolError("offpath fault design keys differ")
    scenarios = list(design["targetScenarios"]) + list(design["controlScenarios"])
    if (
        not design["targetScenarios"]
        or len(set(scenarios)) != len(scenarios)
        or any(name not in OFFPATH_FAULT_SCENARIOS for name in scenarios)
    ):
        raise ProtocolError("offpath fault scenarios are unknown, repeated or empty")
    for name in scenarios:
        if OFFPATH_FAULT_SCENARIOS[name]["implemented"] is not True:
            raise ProtocolError(f"offpath fault scenario {name} is declared but not implemented")
    onset, hold = design["onsetSeconds"], design["holdSeconds"]
    if (
        type(onset) is not int or type(hold) is not int or onset < 30 or hold < 1
        # the pre-window, the hold and a 120 s recovery must fit the 600 s window
        or onset + hold + 120 > 600
    ):
        raise ProtocolError("offpath fault timing does not fit the measurement window")
    if design["metricExportIntervalMilliseconds"] is not None:
        raise ProtocolError(
            "a metric export interval override is not implemented in the posture overlay "
            "(a harness emission change the user must approve)"
        )
    return design
OFFPATH_WORKLOAD = {
    "journey": "checkout-add-to-cart-then-place-order",
    "entry": "frontendproxy",
    "steps": [
        {
            "name": "add-to-cart",
            "method": "POST",
            "path": "/api/cart",
            "body": "{\"item\": {\"productId\": \"OLJCESPC7Z\", \"quantity\": 1}, \"userId\": <journey token>}",
        },
        {
            "name": "place-order",
            "method": "POST",
            "path": "/api/checkout?currencyCode=USD",
            "body": "people.json[0] (larry_sergei@example.com, USD, upstream test card) with userId = <journey token>",
        },
    ],
    "traceContext": (
        "one W3C trace per journey: both steps carry traceparent 00-<journey trace id>-<step span id>-01; "
        "add-to-cart carries the journey's request token and the ledger row's traceparent; place-order "
        "carries <token>-order with its own span id, so the frontendproxy witness keeps one row per "
        "journey token (the add-to-cart request) and place-order rows are not part of the witness"
    ),
    "ledger": (
        "request-ledger.json keeps its keys; one row per offered journey: startedAtEpoch = add-to-cart "
        "start, endedAtEpoch = end of the last step attempted, status = place-order status (or the failing "
        "step's), error None iff both steps return 200; a steps list carries each step's start, end, status"
    ),
    "journeysPerSecond": 1,
    "concurrency": 32,
    "offeredJourneys": 600,
    "stepTimeoutSeconds": 15,
    "readiness": "one complete journey with token readiness-not-scored returning 200 on both steps",
    "upstreamSource": (
        "upstream/opentelemetry-demo 2d4661e: src/frontend/pages/api/cart.ts, src/frontend/pages/api/"
        "checkout.ts, src/loadgenerator/locustfile.py checkout() (add_to_cart then POST /api/checkout "
        "with a people.json person), src/loadgenerator/people.json"
    ),
    "pathCheck": {
        "cell": "the first no-fault-cost full cell in plan order (before every fault cell)",
        "rule": (
            "every journey with error None has observedTraceServices minus accountingservice, "
            "frauddetectionservice and kafka equal to the selected closure, and at least one such "
            "journey exists"
        ),
        "artifact": "workload-path-check.json at the campaign root",
        "onFailure": "the campaign stops before any fault cell; terminal validation fails",
    },
}


def derive_offpath_descriptor(v3_path: Path | None = None) -> dict[str, Any]:
    """Generate the offpath descriptor from the byte-pinned v3 descriptor.

    This function IS the offpath descriptor's source: the checked-in
    ``otel-demo-offpath-v1.json`` must equal ``_pretty_bytes`` of its result
    (tested), so the file is regenerated, never hand-edited. Every v3 field is
    carried over unchanged except the regimes, the selected/async closures and
    their claim boundaries, fault timing and truth, the workload, the
    supersession record and the id.
    """
    path = Path(v3_path) if v3_path is not None else EPOCHS[OFFPATH_PREDECESSOR_EPOCH]["descriptor"]
    v3 = load_descriptor(path)
    if v3["id"] != OFFPATH_PREDECESSOR_EPOCH:
        raise ProtocolError("offpath is derived from the v3 descriptor only")
    document = copy.deepcopy(v3)
    document["id"] = EPOCH
    design = validate_fault_design(copy.deepcopy(OFFPATH_FAULT_DESIGN))
    regimes = offpath_regimes(design)
    document["design"]["regimes"] = [
        {"id": name, **REGIME_CONTRACTS[name]} for name in regimes
    ]
    document["design"]["totalRuns"] = len(regimes) * BLOCKS_PER_REGIME * len(FOUR_POSTURES)
    document["timing"]["faultOnsetSeconds"] = design["onsetSeconds"]
    document["timing"]["interventionHoldSeconds"] = design["holdSeconds"]
    scenarios = list(design["targetScenarios"]) + list(design["controlScenarios"])
    document["faultDesign"] = {
        **copy.deepcopy(design),
        "scenarios": {name: copy.deepcopy(OFFPATH_FAULT_SCENARIOS[name]) for name in scenarios},
        "authority": (
            "DECLARATION.md 8194d74 (fraud-pause, 15 s at 45 s, frontend-pause control) and erratum 2 "
            "(ff65eea: hold, scenario and export interval are parameters; declared defaults kept until "
            "the user chooses a redesign)"
        ),
    }
    fault = document["groundTruth"]["fault"]
    fault["requiredReceiptFields"] = sorted(set(fault["requiredReceiptFields"]) | {
        "barrierMonotonic", "appliedMonotonic", "revertingMonotonic",
        "appliedMonotonicOffsetSeconds", "revertingMonotonicOffsetSeconds",
        "duringRouteAvailable",
    })
    fault["scenarioContracts"] = [
        {
            "commandFamily": {
                "pause": "container-pause-unpause", "stop": "container-stop-start",
            }[OFFPATH_FAULT_SCENARIOS[name]["action"]],
            "containerIdentityRule": "same-container-pre-during-post",
            "duringPredicate": {
                "pause": "running-and-paused", "stop": "not-running",
            }[OFFPATH_FAULT_SCENARIOS[name]["action"]],
            "entryRouteDuringFault": OFFPATH_FAULT_SCENARIOS[name]["entryRouteDuringFault"],
            "postPredicate": "running-and-unpaused-and-journey-ready",
            "prePredicate": "running-and-unpaused",
            "scenario": name,
            "service": OFFPATH_FAULT_SCENARIOS[name]["service"],
        }
        for name in scenarios
    ]
    fault["offPathFraming"] = OFFPATH_ASYNC_FRAMING
    fault["detectionWindow"] = (
        "[appliedMonotonic, revertingMonotonic]: after the pause is observed, before the unpause "
        "command (Hotel compose_pause.py); offsets are relative to the shared barrier"
    )
    truth = document["groundTruth"]["path"]
    truth["expectedNoFaultPath"] = list(OFFPATH_SYNC_PATH)
    frontend_truth = truth["faultSpecificTruth"]["frontend-pause"]
    truth["faultSpecificTruth"] = {
        name: (
            copy.deepcopy(frontend_truth) if name == "frontend-pause" else {
                "duringFaultExpectedOutcome": "offered-journey-outcome-not-presumed",
                "duringFaultFullPathRequired": False,
                "postRecoveryFullPathRequired": True,
                "preFaultFullPathRequired": True,
            }
        )
        for name in scenarios
    }
    realization = document["postureRealization"]
    boundary = copy.deepcopy(realization["none"]["claimBoundary"])
    boundary["loadedButSilencedServices"] = list(EPOCHS[EPOCH]["claimBoundarySilenced"]["selected"])
    realization["selected"] = {
        "claimBoundary": copy.deepcopy(boundary),
        "closure": list(OFFPATH_SELECTED_CLOSURE),
        "closureDecision": (
            "instrumentation is activated on the synchronous checkout path ("
            + ", ".join(OFFPATH_SYNC_PATH)
            + "); every other application service runs uninstrumented"
        ),
        "currentControl": "materialized-posture-controls-selected-closure",
        "derivation": list(OFFPATH_PATH_DERIVATION),
        "reason": None,
        "status": "implemented",
    }
    realization["async"] = {
        "claimBoundary": copy.deepcopy(boundary),
        "closure": list(OFFPATH_ASYNC_CLOSURE),
        "closureDecision": (
            "instrumentation is activated on the selected closure plus "
            + ", ".join(OFFPATH_ASYNC_ADDED_SERVICES)
            + " (the orders topic's broker and its two consumers); every other application service "
            "runs uninstrumented"
        ),
        "currentControl": "materialized-posture-controls-async-closure",
        "reason": None,
        "status": "implemented",
    }
    document["workload"] = copy.deepcopy(OFFPATH_WORKLOAD)
    document["supersedes"] = {
        "authority": OFFPATH_AUTHORITY,
        "descriptorByteSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "descriptorCanonicalSha256": canonical_sha256(v3),
        "descriptorPath": str(path.resolve().relative_to(ROOT)),
        "studyEpoch": OFFPATH_PREDECESSOR_EPOCH,
        "v3Disposition": (
            "v3 (24 cells, /api/recommendations workload) keeps its own runs; offpath is a new epoch on "
            "fb14srv6 and is never pooled with v3, v2 or run 3; the v3 descriptor's bytes are unchanged"
        ),
        "whatChanged": [
            "workload: the offered unit is a checkout journey (add to cart, then place order) through "
            "frontendproxy with W3C trace context, one ledger row per journey",
            "selected = the synchronous checkout path, async = selected + kafka, frauddetectionservice, "
            "accountingservice; none and full unchanged; posture names unchanged",
            "regimes no-fault-cost, fraud-pause-effect, frontend-pause-effect; totalRuns 24 -> 36; each "
            "regime a 3x4 Latin rectangle",
            "fault timing and scenarios from faultDesign (declared default: onset 45 s, hold 15 s, as "
            "Hotel, for both pauses; fraud-pause = docker pause of frauddetectionservice); every receipt "
            "carries appliedMonotonic/revertingMonotonic",
        ],
    }
    return document


def schedule_candidates(epoch: str = EPOCH) -> tuple[tuple[tuple[str, ...], ...], ...]:
    """Every base permutation of the epoch's postures, each expanded into
    ``BLOCKS_PER_REGIME`` cyclic rotations (one per block).

    Three postures: six candidates, each a 3x3 Latin square (v1/v2 unchanged).
    Four postures: 24 candidates, each a 3x4 Latin rectangle.
    """
    codes = EPOCHS[epoch]["postureCodes"] if epoch in EPOCHS else None
    if codes is None:
        raise ProtocolError("unknown study epoch")
    candidates: list[tuple[tuple[str, ...], ...]] = []
    for coded in itertools.permutations(tuple(codes)):
        row = tuple(codes[item] for item in coded)
        candidates.append(tuple(row[shift:] + row[:shift] for shift in range(BLOCKS_PER_REGIME)))
    return tuple(candidates)


def allocate_schedules(epoch: str = EPOCH) -> dict[str, dict[str, Any]]:
    """Latin-rotation allocation seeded by study epoch and regime only.

    The epoch id is the selector preimage, so a new study epoch is a fresh
    randomization and a superseded epoch replays its own schedule unchanged.
    """
    if epoch not in EPOCHS:
        raise ProtocolError("unknown study epoch")
    candidates = schedule_candidates(epoch)
    used: set[int] = set()
    allocation: dict[str, dict[str, Any]] = {}
    for regime in epoch_regimes(epoch):
        selector = f"{epoch}\0{regime}\0{SCHEDULE_CONTEXT}".encode("utf-8")
        digest = hashlib.sha256(selector).hexdigest()
        initial = int.from_bytes(bytes.fromhex(digest), "big") % len(candidates)
        selected = initial
        while selected in used:
            selected = (selected + 1) % len(candidates)
        used.add(selected)
        allocation[regime] = {
            "selectorSha256": digest,
            "initialCandidateIndex": initial,
            "selectedCandidateIndex": selected,
            "collisionIncrements": (selected - initial) % len(candidates),
            "blocks": [list(block) for block in candidates[selected]],
        }
    return allocation


def validate_attempt(value: Any) -> int:
    if type(value) is not int or value < 1:
        raise ProtocolError(f"attempt must be a positive integer, observed {value!r}")
    return value


def campaign_attempt(environment: Mapping[str, str] | None = None) -> int:
    """The attempt the launcher selected, or the admission attempt when unset."""
    raw = (os.environ if environment is None else environment).get(ATTEMPT_ENVIRONMENT)
    if raw is None:
        return DEFAULT_ATTEMPT
    if not raw.isascii() or not raw.isdigit() or raw != str(int(raw)):
        raise ProtocolError(f"{ATTEMPT_ENVIRONMENT} must be a canonical positive integer, observed {raw!r}")
    return validate_attempt(int(raw))


def plan_attempt(plan: Any) -> int:
    """The one attempt every cell of a compiled plan carries."""
    try:
        attempts = {
            cell["runKey"]["attempt"]
            for root in plan["regimeRoots"]
            for block in root["blocks"]
            for cell in block["cells"]
        }
    except (KeyError, TypeError) as exc:
        raise ProtocolError("compiled plan cells carry no attempt") from exc
    if len(attempts) != 1:
        raise ProtocolError(f"compiled plan mixes attempts {sorted(map(repr, attempts))}")
    return validate_attempt(next(iter(attempts)))


def _compile(document: Mapping[str, Any], attempt: int) -> dict[str, Any]:
    attempt = validate_attempt(attempt)
    epoch = str(document["id"])
    allocation = allocate_schedules(epoch)
    roots: list[dict[str, Any]] = []
    all_run_ids: list[str] = []
    for regime in epoch_regimes(epoch):
        contract = REGIME_CONTRACTS[regime]
        blocks: list[dict[str, Any]] = []
        for block_number, order in enumerate(allocation[regime]["blocks"], start=1):
            cells: list[dict[str, Any]] = []
            for ordinal, posture in enumerate(order, start=1):
                run_key = {
                    "studyEpoch": epoch,
                    "regime": regime,
                    "block": block_number,
                    "posture": posture,
                    "attempt": attempt,
                }
                run_id = hashlib.sha256(canonical_json_bytes(run_key)).hexdigest()[:24]
                all_run_ids.append(run_id)
                cells.append(
                    {
                        "runKey": run_key,
                        "runId": run_id,
                        "ordinalPosition": ordinal,
                        "artifactRoot": (
                            f"runs/{regime}/b{block_number:02d}-{ordinal:02d}-{posture}"
                        ),
                        "realizationStatus": document["postureRealization"][posture][
                            "status"
                        ],
                        "fault": contract["fault"],
                    }
                )
            blocks.append(
                {
                    "block": block_number,
                    "order": list(order),
                    "cells": cells,
                }
            )
        roots.append(
            {
                "id": regime,
                **contract,
                "selectorSha256": allocation[regime]["selectorSha256"],
                "initialCandidateIndex": allocation[regime][
                    "initialCandidateIndex"
                ],
                "selectedCandidateIndex": allocation[regime][
                    "selectedCandidateIndex"
                ],
                "collisionIncrements": allocation[regime]["collisionIncrements"],
                "blocks": blocks,
            }
        )
    return {
        "schemaVersion": 1,
        "kind": "otel-demo-candidate-compiled-plan",
        "studyEpoch": epoch,
        "module": MODULE,
        "applicationFamily": APPLICATION_FAMILY,
        "channel": CHANNEL,
        "descriptorSha256": canonical_sha256(document),
        "scheduleVersion": SCHEDULE_CONTEXT,
        "regimeRoots": roots,
        "runCount": len(all_run_ids),
        "uniqueRunCount": len(set(all_run_ids)),
        "runtimeReady": False,
        "runtimeAuthorized": False,
        "candidateExecutionEnabled": False,
        "maximumEvidenceLabel": MAXIMUM_EVIDENCE_LABEL,
        "blockers": copy.deepcopy(document["workflow"]["constructionBlockers"]),
    }


def compile_plan(document: Mapping[str, Any], attempt: int = DEFAULT_ATTEMPT) -> dict[str, Any]:
    validate_descriptor(document)
    plan = _compile(document, attempt)
    validate_plan(document, plan)
    return copy.deepcopy(plan)


def validate_plan(document: Mapping[str, Any], plan: Any) -> None:
    validate_descriptor(document)
    expected = _compile(document, plan_attempt(plan))
    if canonical_json_bytes(plan) != canonical_json_bytes(expected):
        raise ProtocolError("compiled plan differs from the frozen schedule")
    postures = epoch_postures(str(document["id"]))
    total_runs = epoch_total_runs(str(document["id"]))
    if (
        plan.get("runCount") != total_runs
        or plan.get("uniqueRunCount") != total_runs
        or plan.get("runtimeReady") is not False
        or plan.get("runtimeAuthorized") is not False
        or plan.get("candidateExecutionEnabled") is not False
    ):
        raise ProtocolError("compiled plan geometry or runtime denial differs")
    observed: set[tuple[str, int, str]] = set()
    for root in plan["regimeRoots"]:
        positions: set[tuple[int, str]] = set()
        for block in root["blocks"]:
            if len(block["order"]) != len(postures) or set(block["order"]) != set(postures):
                raise ProtocolError("one block does not contain each posture exactly once")
            for ordinal, posture in enumerate(block["order"], start=1):
                if (ordinal, posture) in positions:
                    raise ProtocolError("a posture repeats an ordinal position within one regime")
                positions.add((ordinal, posture))
            for cell in block["cells"]:
                key = cell["runKey"]
                observed.add((key["regime"], key["block"], key["posture"]))
                if root["kind"] == "cost" and cell["fault"] is not None:
                    raise ProtocolError("cost cell contains a fault")
                if root["kind"] == "effect" and cell["fault"] is None:
                    raise ProtocolError("effect cell omits its fault")
    if len(observed) != total_runs:
        raise ProtocolError("compiled cell identities are not unique and complete")


def readiness_report(document: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    validate_plan(document, plan)
    unsupported = [
        posture
        for posture in epoch_postures(str(document["id"]))
        if document["postureRealization"][posture]["status"] != "implemented"
    ]
    return {
        "schemaVersion": 1,
        "kind": "otel-demo-candidate-construction-readiness",
        "studyEpoch": str(document["id"]),
        "descriptorSha256": canonical_sha256(document),
        "planSha256": canonical_sha256(plan),
        "runCount": epoch_total_runs(str(document["id"])),
        "unsupportedPostures": unsupported,
        "constructionValid": True,
        "runtimeReady": False,
        "runtimeAuthorized": False,
        "candidateExecutionEnabled": False,
        "blockers": copy.deepcopy(document["workflow"]["constructionBlockers"]),
    }


def _install_or_verify(path: Path, payload: bytes, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
            raise ProtocolError(f"retained {label} differs")
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProtocolError(f"{label} is not a regular file")
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:  # pragma: no cover - kernel I/O defect
                raise ProtocolError(f"{label} write made no progress")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def materialize(
    root: Path, descriptor_path: Path = DEFAULT_DESCRIPTOR, attempt: int | None = None,
) -> dict[str, Any]:
    """Create or exactly replay local construction artifacts without execution.

    ``attempt`` defaults to ``campaign_attempt()``. A retained plan directory
    compiled for another attempt fails the byte comparison below, so switching
    attempts means archiving the old plan directory first.
    """

    root = Path(root).resolve()
    if root in {Path("/"), Path.home(), ROOT} or root in ROOT.parents:
        raise ProtocolError(f"unsafe construction root: {root}")
    document = load_descriptor(descriptor_path)
    plan = compile_plan(document, campaign_attempt() if attempt is None else attempt)
    receipt = readiness_report(document, plan)
    _install_or_verify(root / DESCRIPTOR_COPY, _pretty_bytes(document), DESCRIPTOR_COPY)
    _install_or_verify(root / PLAN_COPY, _pretty_bytes(plan), PLAN_COPY)
    _install_or_verify(root / RECEIPT_COPY, _pretty_bytes(receipt), RECEIPT_COPY)
    retained_document = strict_json_loads((root / DESCRIPTOR_COPY).read_text())
    retained_plan = strict_json_loads((root / PLAN_COPY).read_text())
    retained_receipt = strict_json_loads((root / RECEIPT_COPY).read_text())
    validate_plan(retained_document, retained_plan)
    if canonical_json_bytes(retained_receipt) != canonical_json_bytes(
        readiness_report(retained_document, retained_plan)
    ):
        raise ProtocolError("retained construction receipt differs")
    return copy.deepcopy(retained_receipt)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--attempt", type=int, default=None)
    parser.add_argument(
        "--emit-v3-descriptor", action="store_true",
        help="write (exclusive-create) or byte-verify <root> as the v3 descriptor derived from v2",
    )
    parser.add_argument(
        "--emit-offpath-descriptor", action="store_true",
        help="write (exclusive-create) or byte-verify <root> as the offpath descriptor derived from v3",
    )
    args = parser.parse_args(argv)
    if args.emit_offpath_descriptor:
        _install_or_verify(Path(args.root), _pretty_bytes(derive_offpath_descriptor()), "offpath descriptor")
        print(canonical_sha256(derive_offpath_descriptor()))
        return 0
    if args.emit_v3_descriptor:
        _install_or_verify(Path(args.root), _pretty_bytes(derive_v3_descriptor()), "v3 descriptor")
        print(canonical_sha256(derive_v3_descriptor()))
        return 0
    print(json.dumps(materialize(args.root, args.descriptor, args.attempt), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ATTEMPT_ENVIRONMENT",
    "DEFAULT_ATTEMPT",
    "DEFAULT_DESCRIPTOR",
    "campaign_attempt",
    "plan_attempt",
    "EPOCH",
    "EPOCHS",
    "FROZEN_EPOCH",
    "ProtocolError",
    "allocate_schedules",
    "epoch_contract",
    "canonical_sha256",
    "compile_plan",
    "derive_offpath_descriptor",
    "derive_v3_descriptor",
    "epoch_regimes",
    "epoch_postures",
    "epoch_total_runs",
    "load_descriptor",
    "materialize",
    "readiness_report",
    "schedule_candidates",
    "strict_json_loads",
    "validate_descriptor",
    "validate_plan",
]
