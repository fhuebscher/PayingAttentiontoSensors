#!/usr/bin/env python3
"""Construction-only materialization for the frozen TeaStore schedule.

The public path in this module can only materialize immutable compiler output
and replay a retained simulation journal.  It has no executor, callback,
launcher, subprocess, SSH, Docker, socket, or transport seam.

``simulate_compiled_schedule`` is a separate fixture exercise.  It derives one
digest from each compiled cell and appends a typed, hash-chained ``simulated``
record.  It never creates a run artifact root and its fixture digests are not
evidence.  Neither path authorizes runtime or makes a scientific claim.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, NoReturn


ROOT = Path(__file__).resolve().parents[3]


def _study_epoch_module():
    """The tree's study-epoch selector (execution/study_epoch.py), loaded by path (python3 -I)."""
    path = Path(__file__).resolve().parent / "study_epoch.py"
    name = "teastore_study_epoch_" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:  # pragma: no cover - install defect
            raise RuntimeError(f"cannot load the study-epoch selector: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


# With no selector: the frozen descriptor and compiler (c1724b1 literals).
EPOCH = _study_epoch_module().active(ROOT)
DEFAULT_DESCRIPTOR = ROOT / EPOCH["descriptorRelative"]
DESCRIPTOR_COPY = "campaign-descriptor.json"
PLAN_COPY = "compiled-plan.json"
CAMPAIGN_MANIFEST = "campaign.json"
SIMULATION_JOURNAL = "simulation-state.jsonl"
LOCK_FILE = ".candidate-schedule.lock"

CAMPAIGN_CONTRACT = "teastore-candidate-pilot-evidence-v1"
SIMULATION_CONTRACT = "teastore-candidate-schedule-simulation-v1"
SIMULATION_FIXTURE_CONTRACT = "teastore-candidate-cell-fixture-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ScheduleError(ValueError):
    """The materialized schedule or simulation journal is invalid."""


def _candidate_pilot_module():
    path = Path(__file__).with_name(Path(EPOCH["compilerRelative"]).name)
    spec = importlib.util.spec_from_file_location(
        "teastore_candidate_pilot_for_schedule", path)
    if spec is None or spec.loader is None:  # pragma: no cover - install defect
        raise RuntimeError(f"cannot load candidate-pilot compiler: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reject_constant(value: str) -> NoReturn:
    raise ScheduleError(f"non-finite JSON value is forbidden: {value}")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScheduleError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(payload: bytes, where: str) -> Any:
    try:
        text = payload.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except ScheduleError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ScheduleError(f"invalid JSON in {where}: {exc}") from exc


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ScheduleError(f"value is not canonical JSON: {exc}") from exc


def _pretty_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ScheduleError(f"value is not serializable JSON: {exc}") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_value(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _same_typed_json(left: Any, right: Any) -> bool:
    """Compare JSON values without Python's ``True == 1`` coercion."""

    try:
        return _canonical_bytes(left) == _canonical_bytes(right)
    except ScheduleError:
        return False


def _regular_file_bytes(path: Path, where: str) -> bytes:
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
            raise ScheduleError(f"{where} is not a regular non-symlink file")
        before = (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        payload = path.read_bytes()
        after_meta = path.lstat()
        after = (after_meta.st_dev, after_meta.st_ino, after_meta.st_size,
                 after_meta.st_mtime_ns)
        if before != after or len(payload) != metadata.st_size:
            raise ScheduleError(f"{where} changed while being read")
        return payload
    except ScheduleError:
        raise
    except OSError as exc:
        raise ScheduleError(f"cannot read {where}: {exc}") from exc


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _install_or_verify(path: Path, expected: bytes, where: str) -> None:
    """Create one immutable file, or verify the existing bytes exactly."""

    if path.exists() or path.is_symlink():
        actual = _regular_file_bytes(path, where)
        if actual != expected:
            raise ScheduleError(f"{where} differs from deterministic materialization")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(expected)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_name, path)
        except FileExistsError:
            actual = _regular_file_bytes(path, where)
            if actual != expected:
                raise ScheduleError(f"{where} differs after concurrent materialization")
        _fsync_directory(path.parent)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


@contextmanager
def _campaign_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / LOCK_FILE
    if lock_path.is_symlink():
        raise ScheduleError("campaign lock cannot be a symbolic link")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ScheduleError("campaign lock is not a regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _flatten_plan(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return cells in the exact nested order emitted by ``compile_plan``."""

    cells: list[dict[str, Any]] = []
    seen: set[str] = set()
    if EPOCH["sweep"]:
        # Traffic sweep: blocks hold the execution order (lead cell, then the seeded shuffle).
        try:
            for block in plan["blocks"]:
                for cell in block["cells"]:
                    if cell["runKey"]["block"] != block["block"]:
                        raise ScheduleError("compiled cell block differs from its root")
                    if cell["runId"] in seen:
                        raise ScheduleError(f"compiled plan repeats run ID {cell['runId']}")
                    seen.add(cell["runId"])
                    cells.append(copy.deepcopy(cell))
        except (KeyError, TypeError) as exc:
            raise ScheduleError(f"compiled plan has no executable cell order: {exc}") from exc
        if len(cells) != plan.get("runCount"):
            raise ScheduleError("compiled cell count differs from compiled runCount")
        return cells
    try:
        for regime_root in plan["regimeRoots"]:
            regime = regime_root["regime"]
            for block in regime_root["blocks"]:
                for cell in block["cells"]:
                    if cell["runKey"]["regime"] != regime:
                        raise ScheduleError("compiled cell regime differs from its root")
                    if cell["runKey"]["block"] != block["block"]:
                        raise ScheduleError("compiled cell block differs from its root")
                    if cell["runId"] in seen:
                        raise ScheduleError(f"compiled plan repeats run ID {cell['runId']}")
                    seen.add(cell["runId"])
                    cells.append(copy.deepcopy(cell))
    except (KeyError, TypeError) as exc:
        raise ScheduleError(f"compiled plan has no executable cell order: {exc}") from exc
    if len(cells) != plan.get("runCount"):
        raise ScheduleError("compiled cell count differs from compiled runCount")
    return cells


def _campaign_manifest(document: dict[str, Any], descriptor_bytes: bytes,
                       plan: dict[str, Any], plan_bytes: bytes) -> dict[str, Any]:
    cells = _flatten_plan(plan)
    allocation = plan["scheduleAllocation"]
    runs = []
    for cell in cells:
        key = cell["runKey"]
        ordinal = cell["ordinalPosition"]
        posture = key["posture"]
        regime = key["regime"]
        block = key["block"]
        runs.append({
            "studyEpoch": key["studyEpoch"],
            "regime": regime,
            "block": block,
            "posture": posture,
            "attempt": key["attempt"],
            "ordinal": ordinal,
            "runId": cell["runId"],
            "compiledArtifactRoot": cell["artifactRoot"],
            # This path is derived only from the compiled identity.  No local
            # construction API creates it or selects a different identity.
            "path": f"runs/{regime}/b{block:02d}-{ordinal:02d}-{posture}",
        })
    descriptor_canonical_sha = _sha256_value(document)
    if descriptor_canonical_sha != plan.get("descriptorSha256"):
        raise ScheduleError("compiled plan descriptor SHA-256 differs from source document")
    return {
        "schemaVersion": 1,
        "contract": CAMPAIGN_CONTRACT,
        "kind": "candidate-pilot-campaign",
        "studyEpoch": plan["studyEpoch"],
        "descriptorId": plan["descriptorId"],
        "descriptorCanonicalSha256": descriptor_canonical_sha,
        "descriptorBytesSha256": _sha256_bytes(descriptor_bytes),
        "compiledPlanCanonicalSha256": _sha256_value(plan),
        "compiledPlanBytesSha256": _sha256_bytes(plan_bytes),
        "scheduleVersion": EPOCH["scheduleVersion"],
        "selectorDigests": {
            regime: allocation[regime]["selectorSha256"] for regime in allocation
        },
        "schedules": {
            regime: allocation[regime]["blocks"] for regime in allocation
        },
        "runs": runs,
        "runCount": plan["runCount"],
        "maximumEvidenceLabel": plan["maximumRunEvidenceLabel"],
        "canonical": False,
        "promotionAuthorized": False,
        "runtimeEnabledByThisManifest": False,
    }


def materialize_campaign(root: Path, descriptor_path: Path = DEFAULT_DESCRIPTOR) -> dict[str, Any]:
    """Materialize or exactly replay the frozen local schedule.

    The caller should hold ``_campaign_lock`` when it will execute cells.  This
    function is also safe for read-mostly inspection because every file is
    created without replacement and existing bytes must match exactly.
    """

    root = Path(root).resolve()
    descriptor_path = Path(descriptor_path).resolve()
    descriptor_bytes = _regular_file_bytes(descriptor_path, "source descriptor")
    candidate = _candidate_pilot_module()
    try:
        document = candidate.strict_json_loads(
            descriptor_bytes.decode("utf-8", errors="strict"))
        candidate.validate_descriptor(document)
        plan = candidate.compile_plan(document)
        candidate.validate_plan(document, plan)
    except (UnicodeError, ValueError) as exc:
        raise ScheduleError(f"candidate descriptor/plan is not frozen: {exc}") from exc
    plan_bytes = _pretty_bytes(plan)
    campaign = _campaign_manifest(document, descriptor_bytes, plan, plan_bytes)
    campaign_bytes = _pretty_bytes(campaign)

    _install_or_verify(root / DESCRIPTOR_COPY, descriptor_bytes, DESCRIPTOR_COPY)
    _install_or_verify(root / PLAN_COPY, plan_bytes, PLAN_COPY)
    _install_or_verify(root / CAMPAIGN_MANIFEST, campaign_bytes, CAMPAIGN_MANIFEST)

    # Replay from retained bytes as a second, independent binding check.
    retained_descriptor = _strict_json(
        _regular_file_bytes(root / DESCRIPTOR_COPY, DESCRIPTOR_COPY), DESCRIPTOR_COPY)
    retained_plan = _strict_json(_regular_file_bytes(root / PLAN_COPY, PLAN_COPY), PLAN_COPY)
    retained_campaign = _strict_json(
        _regular_file_bytes(root / CAMPAIGN_MANIFEST, CAMPAIGN_MANIFEST), CAMPAIGN_MANIFEST)
    try:
        candidate.validate_descriptor(retained_descriptor)
        candidate.validate_plan(retained_descriptor, retained_plan)
    except ValueError as exc:
        raise ScheduleError(f"retained descriptor/plan replay failed: {exc}") from exc
    if not _same_typed_json(retained_campaign, campaign):
        raise ScheduleError("retained campaign manifest differs after replay")
    if retained_campaign["descriptorCanonicalSha256"] != _sha256_value(retained_descriptor):
        raise ScheduleError("retained descriptor canonical SHA-256 differs from campaign")
    if retained_campaign["descriptorBytesSha256"] != _sha256_bytes(descriptor_bytes):
        raise ScheduleError("retained descriptor byte SHA-256 differs from campaign")
    if retained_campaign["compiledPlanCanonicalSha256"] != _sha256_value(retained_plan):
        raise ScheduleError("retained plan canonical SHA-256 differs from campaign")
    if retained_campaign["compiledPlanBytesSha256"] != _sha256_bytes(plan_bytes):
        raise ScheduleError("retained plan byte SHA-256 differs from campaign")
    return {
        "document": retained_descriptor,
        "plan": retained_plan,
        "campaign": retained_campaign,
        "campaignSha256": _sha256_bytes(campaign_bytes),
        "cells": _flatten_plan(retained_plan),
    }


SIMULATION_JOURNAL_KEYS = {
    "schemaVersion", "contract", "recordSequence", "previousRecordSha256",
    "recordSha256", "campaignSha256", "descriptorSha256", "compiledPlanSha256",
    "event", "runId", "runKey", "state", "fixtureSha256", "reason",
}


def _record_without_hash(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "recordSha256"}


def _append_record(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    encoded = _canonical_bytes(record) + b"\n"
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ScheduleError("simulation journal is not a regular file")
        written = 0
        while written < len(encoded):
            count = os.write(descriptor, encoded[written:])
            if count <= 0:  # pragma: no cover - kernel I/O defect
                raise ScheduleError("simulation journal append made no progress")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)
    return record


def _simulation_record(*, event: str, cell: Mapping[str, Any], state: str,
                       fixture_sha256: str | None, reason: str | None,
                       records: list[dict[str, Any]],
                       bindings: Mapping[str, str]) -> dict[str, Any]:
    record = {
        "schemaVersion": 1,
        "contract": SIMULATION_CONTRACT,
        "recordSequence": len(records),
        "previousRecordSha256": records[-1]["recordSha256"] if records else "0" * 64,
        "recordSha256": None,
        "campaignSha256": bindings["campaignSha256"],
        "descriptorSha256": bindings["descriptorSha256"],
        "compiledPlanSha256": bindings["compiledPlanSha256"],
        "event": event,
        "runId": cell["runId"],
        "runKey": copy.deepcopy(cell["runKey"]),
        "state": state,
        "fixtureSha256": fixture_sha256,
        "reason": reason,
    }
    record["recordSha256"] = _sha256_value(_record_without_hash(record))
    return record


def _journal_bindings(materialized: Mapping[str, Any]) -> dict[str, str]:
    campaign = materialized["campaign"]
    return {
        "campaignSha256": materialized["campaignSha256"],
        "descriptorSha256": campaign["descriptorCanonicalSha256"],
        "compiledPlanSha256": campaign["compiledPlanCanonicalSha256"],
    }


def _fixture_sha256(materialized: Mapping[str, Any], cell: Mapping[str, Any]) -> str:
    return _sha256_value({
        "schemaVersion": 1,
        "contract": SIMULATION_FIXTURE_CONTRACT,
        "campaignSha256": materialized["campaignSha256"],
        "cell": cell,
    })


def replay_simulation_journal(
    root: Path, materialized: Mapping[str, Any]
) -> dict[str, Any]:
    """Strictly replay the append-only fixture-simulation chain."""

    path = Path(root).resolve() / SIMULATION_JOURNAL
    if not path.exists() and not path.is_symlink():
        return {"records": [], "runs": {}, "stopped": False}
    payload = _regular_file_bytes(path, SIMULATION_JOURNAL)
    if not payload:
        return {"records": [], "runs": {}, "stopped": False}
    if not payload.endswith(b"\n"):
        raise ScheduleError("simulation journal has a truncated final record")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ScheduleError("simulation journal is not UTF-8") from exc
    if any(not line for line in text.splitlines()):
        raise ScheduleError("simulation journal contains an empty record")

    cells = materialized["cells"]
    bindings = _journal_bindings(materialized)
    records: list[dict[str, Any]] = []
    states: dict[str, dict[str, Any]] = {}
    stopped = False
    for index, line in enumerate(text.splitlines()):
        record = _strict_json(
            line.encode("utf-8"), f"{SIMULATION_JOURNAL} line {index + 1}"
        )
        if not isinstance(record, dict) or set(record) != SIMULATION_JOURNAL_KEYS:
            raise ScheduleError(f"simulation record {index} fields differ")
        if (type(record.get("schemaVersion")) is not int
                or record.get("schemaVersion") != 1
                or record.get("contract") != SIMULATION_CONTRACT):
            raise ScheduleError(f"simulation record {index} schema/contract differs")
        if type(record.get("recordSequence")) is not int or record.get("recordSequence") != index:
            raise ScheduleError(f"simulation record {index} sequence differs")
        expected_previous = records[-1]["recordSha256"] if records else "0" * 64
        if record.get("previousRecordSha256") != expected_previous:
            raise ScheduleError(f"simulation record {index} chain differs")
        digest = record.get("recordSha256")
        if (not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None
                or digest != _sha256_value(_record_without_hash(record))):
            raise ScheduleError(f"simulation record {index} self hash differs")
        if any(record.get(key) != value for key, value in bindings.items()):
            raise ScheduleError(f"simulation record {index} campaign binding differs")
        if stopped:
            raise ScheduleError("simulation journal contains a record after stop")

        event = record.get("event")
        run_id = record.get("runId")
        next_index = len(states)
        if next_index >= len(cells):
            raise ScheduleError("simulation journal contains more cells than the plan")
        cell = cells[next_index]
        if (run_id != cell["runId"]
                or not _same_typed_json(record.get("runKey"), cell["runKey"])):
            raise ScheduleError(
                f"simulation record {index} is missing, duplicate, reordered, or relabelled"
            )
        fixture_sha256 = record.get("fixtureSha256")
        reason = record.get("reason")
        if event == "cell-simulated":
            if (record.get("state") != "simulated"
                    or not isinstance(fixture_sha256, str)
                    or SHA256_RE.fullmatch(fixture_sha256) is None
                    or fixture_sha256 != _fixture_sha256(materialized, cell)
                    or reason is not None):
                raise ScheduleError(f"cell {run_id} has an invalid simulation record")
            states[run_id] = {"state": "simulated", "record": record}
        elif event == "simulation-stop":
            if (record.get("state") != "stopped" or fixture_sha256 is not None
                    or not isinstance(reason, str) or not reason.strip()):
                raise ScheduleError("simulation-stop record fields differ")
            stopped = True
        else:
            raise ScheduleError(f"simulation record {index} has unknown event {event!r}")
        records.append(record)
    return {"records": records, "runs": states, "stopped": stopped}


def _append_simulation(
    root: Path,
    replay: dict[str, Any],
    *,
    event: str,
    cell: Mapping[str, Any],
    state: str,
    fixture_sha256: str | None,
    reason: str | None,
    materialized: Mapping[str, Any],
) -> dict[str, Any]:
    record = _simulation_record(
        event=event,
        cell=cell,
        state=state,
        fixture_sha256=fixture_sha256,
        reason=reason,
        records=replay["records"],
        bindings=_journal_bindings(materialized),
    )
    _append_record(Path(root).resolve() / SIMULATION_JOURNAL, record)
    replay["records"].append(record)
    return record


def _summary(materialized: Mapping[str, Any], replay: Mapping[str, Any],
             *, status: str, simulated_this_call: list[str]) -> dict[str, Any]:
    fixtures = [
        {
            "runId": cell["runId"],
            "fixtureSha256": replay["runs"][cell["runId"]]["record"]["fixtureSha256"],
        }
        for cell in materialized["cells"]
        if cell["runId"] in replay["runs"]
    ]
    return {
        "schemaVersion": 1,
        "kind": "compiled-schedule-fixture-simulation-receipt",
        "status": status,
        "simulationOnly": True,
        "runtimeAuthorized": False,
        "candidateExecutionEnabled": False,
        "campaignSha256": materialized["campaignSha256"],
        "descriptorSha256": materialized["campaign"]["descriptorCanonicalSha256"],
        "compiledPlanSha256": materialized["campaign"]["compiledPlanCanonicalSha256"],
        "scheduledCells": len(materialized["cells"]),
        "simulatedCells": len(fixtures),
        "stateCounts": {"simulated": len(fixtures)},
        "simulatedThisCall": simulated_this_call,
        "fixtures": fixtures,
        "stopped": bool(replay["stopped"]),
        "promotionAuthorized": False,
    }


def run_local_schedule(
    root: Path,
    *,
    descriptor_path: Path = DEFAULT_DESCRIPTOR,
) -> dict[str, Any]:
    """Materialize and replay only; this public path cannot execute a cell.

    The keyword-only signature intentionally rejects a legacy positional or
    keyword executor before the body runs, so even its campaign root is not
    created.  Retained simulation rows are inspected but never appended here.
    """

    root = Path(root).resolve()
    with _campaign_lock(root):
        materialized = materialize_campaign(root, descriptor_path)
        replay = replay_simulation_journal(root, materialized)
        return {
            "schemaVersion": 1,
            "kind": "compiled-schedule-materialization-receipt",
            "status": "materialized",
            "runtimeAuthorized": False,
            "candidateExecutionEnabled": False,
            "campaignSha256": materialized["campaignSha256"],
            "descriptorSha256": materialized["campaign"]["descriptorCanonicalSha256"],
            "compiledPlanSha256": materialized["campaign"]["compiledPlanCanonicalSha256"],
            "scheduledCells": len(materialized["cells"]),
            "retainedSimulationRecords": len(replay["records"]),
            "promotionAuthorized": False,
        }


def simulate_compiled_schedule(
    root: Path,
    *,
    descriptor_path: Path = DEFAULT_DESCRIPTOR,
    max_cells: int | None = None,
) -> dict[str, Any]:
    """Exercise exactly the compiled cells as non-evidentiary fixtures.

    No callback is accepted.  Each fixture digest is derived entirely from the
    retained campaign binding and compiled cell.  The function creates no path
    under ``runs/``; a pre-existing compiled run path is instead a permanent
    simulation stop so a fixture exercise cannot overlap runtime artifacts.
    """

    if max_cells is not None and (type(max_cells) is not int or max_cells < 0):
        raise ScheduleError("max_cells must be null or a non-negative integer")
    root = Path(root).resolve()
    simulated_this_call: list[str] = []
    with _campaign_lock(root):
        materialized = materialize_campaign(root, descriptor_path)
        replay = replay_simulation_journal(root, materialized)
        if replay["stopped"]:
            return _summary(
                materialized, replay, status="stopped",
                simulated_this_call=simulated_this_call,
            )

        for cell in materialized["cells"]:
            run_id = cell["runId"]
            if run_id in replay["runs"]:
                continue
            if max_cells is not None and len(simulated_this_call) >= max_cells:
                return _summary(
                    materialized, replay, status="paused",
                    simulated_this_call=simulated_this_call,
                )

            manifest_row = next(
                row for row in materialized["campaign"]["runs"]
                if row["runId"] == run_id
            )
            run_artifact_root = root / manifest_row["path"]
            if run_artifact_root.exists() or run_artifact_root.is_symlink():
                _append_simulation(
                    root, replay, event="simulation-stop", cell=cell,
                    state="stopped", fixture_sha256=None,
                    reason="compiled run artifact root already exists",
                    materialized=materialized,
                )
                replay = replay_simulation_journal(root, materialized)
                return _summary(
                    materialized, replay, status="stopped",
                    simulated_this_call=simulated_this_call,
                )

            _append_simulation(
                root, replay, event="cell-simulated", cell=cell,
                state="simulated",
                fixture_sha256=_fixture_sha256(materialized, cell),
                reason=None, materialized=materialized,
            )
            simulated_this_call.append(run_id)
            replay = replay_simulation_journal(root, materialized)

        return _summary(
            materialized, replay, status="complete",
            simulated_this_call=simulated_this_call,
        )


__all__ = [
    "CAMPAIGN_MANIFEST", "DEFAULT_DESCRIPTOR", "DESCRIPTOR_COPY", "PLAN_COPY",
    "SIMULATION_JOURNAL", "ScheduleError", "materialize_campaign",
    "replay_simulation_journal", "run_local_schedule", "simulate_compiled_schedule",
]
