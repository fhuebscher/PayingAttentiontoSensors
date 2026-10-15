#!/usr/bin/env python3
"""Validate the TeaStore construction epoch without weakening OpenSpec v1.

The validator reads no executable command from Markdown or JSON.  Git queries,
the candidate compiler import, and every checked path are code-owned.  A pass is
local construction evidence only: runtime and promotion always remain false.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, NoReturn

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


ROOT = Path(__file__).resolve().parents[1]
CHANGE_ID = "adopt-teastore-diagnostic-harness"
CHANGE_ROOT = ROOT / "openspec" / "changes" / CHANGE_ID
MANIFEST_PATH = CHANGE_ROOT / "governance.json"
SCHEMA_PATH = ROOT / "contracts" / "science-construction-control.schema.json"
PARENT_COMMIT = "b331aa4d365d7d41accc7d7cf1c20904fab2f622"
PARENT_TREE = "998aaba29c8ba43f5f3929aacd9b235ff51b9028"
SOURCE_COMMIT = "b4a6e053afbd9d2de322e2df6ad43e847a20979a"
SOURCE_TREE = "fcc1efeb266bf5d351a9f6381eb698ed59d4b57c"
DESCRIPTOR_BYTE_SHA256 = "742a9b0f625e1aea7eb87198b53d7d8a6ff3818cb6dbb3a88512a8cca31d4921"
DESCRIPTOR_CANONICAL_SHA256 = "5dcb633f0c0c38255b911779afb8e1737cb87925d76ab0a60a2e9ae382778320"
PLAN_CANONICAL_SHA256 = "de436f23a0f5bc21913025e574bdfe28260161767924d4f8000f65de424b1b94"
CHECK_IDS = (
    "construction-schema",
    "parent-epoch",
    "source-bindings",
    "delivery-ownership",
    "protocol-bindings",
    "observation-ceiling",
    "artifact-completeness",
    "gate-boundary",
)
EXPECTED_OBSERVATIONS = [
    {
        "campaignId": "canddiag-20260829-1813",
        "terminalStatus": "pass",
        "manifestSha256": "8c3bdeded3ada824b2c51509680dd3db46eafee02674b95863062dad1f549f05",
        "qualification": "diagnostic-only",
        "canonical": False,
        "candidateCellEligible": False,
    },
    {
        "campaignId": "canddiag-effect-20260829-1854",
        "terminalStatus": "blocked",
        "manifestSha256": "77abd456856673858e138be3c0b635707afcb1bfdaaf8d8126634a761195c8ae",
        "qualification": "diagnostic-only",
        "canonical": False,
        "candidateCellEligible": False,
    },
    {
        "campaignId": "canddiag-effect2-20260829-1931",
        "terminalStatus": "pass",
        "manifestSha256": "bf1e42e37062c076ba775eaa401c4f69e7126919a18fdf5eded5828e9da5c37b",
        "qualification": "diagnostic-only",
        "canonical": False,
        "candidateCellEligible": False,
    },
]
EXPECTED_PERMISSIONS = {
    "runtimeAllowed": False,
    "externalMutationAllowed": False,
    "heldOutOutcomeAccessAllowed": False,
    "aiSelectorAllowed": False,
    "evidencePromotionAllowed": False,
}
EXPECTED_CHECKPOINTS = [
    {"id": "GATE-PLAN", "scope": "plan-approval", "status": "pending", "decisionBinding": None},
    {"id": "GATE-RUN", "scope": "run-authorization", "status": "not-requested", "decisionBinding": None},
    {"id": "GATE-PROMOTION", "scope": "evidence-promotion", "status": "not-requested", "decisionBinding": None},
]
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
HEX_COMMIT = re.compile(r"^[0-9a-f]{40}$")
FINDING_ID = re.compile(r"^F-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
FINDINGS_HEADER = (
    "finding_id",
    "change_id",
    "reviewer_context",
    "classification",
    "severity",
    "status",
    "artifact_path",
    "summary",
    "evidence",
    "disposition",
)


class DuplicateKeyError(ValueError):
    """Reject ambiguous JSON members."""


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise DuplicateKeyError(f"duplicate JSON member: {key}")
        value[key] = item
    return value


def _constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number: {value}")


def load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_pairs,
        parse_constant=_constant,
    )


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _canonical_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or value.endswith("/"):
        raise ValueError(f"not an exact repository file: {value!r}")
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or pure.as_posix() != value
        or any(part in {"", ".", ".."} for part in pure.parts)
        or "\\" in value
        or "//" in value
        or "\x00" in value
    ):
        raise ValueError(f"not a canonical repository file: {value!r}")
    return value


def _safe_file(root: Path, relative: Any) -> Path:
    canonical = _canonical_relative(relative)
    current = root.resolve()
    for part in PurePosixPath(canonical).parts:
        current = current / part
        try:
            observed = current.lstat()
        except FileNotFoundError as exc:
            raise ValueError(f"missing repository file: {canonical}") from exc
        if stat.S_ISLNK(observed.st_mode):
            raise ValueError(f"repository path contains a symlink: {canonical}")
    resolved = current.resolve()
    if root.resolve() not in resolved.parents or not current.is_file():
        raise ValueError(f"repository file escapes root: {canonical}")
    return current


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    with tempfile.TemporaryDirectory(prefix="construction-git-home-") as raw:
        return subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env={
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
                "HOME": raw,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_NO_REPLACE_OBJECTS": "1",
            },
        )


@dataclass(frozen=True)
class Check:
    check_id: str
    errors: tuple[str, ...]

    @property
    def status(self) -> str:
        return "pass" if not self.errors else "fail"

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.check_id, "status": self.status, "diagnostics": list(self.errors)}


def check_schema(root: Path, manifest: dict[str, Any]) -> Check:
    errors: list[str] = []
    try:
        schema = load_json(root / "contracts" / "science-construction-control.schema.json")
        Draft202012Validator.check_schema(schema)
        for error in sorted(
            Draft202012Validator(schema).iter_errors(manifest),
            key=lambda item: list(item.absolute_path),
        ):
            location = ".".join(str(part) for part in error.absolute_path) or "$"
            errors.append(f"{location}: {error.message}")
    except (OSError, ValueError, json.JSONDecodeError, DuplicateKeyError, SchemaError) as exc:
        errors.append(f"construction schema unavailable or invalid: {exc}")
    return Check("construction-schema", tuple(errors))


def check_parent(root: Path, manifest: dict[str, Any]) -> Check:
    errors: list[str] = []
    if manifest.get("parentEpoch") != {
        "changeId": "teastore-candidate-pilot-freeze",
        "commit": PARENT_COMMIT,
        "tree": PARENT_TREE,
    }:
        errors.append("parent epoch differs from reviewed b331aa4 freeze")
    if manifest.get("adoptedSource") != {
        "kind": "diagnostic-harness",
        "commit": SOURCE_COMMIT,
        "tree": SOURCE_TREE,
        "qualification": "diagnostic-only",
    }:
        errors.append("adopted source differs from diagnostic harness b4a6e05")
    for commit, expected_tree in ((PARENT_COMMIT, PARENT_TREE), (SOURCE_COMMIT, SOURCE_TREE)):
        observed = _git(root, "show", "-s", "--format=%T", commit)
        if observed.returncode != 0:
            errors.append(f"source commit unavailable: {commit}")
        elif observed.stdout.decode().strip() != expected_tree:
            errors.append(f"source tree mismatch: {commit}")
    ancestor = _git(root, "merge-base", "--is-ancestor", PARENT_COMMIT, "HEAD")
    if ancestor.returncode not in {0, 1}:
        errors.append("cannot establish parent ancestry")
    elif ancestor.returncode == 1:
        errors.append("reviewed parent is not an ancestor of HEAD")
    return Check("parent-epoch", tuple(errors))


def check_sources(root: Path, manifest: dict[str, Any]) -> Check:
    errors: list[str] = []
    bindings = manifest.get("sourceBindings")
    if not isinstance(bindings, list) or not bindings:
        return Check("source-bindings", ("sourceBindings is empty",))
    seen: set[tuple[str, str]] = set()
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            errors.append(f"binding {index} is not an object")
            continue
        relative = binding.get("path")
        commit = binding.get("sourceCommit")
        declared = binding.get("sha256")
        try:
            canonical = _canonical_relative(relative)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        identity = (str(commit), canonical)
        if identity in seen:
            errors.append(f"duplicate source binding: {identity}")
        seen.add(identity)
        if commit not in {PARENT_COMMIT, SOURCE_COMMIT}:
            errors.append(f"unreviewed source commit for {canonical}")
            continue
        if not isinstance(declared, str) or not HEX_SHA256.fullmatch(declared):
            errors.append(f"invalid source digest for {canonical}")
            continue
        result = _git(root, "show", f"{commit}:{canonical}")
        if result.returncode != 0:
            errors.append(f"source path absent at {commit}: {canonical}")
        elif sha256_bytes(result.stdout) != declared:
            errors.append(f"source digest mismatch at {commit}: {canonical}")
    return Check("source-bindings", tuple(errors))


def _nul_paths(result: subprocess.CompletedProcess[bytes]) -> set[str]:
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return {item.decode("utf-8") for item in result.stdout.split(b"\0") if item}


def changed_paths(root: Path, base_commit: str) -> set[str]:
    paths: set[str] = set()
    commands = (
        ("diff", "--name-only", "-z", f"{base_commit}..HEAD", "--"),
        ("diff", "--name-only", "-z", "--cached", "--"),
        ("diff", "--name-only", "-z", "--"),
        ("ls-files", "--others", "--exclude-standard", "-z", "--"),
    )
    for command in commands:
        paths.update(_nul_paths(_git(root, *command)))
    return paths


def delivery_errors(observed: set[str], allowed_value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(allowed_value, list):
        return ["pathOwnership.allowed is not a list"]
    allowed: set[str] = set()
    for item in allowed_value:
        try:
            allowed.add(_canonical_relative(item))
        except ValueError as exc:
            errors.append(str(exc))
    unknown = sorted(observed - allowed)
    unused = sorted(allowed - observed)
    if unknown:
        errors.append(f"changed paths lack exact ownership: {unknown}")
    if unused:
        errors.append(f"declared ownership exceeds the actual delivery: {unused}")
    if any(item.startswith((".local/", "upstream/")) for item in observed):
        errors.append("delivery overlaps forbidden local evidence or upstream source")
    return errors


def check_delivery(
    root: Path, manifest: dict[str, Any], delivery_base_commit: str = PARENT_COMMIT
) -> Check:
    errors: list[str] = []
    ownership = manifest.get("pathOwnership")
    if not HEX_COMMIT.fullmatch(delivery_base_commit):
        return Check("delivery-ownership", ("trusted delivery base is not a full commit",))
    if not isinstance(ownership, dict) or ownership.get("baseCommit") != delivery_base_commit:
        return Check(
            "delivery-ownership",
            ("path ownership does not bind the root-routed delivery base",),
        )
    try:
        observed = changed_paths(root, delivery_base_commit)
    except (RuntimeError, UnicodeError) as exc:
        errors.append(f"cannot enumerate delivery: {exc}")
        observed = set()
    errors.extend(delivery_errors(observed, ownership.get("allowed")))
    return Check("delivery-ownership", tuple(errors))


def _candidate_module(root: Path):
    source = root / "modules" / "teastore" / "execution" / "candidate_pilot.py"
    spec = importlib.util.spec_from_file_location("construction_candidate_pilot", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("candidate compiler cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_protocol(
    root: Path,
    manifest: dict[str, Any],
    expected_module_sha256: str | None = None,
) -> Check:
    errors: list[str] = []
    expected = {
        "studyEpoch": "teastore-candidate-pilot-v1",
        "descriptor": {
            "id": "teastore-candidate-pilot-v1",
            "path": "pipelines/campaigns/teastore-candidate-pilot-v1.json",
            "byteSha256": DESCRIPTOR_BYTE_SHA256,
            "canonicalSha256": DESCRIPTOR_CANONICAL_SHA256,
        },
        "compiledPlan": {
            "canonicalSha256": PLAN_CANONICAL_SHA256,
            "runCount": 27,
            "timedSeconds": 19440,
            "operationalUpperSeconds": 28800,
        },
        "maximumFutureRunEvidenceLabel": "candidate-evidence",
        "canonical": False,
    }
    if manifest.get("protocolBindings") != expected:
        errors.append("protocol binding envelope differs from reviewed values")
    try:
        module_path = _safe_file(
            root, "modules/teastore/execution/candidate_pilot.py"
        )
        if (
            not isinstance(expected_module_sha256, str)
            or not HEX_SHA256.fullmatch(expected_module_sha256)
        ):
            raise RuntimeError("root-routed protocol module digest is unavailable")
        if sha256_file(module_path) != expected_module_sha256:
            raise RuntimeError("protocol module bytes differ from the root-owned pin")
        descriptor_path = _safe_file(root, expected["descriptor"]["path"])
        if sha256_file(descriptor_path) != DESCRIPTOR_BYTE_SHA256:
            errors.append("candidate descriptor byte digest differs")
        module = _candidate_module(root)
        descriptor = module.strict_json_file(descriptor_path)
        module.validate_descriptor(descriptor)
        if module.canonical_sha256(descriptor) != DESCRIPTOR_CANONICAL_SHA256:
            errors.append("candidate descriptor canonical digest differs")
        plan = module.compile_plan(descriptor)
        if module.canonical_sha256(plan) != PLAN_CANONICAL_SHA256:
            errors.append("compiled plan canonical digest differs")
        if plan.get("runCount") != 27 or plan.get("minimumTimedSeconds") != 19440:
            errors.append("compiled plan population or timing differs")
        flattened = [
            cell
            for regime in plan["regimeRoots"]
            for block in regime["blocks"]
            for cell in block["cells"]
        ]
        if len(flattened) != 27 or len({item["runId"] for item in flattened}) != 27:
            errors.append("compiled plan does not have 27 unique run IDs")
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        errors.append(f"candidate protocol cannot be replayed: {exc}")
    return Check("protocol-bindings", tuple(errors))


def check_observations(_root: Path, manifest: dict[str, Any]) -> Check:
    errors: list[str] = []
    if manifest.get("diagnosticObservations") != EXPECTED_OBSERVATIONS:
        errors.append("diagnostic observation identities or ceilings differ")
    if manifest.get("claimCeiling") != "diagnostic-harness-adoption":
        errors.append("adoption claim ceiling differs")
    return Check("observation-ceiling", tuple(errors))


def findings_errors(root: Path, relative: str) -> list[str]:
    """Validate the successor ledger with the root-owned v1 vocabulary."""

    errors: list[str] = []
    try:
        path = _safe_file(root, relative)
        rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"), newline=""), strict=True))
    except (OSError, UnicodeDecodeError, ValueError, csv.Error) as exc:
        return [f"cannot read findings ledger: {exc}"]
    if not rows or tuple(rows[0]) != FINDINGS_HEADER:
        return ["findings ledger header differs from the root-owned vocabulary"]
    seen: set[str] = set()
    for row_number, row in enumerate(rows[1:], start=2):
        if len(row) != len(FINDINGS_HEADER):
            errors.append(f"findings row {row_number} has {len(row)} fields")
            continue
        record = dict(zip(FINDINGS_HEADER, row, strict=True))
        if any(not value or value != value.strip() for value in record.values()):
            errors.append(f"findings row {row_number} has an empty or untrimmed field")
        if any(value.startswith(("=", "+", "-", "@")) for value in record.values()):
            errors.append(f"findings row {row_number} has spreadsheet-active content")
        finding_id = record["finding_id"]
        if not FINDING_ID.fullmatch(finding_id):
            errors.append(f"invalid finding id on row {row_number}")
        if finding_id in seen:
            errors.append(f"duplicate finding id: {finding_id}")
        seen.add(finding_id)
        if record["change_id"] != CHANGE_ID:
            errors.append(f"findings row {row_number} names another change")
        if record["reviewer_context"] not in {"separate-instance", "fresh-subagent", "human"}:
            errors.append(f"invalid reviewer_context on row {row_number}")
        if record["classification"] not in {"DECISION", "RECORD"}:
            errors.append(f"invalid classification on row {row_number}")
        if record["severity"] not in {"blocker", "major", "minor", "note"}:
            errors.append(f"invalid severity on row {row_number}")
        if record["status"] not in {"open", "resolved", "accepted-risk", "not-applicable"}:
            errors.append(f"invalid status on row {row_number}")
        try:
            _safe_file(root, record["artifact_path"])
        except (OSError, ValueError) as exc:
            errors.append(f"invalid artifact_path on row {row_number}: {exc}")
    return errors


def check_artifacts(root: Path, manifest: dict[str, Any]) -> Check:
    errors: list[str] = []
    expected = {
        f"openspec/changes/{CHANGE_ID}/.openspec.yaml",
        f"openspec/changes/{CHANGE_ID}/proposal.md",
        f"openspec/changes/{CHANGE_ID}/authority.md",
        f"openspec/changes/{CHANGE_ID}/design.md",
        f"openspec/changes/{CHANGE_ID}/tasks.md",
        f"openspec/changes/{CHANGE_ID}/verification.md",
        f"openspec/changes/{CHANGE_ID}/governance.json",
        f"openspec/changes/{CHANGE_ID}/specs/{CHANGE_ID}/spec.md",
        f"findings/{CHANGE_ID}.csv",
    }
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return Check("artifact-completeness", ("artifacts is not an object",))
    declared: set[str] = set()
    for key, value in artifacts.items():
        values = value if key == "specs" and isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str):
                declared.add(item)
    declared.add(f"openspec/changes/{CHANGE_ID}/.openspec.yaml")
    if declared != expected:
        errors.append(f"artifact set differs: missing={sorted(expected-declared)}, unknown={sorted(declared-expected)}")
    for relative in sorted(expected):
        try:
            item = _safe_file(root, relative)
            if item.stat().st_size == 0:
                errors.append(f"artifact is empty: {relative}")
        except ValueError as exc:
            errors.append(str(exc))
    errors.extend(findings_errors(root, f"findings/{CHANGE_ID}.csv"))
    return Check("artifact-completeness", tuple(errors))


def check_gates(_root: Path, manifest: dict[str, Any]) -> Check:
    errors: list[str] = []
    if manifest.get("permissions") != EXPECTED_PERMISSIONS:
        errors.append("every dangerous permission must remain false")
    if manifest.get("humanCheckpoints") != EXPECTED_CHECKPOINTS:
        errors.append("construction child cannot self-authorize a human gate")
    if manifest.get("checkIds") != list(CHECK_IDS):
        errors.append("construction check registry differs")
    verification = manifest.get("verification")
    if verification != {
        "status": "not-run",
        "independentReviewerRequired": True,
        "reportBinding": None,
    }:
        errors.append("construction child cannot self-assert review completion")
    return Check("gate-boundary", tuple(errors))


CHECKS: tuple[Callable[[Path, dict[str, Any]], Check], ...] = (
    check_schema,
    check_parent,
    check_sources,
    check_delivery,
    check_protocol,
    check_observations,
    check_artifacts,
    check_gates,
)


def validate_repository(
    root: Path = ROOT,
    *,
    delivery_base_commit: str = PARENT_COMMIT,
    protocol_module_sha256: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    try:
        manifest = load_json(root / "openspec" / "changes" / CHANGE_ID / "governance.json")
        if not isinstance(manifest, dict):
            raise ValueError("governance manifest is not an object")
    except (OSError, ValueError, json.JSONDecodeError, DuplicateKeyError) as exc:
        errors.append(f"cannot parse construction governance: {exc}")
        manifest = {}
    results = [
        check_delivery(root, manifest, delivery_base_commit)
        if function is check_delivery
        else check_protocol(root, manifest, protocol_module_sha256)
        if function is check_protocol
        else function(root, manifest)
        for function in CHECKS
    ]
    if errors:
        results[0] = Check(results[0].check_id, tuple((*errors, *results[0].errors)))
    status = "pass" if all(item.status == "pass" for item in results) else "fail"
    return {
        "schemaVersion": 2,
        "status": status,
        "constructionControlValid": status == "pass",
        "runtimeAuthorized": False,
        "promotionEligible": False,
        "changeId": CHANGE_ID,
        "checks": [item.as_dict() for item in results],
        "claimBoundary": (
            "Local construction lineage and deterministic protocol checks only; "
            "no SSH, runtime, candidate evidence, canonical qualification, or promotion."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args()
    report = validate_repository(arguments.root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
