"""Executor-neutral lifecycle state and receipt validation.

SUT modules own how an operation is performed. This module only enforces the
ordering and evidence contract shared by SSH, AWS/SSM, Dagger, and kind.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Protocol


class State(str, Enum):
    UNKNOWN = "unknown"
    INVENTORIED = "inventoried"
    QUARANTINED = "quarantined"
    STOPPED = "stopped"
    MATERIALIZED = "materialized"
    DEPLOYED = "deployed"
    READY = "ready"
    POSTURE_PROVEN = "posture-proven"
    RUNNING = "running"
    COLLECTED = "collected"
    FETCHED = "fetched"
    VALIDATED = "validated"
    FAILED = "failed"


TRANSITIONS: dict[str, tuple[frozenset[State], State]] = {
    "preflight": (frozenset({State.UNKNOWN}), State.INVENTORIED),
    "quarantine": (frozenset({State.INVENTORIED}), State.QUARANTINED),
    "stop": (frozenset({State.INVENTORIED, State.QUARANTINED, State.READY,
                         State.POSTURE_PROVEN, State.COLLECTED, State.FAILED}), State.STOPPED),
    "materialize": (frozenset({State.INVENTORIED, State.QUARANTINED, State.STOPPED}),
                    State.MATERIALIZED),
    "deploy": (frozenset({State.MATERIALIZED}), State.DEPLOYED),
    "start": (frozenset({State.DEPLOYED}), State.READY),
    "apply_posture": (frozenset({State.READY}), State.POSTURE_PROVEN),
    "run_workload": (frozenset({State.POSTURE_PROVEN}), State.RUNNING),
    "inject": (frozenset({State.RUNNING}), State.RUNNING),
    "collect": (frozenset({State.RUNNING}), State.COLLECTED),
    "teardown": (frozenset({State.READY, State.POSTURE_PROVEN, State.RUNNING,
                             State.COLLECTED, State.FAILED}), State.STOPPED),
    "fetch": (frozenset({State.STOPPED}), State.FETCHED),
    "validate": (frozenset({State.FETCHED}), State.VALIDATED),
}


@dataclass(frozen=True)
class OperationReceipt:
    run_id: str
    operation_id: str
    operation: str
    state_before: State
    state_after: State
    status: str
    started_at: str
    ended_at: str
    executor: str
    target: str
    source: Mapping[str, Any]
    parent_operation_id: str | None = None
    requested: Mapping[str, Any] = field(default_factory=dict)
    observed: Mapping[str, Any] = field(default_factory=dict)
    ownership_scope: Mapping[str, Any] = field(default_factory=dict)
    findings: tuple[Mapping[str, Any], ...] = ()
    artifacts: tuple[Mapping[str, Any], ...] = ()
    tool_versions: Mapping[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    schema_version: int = 1

    def as_json(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "runId": self.run_id,
            "operationId": self.operation_id,
            "parentOperationId": self.parent_operation_id,
            "operation": self.operation,
            "target": self.target,
            "startedAt": self.started_at,
            "endedAt": self.ended_at,
            "status": self.status,
            "source": dict(self.source),
            "ownershipScope": dict(self.ownership_scope),
            "findings": list(self.findings),
            "artifacts": list(self.artifacts),
            "toolVersions": dict(self.tool_versions),
            "executor": self.executor,
            "requested": dict(self.requested),
            "observed": dict(self.observed),
            "errors": list(self.errors),
            "stateBefore": self.state_before.value,
            "stateAfter": self.state_after.value,
        }

    @property
    def successful(self) -> bool:
        return self.status in {"ok", "noncanonical"}


class Executor(Protocol):
    """Behavioral boundary implemented by SSH, SSM, Dagger, or kind adapters."""

    name: str

    def execute(self, operation: str, context: Mapping[str, Any]) -> OperationReceipt: ...


class LifecycleJournal:
    def __init__(self) -> None:
        self.state = State.UNKNOWN
        self.receipts: list[OperationReceipt] = []

    def accept(self, receipt: OperationReceipt) -> State:
        if not receipt.run_id or not receipt.operation_id:
            raise ValueError("receipt run and operation IDs must be non-empty")
        if receipt.status not in {"ok", "failed", "blocked", "noncanonical"}:
            raise ValueError(f"invalid lifecycle status: {receipt.status}")
        try:
            started = datetime.fromisoformat(receipt.started_at.replace("Z", "+00:00"))
            ended = datetime.fromisoformat(receipt.ended_at.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError("receipt timestamps must be ISO-8601 date-times") from exc
        if started.tzinfo is None or ended.tzinfo is None or ended < started:
            raise ValueError("receipt timestamps must be timezone-aware and nondecreasing")
        if receipt.operation not in TRANSITIONS:
            raise ValueError(f"unknown lifecycle operation: {receipt.operation}")
        allowed, expected_after = TRANSITIONS[receipt.operation]
        if receipt.state_before != self.state:
            raise ValueError(
                f"receipt starts at {receipt.state_before.value}, journal is {self.state.value}"
            )
        if receipt.state_before not in allowed:
            raise ValueError(
                f"operation {receipt.operation} is not allowed from {receipt.state_before.value}"
            )
        if receipt.successful:
            if receipt.state_after != expected_after:
                raise ValueError(
                    f"successful {receipt.operation} must end at {expected_after.value}"
                )
        elif receipt.state_after != State.FAILED:
            raise ValueError("failed operation must end in failed state")
        if receipt.successful and receipt.errors:
            raise ValueError("successful receipt cannot contain errors")
        if not receipt.successful and not receipt.errors:
            raise ValueError("failed receipt must explain at least one error")
        if self.receipts:
            previous = self.receipts[-1]
            if receipt.parent_operation_id != previous.operation_id:
                raise ValueError("receipt parent does not reference the preceding operation")
            if receipt.run_id != previous.run_id:
                raise ValueError("lifecycle receipts must retain one run ID")
            if dict(receipt.source) != dict(previous.source):
                raise ValueError("lifecycle source provenance changed between operations")
            previous_ended = datetime.fromisoformat(previous.ended_at.replace("Z", "+00:00"))
            if started < previous_ended:
                raise ValueError("lifecycle operations overlap or are out of order")
            if any(item.operation_id == receipt.operation_id for item in self.receipts):
                raise ValueError("lifecycle operation IDs must be unique")
        if not self.receipts and receipt.parent_operation_id is not None:
            raise ValueError("first receipt cannot declare a parent operation")
        self.receipts.append(receipt)
        self.state = receipt.state_after
        return self.state
