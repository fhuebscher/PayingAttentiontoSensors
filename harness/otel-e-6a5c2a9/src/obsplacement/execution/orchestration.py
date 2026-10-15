"""Design-time orchestration contract shared by all execution backends.

This module is deliberately unable to launch infrastructure.  It validates
immutable inputs and renders argv-only delegation plans for an external
orchestrator (including Dagger).  SUT-specific behavior remains in module
adapters.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


PHASE_ORDER: tuple[str, ...] = (
    "preflight",
    "quarantine",
    "stop",
    "materialize",
    "deploy",
    "start",
    "apply_posture",
    "run_workload",
    "inject",
    "collect",
    "teardown",
    "fetch",
    "validate",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_BROAD_OWNERSHIP = {"*", "/", ".", "all", "any", "host", "global", "everything"}


class ContractError(ValueError):
    """The orchestration plan is unsafe, ambiguous, or incompatible."""


def _keys(value: Mapping[str, Any], required: set[str], *, where: str) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    extra = sorted(actual - required)
    if missing or extra:
        raise ContractError(f"{where} keys mismatch; missing={missing}, extra={extra}")


def _object(value: Any, *, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{where} must be an object")
    return value


def _string(value: Any, *, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{where} must be a non-empty string")
    return value


def _strings(value: Any, *, where: str, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ContractError(f"{where} must be a{' non-empty' if nonempty else ''} string array")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ContractError(f"{where} must contain only non-empty strings")
    if len(set(value)) != len(value):
        raise ContractError(f"{where} contains duplicate values")
    return value


def _relative_path(value: Any, *, where: str, local_only: bool = False) -> str:
    raw = _string(value, where=where)
    if "\\" in raw:
        raise ContractError(f"{where} must use POSIX separators")
    parsed = PurePosixPath(raw)
    if parsed.is_absolute() or ".." in parsed.parts or raw in {".", "./"}:
        raise ContractError(f"{where} must be a normalized repository-relative path")
    normalized = str(parsed)
    if normalized != raw:
        raise ContractError(f"{where} must be normalized")
    if local_only and (not parsed.parts or parsed.parts[0] != ".local"):
        raise ContractError(f"{where} must be under ignored .local/")
    return raw


def _resource_id(value: Any, *, where: str) -> str:
    identity = _string(value, where=where)
    if (identity.strip().lower() in _BROAD_OWNERSHIP
            or not _SAFE_ID.fullmatch(identity)
            or ".." in PurePosixPath(identity).parts
            or "//" in identity):
        raise ContractError(f"{where} must identify one exact executor-owned resource")
    return identity


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_file(repo: Path, item: Any, *, where: str) -> dict[str, str]:
    record = _object(item, where=where)
    _keys(record, {"role", "path", "sha256"}, where=where)
    role = _string(record["role"], where=f"{where}.role")
    relative = _relative_path(record["path"], where=f"{where}.path")
    digest = _string(record["sha256"], where=f"{where}.sha256")
    if not _SHA256.fullmatch(digest):
        raise ContractError(f"{where}.sha256 must be lowercase SHA-256")

    root = repo.resolve(strict=True)
    candidate = repo / relative
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, ValueError) as exc:
        raise ContractError(f"{where}.path does not resolve to a file inside the repository") from exc
    if not resolved.is_file() or candidate.is_symlink():
        raise ContractError(f"{where}.path must be a regular, non-symlink file")
    observed = _sha256_file(resolved)
    if observed != digest:
        raise ContractError(
            f"{where}.sha256 mismatch for {relative}: expected {digest}, observed {observed}"
        )
    return {"role": role, "path": relative, "sha256": digest}


def _validate_source(value: Any) -> dict[str, Any]:
    source = _object(value, where="plan.source")
    _keys(source, {"frameworkCommit", "sutCommit", "dirty", "patchSha256"}, where="plan.source")
    for field in ("frameworkCommit", "sutCommit"):
        commit = _string(source[field], where=f"plan.source.{field}")
        if not _COMMIT.fullmatch(commit):
            raise ContractError(f"plan.source.{field} must be a lowercase 40-hex commit")
    if not isinstance(source["dirty"], bool):
        raise ContractError("plan.source.dirty must be boolean")
    patch = source["patchSha256"]
    if source["dirty"]:
        if not isinstance(patch, str) or not _SHA256.fullmatch(patch):
            raise ContractError("dirty source requires a lowercase patchSha256")
    elif patch is not None:
        raise ContractError("clean source must set patchSha256 to null")
    return dict(source)


def _validate_argv(value: Any, *, where: str) -> list[str]:
    argv = _strings(value, where=where)
    if any("\x00" in token or "\n" in token or "\r" in token for token in argv):
        raise ContractError(f"{where} contains a control character")
    if len(argv) >= 2 and Path(argv[0]).name in {"sh", "bash", "zsh"} and argv[1] == "-c":
        raise ContractError(f"{where} must delegate with argv, not a shell command string")
    return argv


def _validate_adapter(value: Any, experiment_inputs: list[dict[str, str]]) -> dict[str, Any]:
    adapter = _object(value, where="plan.adapter")
    _keys(
        adapter,
        {"entrypoint", "supportedPostures", "capabilities", "invocations"},
        where="plan.adapter",
    )
    entrypoint = _object(adapter["entrypoint"], where="plan.adapter.entrypoint")
    _keys(entrypoint, {"path", "sha256"}, where="plan.adapter.entrypoint")
    path = _relative_path(entrypoint["path"], where="plan.adapter.entrypoint.path")
    digest = _string(entrypoint["sha256"], where="plan.adapter.entrypoint.sha256")
    if not _SHA256.fullmatch(digest):
        raise ContractError("plan.adapter.entrypoint.sha256 must be lowercase SHA-256")
    matching = [
        item for item in experiment_inputs
        if item["role"] == "module-adapter" and item["path"] == path and item["sha256"] == digest
    ]
    if len(matching) != 1:
        raise ContractError("adapter entrypoint must match exactly one immutable module-adapter input")

    supported = _strings(adapter["supportedPostures"], where="plan.adapter.supportedPostures")
    capabilities = _strings(adapter["capabilities"], where="plan.adapter.capabilities")
    invocations_raw = adapter["invocations"]
    if not isinstance(invocations_raw, list) or not invocations_raw:
        raise ContractError("plan.adapter.invocations must be a non-empty array")

    invocations: list[dict[str, Any]] = []
    flattened: list[str] = []
    ids: set[str] = set()
    for index, raw in enumerate(invocations_raw):
        where = f"plan.adapter.invocations[{index}]"
        invocation = _object(raw, where=where)
        _keys(invocation, {"id", "phases", "argv", "receiptPhases"}, where=where)
        invocation_id = _string(invocation["id"], where=f"{where}.id")
        if not _SAFE_ID.fullmatch(invocation_id) or invocation_id in ids:
            raise ContractError(f"{where}.id must be unique and stable")
        ids.add(invocation_id)
        phases = _strings(invocation["phases"], where=f"{where}.phases")
        unknown = sorted(set(phases) - set(PHASE_ORDER))
        if unknown:
            raise ContractError(f"{where}.phases contains unknown phases: {unknown}")
        receipts = _strings(invocation["receiptPhases"], where=f"{where}.receiptPhases")
        if receipts != phases:
            raise ContractError(f"{where} must promise one receipt for every covered phase")
        flattened.extend(phases)
        invocations.append(
            {"id": invocation_id, "phases": phases,
             "argv": _validate_argv(invocation["argv"], where=f"{where}.argv"),
             "receiptPhases": receipts}
        )
    if tuple(flattened) != PHASE_ORDER:
        raise ContractError("adapter invocations must cover the lifecycle once, in canonical order")
    return {
        "entrypoint": {"path": path, "sha256": digest},
        "supportedPostures": supported,
        "capabilities": capabilities,
        "invocations": invocations,
    }


def _validate_backend(value: Any) -> dict[str, Any]:
    backend = _object(value, where="backend")
    _keys(
        backend,
        {
            "schemaVersion", "backend", "transport", "capabilities", "phaseContract",
            "receiptContract", "cleanupContract", "delegation",
        },
        where="backend",
    )
    if backend["schemaVersion"] != 1:
        raise ContractError("backend.schemaVersion must equal 1")
    name = _string(backend["backend"], where="backend.backend")
    transport = _string(backend["transport"], where="backend.transport")
    capabilities = _strings(backend["capabilities"], where="backend.capabilities")
    phases = _strings(backend["phaseContract"], where="backend.phaseContract")
    if tuple(phases) != PHASE_ORDER:
        raise ContractError("backend.phaseContract must equal the canonical lifecycle")

    receipt = _object(backend["receiptContract"], where="backend.receiptContract")
    _keys(receipt, {"schemaPath", "perPhase", "immutableFinalManifest"}, where="backend.receiptContract")
    if receipt != {
        "schemaPath": "contracts/execution-receipt.schema.json",
        "perPhase": True,
        "immutableFinalManifest": True,
    }:
        raise ContractError("backend receipt contract must require canonical per-phase receipts")

    cleanup = _object(backend["cleanupContract"], where="backend.cleanupContract")
    _keys(
        cleanup,
        {"allowedOwnershipKinds", "allowWholeHost", "joinBeforeTeardown", "evidenceRequired"},
        where="backend.cleanupContract",
    )
    kinds = _strings(cleanup["allowedOwnershipKinds"], where="backend.cleanupContract.allowedOwnershipKinds")
    if cleanup["allowWholeHost"] is not False:
        raise ContractError("backend cleanup must prohibit whole-host ownership")
    if cleanup["joinBeforeTeardown"] is not True:
        raise ContractError("backend cleanup must join cancellation before teardown")
    if cleanup["evidenceRequired"] is not True:
        raise ContractError("backend cleanup must require evidence")

    delegation = _object(backend["delegation"], where="backend.delegation")
    _keys(delegation, {"adapterCommands", "argvOnly", "sutBranches"}, where="backend.delegation")
    if delegation != {"adapterCommands": True, "argvOnly": True, "sutBranches": False}:
        raise ContractError("backend must be argv-only, adapter-delegating, and SUT-neutral")
    return {
        "schemaVersion": 1,
        "backend": name,
        "transport": transport,
        "capabilities": capabilities,
        "phaseContract": phases,
        "receiptContract": dict(receipt),
        "cleanupContract": {
            "allowedOwnershipKinds": kinds,
            "allowWholeHost": False,
            "joinBeforeTeardown": True,
            "evidenceRequired": True,
        },
        "delegation": dict(delegation),
    }


def validate_plan(plan_value: Any, backend_value: Any, repo: Path) -> dict[str, Any]:
    """Validate and normalize a plan without executing any command."""
    plan = _object(plan_value, where="plan")
    _keys(
        plan,
        {
            "schemaVersion", "runId", "module", "backend", "target", "source", "requested",
            "requiredCapabilities", "immutableInputs", "adapter", "receiptContract", "cleanup",
        },
        where="plan",
    )
    if plan["schemaVersion"] != 1:
        raise ContractError("plan.schemaVersion must equal 1")
    run_id = _string(plan["runId"], where="plan.runId")
    if not _SAFE_ID.fullmatch(run_id):
        raise ContractError("plan.runId must be a stable identifier")
    module = _string(plan["module"], where="plan.module")
    backend_name = _string(plan["backend"], where="plan.backend")
    target = _string(plan["target"], where="plan.target")
    source = _validate_source(plan["source"])

    requested = _object(plan["requested"], where="plan.requested")
    _keys(requested, {"campaign", "goal", "postures"}, where="plan.requested")
    normalized_requested = {
        "campaign": _string(requested["campaign"], where="plan.requested.campaign"),
        "goal": _string(requested["goal"], where="plan.requested.goal"),
        "postures": _strings(requested["postures"], where="plan.requested.postures"),
    }
    required_capabilities = _strings(
        plan["requiredCapabilities"], where="plan.requiredCapabilities"
    )

    immutable = _object(plan["immutableInputs"], where="plan.immutableInputs")
    _keys(immutable, {"experiment", "executor"}, where="plan.immutableInputs")
    normalized_inputs: dict[str, list[dict[str, str]]] = {}
    all_paths: set[str] = set()
    for group in ("experiment", "executor"):
        raw_items = immutable[group]
        if not isinstance(raw_items, list) or not raw_items:
            raise ContractError(f"plan.immutableInputs.{group} must be a non-empty array")
        items = [
            _verified_file(repo, item, where=f"plan.immutableInputs.{group}[{index}]")
            for index, item in enumerate(raw_items)
        ]
        for item in items:
            if item["path"] in all_paths:
                raise ContractError("immutable input paths must be unique across groups")
            all_paths.add(item["path"])
        normalized_inputs[group] = items

    adapter = _validate_adapter(plan["adapter"], normalized_inputs["experiment"])
    unsupported_postures = sorted(
        set(normalized_requested["postures"]) - set(adapter["supportedPostures"])
    )
    if unsupported_postures:
        raise ContractError(f"adapter does not support requested postures: {unsupported_postures}")

    backend = _validate_backend(backend_value)
    if backend_name != backend["backend"]:
        raise ContractError("plan.backend does not match backend descriptor")
    missing_adapter = sorted(set(required_capabilities) - set(adapter["capabilities"]))
    missing_backend = sorted(set(required_capabilities) - set(backend["capabilities"]))
    if missing_adapter or missing_backend:
        raise ContractError(
            f"unsupported required capabilities; adapter={missing_adapter}, backend={missing_backend}"
        )

    receipt = _object(plan["receiptContract"], where="plan.receiptContract")
    _keys(
        receipt,
        {"schemaPath", "schemaSha256", "perPhase", "immutableFinalManifest", "outputRoot"},
        where="plan.receiptContract",
    )
    schema_path = _relative_path(receipt["schemaPath"], where="plan.receiptContract.schemaPath")
    schema_digest = _string(receipt["schemaSha256"], where="plan.receiptContract.schemaSha256")
    if schema_path != backend["receiptContract"]["schemaPath"]:
        raise ContractError("plan and backend receipt schema paths differ")
    verified_schema = _verified_file(
        repo,
        {"role": "receipt-schema", "path": schema_path, "sha256": schema_digest},
        where="plan.receiptContract",
    )
    if receipt["perPhase"] is not True or receipt["immutableFinalManifest"] is not True:
        raise ContractError("plan must require per-phase receipts and an immutable final manifest")
    output_root = _relative_path(
        receipt["outputRoot"], where="plan.receiptContract.outputRoot", local_only=True
    )

    cleanup = _object(plan["cleanup"], where="plan.cleanup")
    _keys(
        cleanup,
        {"ownership", "allowWholeHost", "cancelJoin", "evidencePath"},
        where="plan.cleanup",
    )
    if cleanup["allowWholeHost"] is not False:
        raise ContractError("plan cleanup cannot claim whole-host ownership")
    ownership_raw = cleanup["ownership"]
    if not isinstance(ownership_raw, list) or not ownership_raw:
        raise ContractError("plan.cleanup.ownership must identify at least one exact resource")
    ownership: list[dict[str, str]] = []
    seen_ownership: set[tuple[str, str]] = set()
    allowed_kinds = set(backend["cleanupContract"]["allowedOwnershipKinds"])
    for index, raw in enumerate(ownership_raw):
        where = f"plan.cleanup.ownership[{index}]"
        item = _object(raw, where=where)
        _keys(item, {"kind", "id"}, where=where)
        kind = _string(item["kind"], where=f"{where}.kind")
        identity = _resource_id(item["id"], where=f"{where}.id")
        if kind not in allowed_kinds:
            raise ContractError(f"{where}.kind is not allowed by backend")
        pair = (kind, identity)
        if pair in seen_ownership:
            raise ContractError("plan.cleanup.ownership contains a duplicate")
        seen_ownership.add(pair)
        ownership.append({"kind": kind, "id": identity})

    cancel = _object(cleanup["cancelJoin"], where="plan.cleanup.cancelJoin")
    _keys(cancel, {"mode", "argv", "evidenceRequired"}, where="plan.cleanup.cancelJoin")
    mode = _string(cancel["mode"], where="plan.cleanup.cancelJoin.mode")
    if mode not in {"argv", "adapter-internal"}:
        raise ContractError("plan.cleanup.cancelJoin.mode must be argv or adapter-internal")
    if cancel["evidenceRequired"] is not True:
        raise ContractError("cancellation/join evidence is required")
    if mode == "argv":
        cancel_argv = _validate_argv(cancel["argv"], where="plan.cleanup.cancelJoin.argv")
    else:
        if cancel["argv"] != []:
            raise ContractError("adapter-internal cancellation must not provide external argv")
        cancel_argv = []
    evidence_path = _relative_path(
        cleanup["evidencePath"], where="plan.cleanup.evidencePath", local_only=True
    )
    if not (evidence_path == output_root or evidence_path.startswith(output_root.rstrip("/") + "/")):
        raise ContractError("cleanup evidence must be inside the receipt output root")

    return {
        "schemaVersion": 1,
        "runId": run_id,
        "module": module,
        "backend": backend_name,
        "transport": backend["transport"],
        "target": target,
        "source": source,
        "requested": normalized_requested,
        "requiredCapabilities": required_capabilities,
        "immutableInputs": normalized_inputs,
        "adapter": adapter,
        "phaseContract": list(PHASE_ORDER),
        "receiptContract": {
            "schemaPath": verified_schema["path"],
            "schemaSha256": verified_schema["sha256"],
            "perPhase": True,
            "immutableFinalManifest": True,
            "outputRoot": output_root,
        },
        "cleanup": {
            "ownership": ownership,
            "allowWholeHost": False,
            "cancelJoin": {"mode": mode, "argv": cancel_argv, "evidenceRequired": True},
            "evidencePath": evidence_path,
        },
    }


def render_plan(plan_value: Any, backend_value: Any, repo: Path) -> dict[str, Any]:
    """Render a deterministic, non-executing orchestration description."""
    plan = validate_plan(plan_value, backend_value, repo)
    steps: list[dict[str, Any]] = []
    cancel_emitted = False
    for invocation in plan["adapter"]["invocations"]:
        if "teardown" in invocation["phases"] and not cancel_emitted:
            steps.append(
                {
                    "kind": "cancel-join-boundary",
                    "mode": plan["cleanup"]["cancelJoin"]["mode"],
                    "argv": plan["cleanup"]["cancelJoin"]["argv"],
                    "evidenceRequired": True,
                    "mustCompleteBefore": "teardown",
                }
            )
            cancel_emitted = True
        steps.append(
            {
                "kind": "adapter-invocation",
                "id": invocation["id"],
                "phases": invocation["phases"],
                "argv": invocation["argv"],
                "receiptPhases": invocation["receiptPhases"],
            }
        )
    if not cancel_emitted:  # defensive; full phase coverage should make this unreachable
        raise ContractError("rendered plan has no cancellation boundary before teardown")
    return {
        "schemaVersion": 1,
        "mode": "render-only",
        "runId": plan["runId"],
        "module": plan["module"],
        "backend": plan["backend"],
        "transport": plan["transport"],
        "target": plan["target"],
        "phaseContract": plan["phaseContract"],
        "steps": steps,
        "immutableInputs": plan["immutableInputs"],
        "receiptContract": plan["receiptContract"],
        "cleanup": plan["cleanup"],
    }


def equivalence_fingerprint(plan_value: Any, backend_value: Any, repo: Path) -> dict[str, Any]:
    """Fingerprint executor-neutral inputs; this is not proof of runtime equivalence."""
    plan = validate_plan(plan_value, backend_value, repo)
    payload = {
        "schemaVersion": 1,
        "module": plan["module"],
        "source": plan["source"],
        "requested": plan["requested"],
        "requiredCapabilities": plan["requiredCapabilities"],
        "experimentInputs": plan["immutableInputs"]["experiment"],
        "adapterEntrypoint": plan["adapter"]["entrypoint"],
        "adapterPhaseCoverage": [item["phases"] for item in plan["adapter"]["invocations"]],
        "phaseContract": plan["phaseContract"],
        "receiptSchema": {
            "path": plan["receiptContract"]["schemaPath"],
            "sha256": plan["receiptContract"]["schemaSha256"],
            "perPhase": True,
            "immutableFinalManifest": True,
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "inputs": payload}


def compare_plans(
    left_plan: Any,
    left_backend: Any,
    right_plan: Any,
    right_backend: Any,
    repo: Path,
) -> dict[str, Any]:
    left = equivalence_fingerprint(left_plan, left_backend, repo)
    right = equivalence_fingerprint(right_plan, right_backend, repo)
    return {
        "equivalent": left["sha256"] == right["sha256"],
        "claimBoundary": (
            "Executor-neutral input and receipt-contract equivalence only; this does not prove "
            "runtime, host, transport, telemetry, or scientific equivalence."
        ),
        "left": left,
        "right": right,
    }


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read strict JSON from {path}: {exc}") from exc


def load_repo_json(repo: Path, path: Path, *, where: str) -> Any:
    """Read a CLI input only when it is a regular file inside the supplied repo."""
    if path.is_absolute() or ".." in path.parts:
        raise ContractError(f"{where} must be a repository-relative path")
    try:
        root = repo.resolve(strict=True)
        candidate = (root / path).resolve(strict=True)
        candidate.relative_to(root)
    except (FileNotFoundError, ValueError) as exc:
        raise ContractError(f"{where} must resolve inside the repository") from exc
    if not candidate.is_file() or (root / path).is_symlink():
        raise ContractError(f"{where} must be a regular, non-symlink file")
    return load_json(candidate)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "render"):
        command = sub.add_parser(name)
        command.add_argument("--repo", type=Path, default=Path.cwd())
        command.add_argument("--plan", type=Path, required=True)
        command.add_argument("--backend", type=Path, required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--repo", type=Path, default=Path.cwd())
    compare.add_argument("--left-plan", type=Path, required=True)
    compare.add_argument("--left-backend", type=Path, required=True)
    compare.add_argument("--right-plan", type=Path, required=True)
    compare.add_argument("--right-backend", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            normalized = validate_plan(
                load_repo_json(args.repo, args.plan, where="plan"),
                load_repo_json(args.repo, args.backend, where="backend"), args.repo)
            result: Any = {"valid": True, "normalized": normalized}
        elif args.command == "render":
            result = render_plan(
                load_repo_json(args.repo, args.plan, where="plan"),
                load_repo_json(args.repo, args.backend, where="backend"), args.repo)
        else:
            result = compare_plans(
                load_repo_json(args.repo, args.left_plan, where="left plan"),
                load_repo_json(args.repo, args.left_backend, where="left backend"),
                load_repo_json(args.repo, args.right_plan, where="right plan"),
                load_repo_json(args.repo, args.right_backend, where="right backend"), args.repo,
            )
    except ContractError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
