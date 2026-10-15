#!/usr/bin/env python3
"""Local-only validation for the frozen TeaStore witness-image inputs.

This module never invokes Maven, Docker, SSH, or a network client.  It proves
only facts available from repository bytes, built WAR bytes, a post-build image
lock, and a Compose override.  In particular, a passing lock/Compose binding is
not evidence that an image exists or contains the recorded WAR; Docker-side
inspection remains a separate runtime gate.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import struct
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import jsonschema
import yaml


ROOT = Path(__file__).parents[3]
DEFAULT_CONTRACT = Path("modules/teastore/images/patched-image-inputs.json")
LOCK_SCHEMA = Path("modules/teastore/images/patched-image-lock.schema.json")
PLATFORM = "linux/amd64"
SOURCE_COMMIT = "34b37f7e7be433ce72d5f9455e66922a13116749"
SOURCE_LOCK_SHA256 = "55a48c1ed866403d727dd235fbadee5c1faf827ab99b574a9a16c51da9f14048"
PATCH_SHA256 = "2199c0f6e9ab1098afcac3c6b5a68d7860ad1b94b70019d790862eb1a7d60094"
PATCH_MANIFEST_SHA256 = "94645d471331bdee9fabce89930276e828ad227dfc115e39492395a35e1ec0ee"
V2_PATCH_SHA256 = "c6fbb755ba9f572f4df2197e78eee22f7e2e9768fb8106654a5a79dc08d0bfff"
V2_PATCH_MANIFEST_SHA256 = "ea69ed052bed5fca02c78a796bd9a2fa4cfed221a30e2eefea132cfb7eb5f2df"
V1_PATCH_SHA256 = "0694a442eb992b5c415416982aea344502a87d79544af8950555494f58916fac"
V1_PATCH_MANIFEST_SHA256 = "7254bb68f05d62af65cbbf14ba93e8421d736078ac8d39aba7837f5bd876fcfb"
# The framework witness helper lives in this package; the system under test's own
# AspectJ weaving must never observe it, in any posture (F-ADH-071).
WITNESS_WEAVING_EXCLUDE_PACKAGE = "tools.descartes.teastore.registryclient.observability"
AOP_CONFIGURATION_PATH = "utilities/tools.descartes.teastore.dockerbase/aop.xml"
AOP_OVERLAY_PATH = "/usr/local/tomcat/lib/aop.xml"
KIEKER_JAR_SHA256 = "c3bf5b6b4ff7b765885cdef88507e73ab63cea7bd58562a2175d5a6f43fc6ff1"
REPOSITORY_DIGEST_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")

MAVEN_COMMAND = [
    "mvn",
    "-B",
    "-ntp",
    "-pl",
    (
        "utilities/tools.descartes.teastore.registryclient,"
        "services/tools.descartes.teastore.webui,"
        "services/tools.descartes.teastore.auth,"
        "services/tools.descartes.teastore.persistence"
    ),
    "-am",
    "clean",
    "verify",
]

SERVICE_INPUTS = {
    "auth": {
        "artifactPath": (
            "services/tools.descartes.teastore.auth/target/"
            "tools.descartes.teastore.auth.war"
        ),
        "dockerfilePath": "modules/teastore/images/Dockerfile.auth",
        "parentImage": (
            "descartesresearch/teastore-auth@sha256:"
            "1babe5ca10bda103daa03f52db3e2357e0d3ec32a9ed549c4b2e2020152b0dac"
        ),
        "outputRepository": "observability-placement/teastore-auth-witness",
        "overlayPath": "/usr/local/tomcat/webapps/tools.descartes.teastore.auth.war",
        "serviceClass": (
            "WEB-INF/classes/tools/descartes/teastore/auth/rest/"
            "AuthUserActionsRest.class"
        ),
        "requiredUtf8Markers": ["login-persistence-request", "emitNativeTraceBridge"],
    },
    "persistence": {
        "artifactPath": (
            "services/tools.descartes.teastore.persistence/target/"
            "tools.descartes.teastore.persistence.war"
        ),
        "dockerfilePath": "modules/teastore/images/Dockerfile.persistence",
        "parentImage": (
            "descartesresearch/teastore-persistence@sha256:"
            "ac6b0fe9aeca04ee31fea20caed0b49af2ddf709c28a2cf1f4b9b041af05279b"
        ),
        "outputRepository": "observability-placement/teastore-persistence-witness",
        "overlayPath": (
            "/usr/local/tomcat/webapps/tools.descartes.teastore.persistence.war"
        ),
        "serviceClass": (
            "WEB-INF/classes/tools/descartes/teastore/persistence/rest/"
            "UserEndpoint.class"
        ),
        "requiredUtf8Markers": ["login-user-lookup"],
    },
    "webui": {
        "artifactPath": (
            "services/tools.descartes.teastore.webui/target/"
            "tools.descartes.teastore.webui.war"
        ),
        "dockerfilePath": "modules/teastore/images/Dockerfile.webui",
        "parentImage": (
            "descartesresearch/teastore-webui@sha256:"
            "d0e490bd025167fefaf84d43f978c3c6d14fad9bf3cba9bc49ef902a0d106078"
        ),
        "outputRepository": "observability-placement/teastore-webui-witness",
        "overlayPath": "/usr/local/tomcat/webapps/tools.descartes.teastore.webui.war",
        "serviceClass": (
            "WEB-INF/classes/tools/descartes/teastore/webui/servlet/"
            "LoginActionServlet.class"
        ),
        "requiredUtf8Markers": ["X-Observability-Journey-Id"],
    },
}

REGISTRY_ENTRY = "WEB-INF/lib/registryclient-1.4.2.jar"
REGISTRY_CLASSES = [
    "tools/descartes/teastore/registryclient/observability/ObservabilityJourney.class",
    "tools/descartes/teastore/registryclient/rest/LoadBalancedCRUDOperations.class",
    "tools/descartes/teastore/registryclient/rest/LoadBalancedStoreOperations.class",
    "tools/descartes/teastore/registryclient/rest/NonBalancedCRUDOperations.class",
]
REGISTRY_MARKERS = [
    "OBSERVABILITY_APP_WITNESS ",
    "OBSERVABILITY_NATIVE_TRACE_BRIDGE ",
    "X-Observability-Journey-Id",
    "journey-[0-9a-f]{32}",
    "emitNativeTraceBridge",
    "kieker/monitoring/core/controller/MonitoringController",
    "kieker/monitoring/core/registry/ControlFlowRegistry",
]
PATCHED_PATHS = [
    (
        "services/tools.descartes.teastore.auth/src/main/java/"
        "tools/descartes/teastore/auth/rest/AuthUserActionsRest.java"
    ),
    (
        "services/tools.descartes.teastore.persistence/src/main/java/"
        "tools/descartes/teastore/persistence/rest/UserEndpoint.java"
    ),
    (
        "services/tools.descartes.teastore.webui/src/main/java/"
        "tools/descartes/teastore/webui/servlet/LoginActionServlet.java"
    ),
    AOP_CONFIGURATION_PATH,
    (
        "utilities/tools.descartes.teastore.registryclient/src/main/java/"
        "tools/descartes/teastore/registryclient/observability/ObservabilityJourney.java"
    ),
    (
        "utilities/tools.descartes.teastore.registryclient/src/main/java/"
        "tools/descartes/teastore/registryclient/rest/LoadBalancedCRUDOperations.java"
    ),
    (
        "utilities/tools.descartes.teastore.registryclient/src/main/java/"
        "tools/descartes/teastore/registryclient/rest/LoadBalancedStoreOperations.java"
    ),
    (
        "utilities/tools.descartes.teastore.registryclient/src/main/java/"
        "tools/descartes/teastore/registryclient/rest/NonBalancedCRUDOperations.java"
    ),
]


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: yaml.SafeLoader, node: yaml.Node, deep: bool = False):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ValueError("YAML mapping keys must be strings")
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ValueError("YAML mapping key is unhashable") from exc
        if duplicate:
            raise ValueError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping,
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_object_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON constant: {value}")),
    )


def _read_yaml(path: Path) -> Any:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)


def _keys(value: Any, expected: set[str], where: str, blockers: list[str]) -> bool:
    if not isinstance(value, dict):
        blockers.append(f"{where} is not an object")
        return False
    if set(value) != expected:
        blockers.append(f"{where} fields differ from the frozen contract")
        return False
    return True


def _record(blockers: list[str], condition: bool, message: str) -> None:
    if not condition:
        blockers.append(message)


class ClassFileError(ValueError):
    """A required classfile is truncated, malformed, or has the wrong identity."""


class _ClassReader:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0

    def take(self, size: int) -> bytes:
        if size < 0 or self.offset + size > len(self.payload):
            raise ClassFileError("truncated classfile")
        value = self.payload[self.offset:self.offset + size]
        self.offset += size
        return value

    def u1(self) -> int:
        return self.take(1)[0]

    def u2(self) -> int:
        return struct.unpack(">H", self.take(2))[0]

    def u4(self) -> int:
        return struct.unpack(">I", self.take(4))[0]


def _classfile_utf8(
    payload: bytes, expected_internal_name: str, *, expected_major: int | None = 55,
) -> set[bytes]:
    reader = _ClassReader(payload)
    if reader.take(4) != b"\xca\xfe\xba\xbe":
        raise ClassFileError("classfile magic differs")
    reader.u2()  # minor
    major = reader.u2()
    if expected_major is not None and major != expected_major:
        raise ClassFileError(
            f"classfile major version {major} differs from Java 11 ({expected_major})")
    count = reader.u2()
    if count < 5:
        raise ClassFileError("classfile constant pool is implausibly small")
    pool: list[tuple[int, Any] | None] = [None] * count
    index = 1
    while index < count:
        tag = reader.u1()
        if tag == 1:
            pool[index] = (tag, reader.take(reader.u2()))
        elif tag in {3, 4}:
            pool[index] = (tag, reader.take(4))
        elif tag in {5, 6}:
            if index + 1 >= count:
                raise ClassFileError("long/double constant lacks its reserved pool slot")
            pool[index] = (tag, reader.take(8))
            index += 1
            if index < count:
                pool[index] = None
        elif tag in {7, 8, 16, 19, 20}:
            pool[index] = (tag, reader.u2())
        elif tag in {9, 10, 11, 12, 17, 18}:
            pool[index] = (tag, (reader.u2(), reader.u2()))
        elif tag == 15:
            pool[index] = (tag, (reader.u1(), reader.u2()))
        else:
            raise ClassFileError(f"unknown constant-pool tag: {tag}")
        index += 1

    def entry(cp_index: int, tags: set[int], where: str) -> tuple[int, Any]:
        if not 0 < cp_index < count or pool[cp_index] is None:
            raise ClassFileError(f"{where} has an invalid constant-pool index")
        item = pool[cp_index]
        assert item is not None
        if item[0] not in tags:
            raise ClassFileError(f"{where} has the wrong constant-pool tag")
        return item

    for cp_index, item in enumerate(pool):
        if item is None:
            continue
        tag, value = item
        if tag in {7, 19, 20}:
            entry(value, {1}, f"constant-pool entry {cp_index}")
        elif tag in {8, 16}:
            entry(value, {1}, f"constant-pool entry {cp_index}")
        elif tag in {9, 10, 11}:
            entry(value[0], {7}, f"constant-pool entry {cp_index} class")
            entry(value[1], {12}, f"constant-pool entry {cp_index} name/type")
        elif tag == 12:
            entry(value[0], {1}, f"constant-pool entry {cp_index} name")
            entry(value[1], {1}, f"constant-pool entry {cp_index} descriptor")
        elif tag == 15:
            if not 1 <= value[0] <= 9:
                raise ClassFileError("method-handle reference kind is invalid")
            entry(value[1], {9, 10, 11}, f"constant-pool entry {cp_index} reference")
        elif tag in {17, 18}:
            entry(value[1], {12}, f"constant-pool entry {cp_index} name/type")

    reader.u2()  # access flags
    this_class = entry(reader.u2(), {7}, "this_class")
    super_index = reader.u2()
    if super_index:
        entry(super_index, {7}, "super_class")
    name_entry = entry(this_class[1], {1}, "this_class name")
    try:
        actual_name = name_entry[1].decode("ascii")
    except UnicodeError as exc:
        raise ClassFileError("this_class name is not ASCII") from exc
    if actual_name != expected_internal_name:
        raise ClassFileError(
            f"classfile identity {actual_name!r} differs from {expected_internal_name!r}")

    for _ in range(reader.u2()):
        entry(reader.u2(), {7}, "interface")

    def attributes() -> None:
        for _ in range(reader.u2()):
            entry(reader.u2(), {1}, "attribute name")
            reader.take(reader.u4())

    def members() -> None:
        for _ in range(reader.u2()):
            reader.u2()
            entry(reader.u2(), {1}, "member name")
            entry(reader.u2(), {1}, "member descriptor")
            attributes()

    members()  # fields
    members()  # methods
    attributes()
    if reader.offset != len(payload):
        raise ClassFileError("classfile has trailing bytes")
    return {item[1] for item in pool if item is not None and item[0] == 1}


def _require_class_markers(
    payload: bytes, class_path: str, markers: list[str], *, expected_major: int | None = 55,
) -> None:
    internal_name = class_path.removesuffix(".class")
    utf8 = _classfile_utf8(payload, internal_name, expected_major=expected_major)
    for marker in markers:
        encoded = marker.encode("utf-8")
        if not any(encoded in constant for constant in utf8):
            raise ClassFileError(f"class constant pool is missing marker: {marker}")


def expected_dockerfile(service: str) -> str:
    expected = SERVICE_INPUTS[service]
    return (
        f"FROM --platform={PLATFORM} {expected['parentImage']}\n"
        f"COPY {expected['artifactPath']} {expected['overlayPath']}\n"
        f"COPY {AOP_CONFIGURATION_PATH} {AOP_OVERLAY_PATH}\n"
        f"LABEL org.opencontainers.image.revision={SOURCE_COMMIT}\n"
        f"LABEL org.observability-placement.patch.sha256={PATCH_SHA256}\n"
        f"LABEL org.observability-placement.service={service}\n"
    )


def expected_source_preparation() -> dict[str, Any]:
    head = SOURCE_COMMIT + "\n"
    return {
        "strategy": "detached-git-worktree",
        "ephemeralPathPlaceholder": "<EPHEMERAL_SOURCE>",
        "patchPathPlaceholder": "<PATCH_FILE>",
        "placeholderRequirements": {
            "ephemeralSource": (
                "absolute non-existing child of a dedicated temporary directory; never the "
                "repository root, pinned checkout, or an ancestor of either"
            ),
            "patchFile": (
                "absolute resolved path of modules/teastore/witness/"
                "teastore-app-witness-v3.patch"
            ),
        },
        "preservePinnedCheckoutClean": True,
        "materializedByValidator": False,
        "networkAccessByValidator": False,
        "beforeBuild": [
            {
                "id": "verify-base-head",
                "argv": ["git", "-C", "upstream/teastore", "rev-parse", "HEAD"],
                "expectedExitCode": 0,
                "expectedStdout": head,
            },
            {
                "id": "verify-base-clean",
                "argv": [
                    "git", "-C", "upstream/teastore", "status", "--porcelain",
                    "--untracked-files=no",
                ],
                "expectedExitCode": 0,
                "expectedStdout": "",
            },
            {
                "id": "create-ephemeral-worktree",
                "argv": [
                    "git", "-C", "upstream/teastore", "worktree", "add", "--detach",
                    "<EPHEMERAL_SOURCE>", SOURCE_COMMIT,
                ],
                "expectedExitCode": 0,
            },
            {
                "id": "check-witness-patch",
                "argv": [
                    "git", "-C", "<EPHEMERAL_SOURCE>", "apply", "--check",
                    "--ignore-space-change", "<PATCH_FILE>",
                ],
                "expectedExitCode": 0,
            },
            {
                "id": "apply-witness-patch",
                "argv": [
                    "git", "-C", "<EPHEMERAL_SOURCE>", "apply", "--index",
                    "--ignore-space-change", "<PATCH_FILE>",
                ],
                "expectedExitCode": 0,
            },
            {
                "id": "verify-ephemeral-head",
                "argv": ["git", "-C", "<EPHEMERAL_SOURCE>", "rev-parse", "HEAD"],
                "expectedExitCode": 0,
                "expectedStdout": head,
            },
            {
                "id": "verify-patched-paths",
                "argv": [
                    "git", "-C", "<EPHEMERAL_SOURCE>", "diff", "--cached", "--name-only", "--",
                ],
                "expectedExitCode": 0,
                "expectedStdout": "".join(path + "\n" for path in PATCHED_PATHS),
            },
            {
                "id": "verify-no-unstaged-diff",
                "argv": ["git", "-C", "<EPHEMERAL_SOURCE>", "diff", "--quiet", "--"],
                "expectedExitCode": 0,
            },
        ],
        "buildRequiresCompletedStep": "verify-no-unstaged-diff",
        "ephemeralLifetime": (
            "retain through WAR validation and image construction; cleanup in an outer "
            "finally block"
        ),
        "cleanupFinally": [
            {
                "id": "remove-ephemeral-worktree",
                "argv": [
                    "git", "-C", "upstream/teastore", "worktree", "remove", "--force",
                    "<EPHEMERAL_SOURCE>",
                ],
                "expectedExitCode": 0,
            },
            {
                "id": "verify-base-head-after",
                "argv": ["git", "-C", "upstream/teastore", "rev-parse", "HEAD"],
                "expectedExitCode": 0,
                "expectedStdout": head,
            },
            {
                "id": "verify-base-clean-after",
                "argv": [
                    "git", "-C", "upstream/teastore", "status", "--porcelain",
                    "--untracked-files=no",
                ],
                "expectedExitCode": 0,
                "expectedStdout": "",
            },
        ],
    }


def dockerfile_blockers(service: str, text: str) -> list[str]:
    """Return fail-closed blockers for one overlay Dockerfile's exact bytes."""
    blockers: list[str] = []
    if service not in SERVICE_INPUTS:
        return [f"unknown service: {service}"]
    if text != expected_dockerfile(service):
        blockers.append(f"{service} Dockerfile differs from the frozen exact overlay")
    upper_lines = [line.strip().upper() for line in text.splitlines()]
    if any("*" in line or "?" in line for line in text.splitlines()):
        blockers.append(f"{service} Dockerfile contains a wildcard")
    if "HTTP://" in text.upper() or "HTTPS://" in text.upper():
        blockers.append(f"{service} Dockerfile contains a network URL")
    if any(line.startswith(("ADD ", "RUN ", "ARG ")) for line in upper_lines):
        blockers.append(f"{service} Dockerfile contains a forbidden build instruction")
    if "${" in text or "$(" in text or "`" in text:
        blockers.append(f"{service} Dockerfile contains substitution")
    from_lines = [line for line in text.splitlines() if line.upper().startswith("FROM ")]
    if len(from_lines) != 1 or SERVICE_INPUTS[service]["parentImage"] not in from_lines[0]:
        blockers.append(f"{service} parent is not the exact repository digest")
    return sorted(set(blockers))


def _contract_path(root: Path, contract_path: Path | None) -> Path:
    path = contract_path or DEFAULT_CONTRACT
    return path if path.is_absolute() else root / path


def validate_inputs(root: Path = ROOT, contract_path: Path | None = None) -> dict[str, Any]:
    """Validate frozen source, patch, tool command, and Dockerfile bytes locally."""
    root = root.resolve()
    path = _contract_path(root, contract_path)
    blockers: list[str] = []
    try:
        contract = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schema": "teastore.patched-image-input-report",
            "schemaVersion": 1,
            "outcome": "blocked",
            "runtimeReady": False,
            "blockers": [f"input contract is unreadable: {type(exc).__name__}: {exc}"],
        }
    if not isinstance(contract, dict):
        return {
            "schema": "teastore.patched-image-input-report",
            "schemaVersion": 1,
            "outcome": "blocked",
            "runtimeReady": False,
            "blockers": ["input contract is not an object"],
        }

    top_keys = {
        "schema", "schemaVersion", "claimCeiling", "platform", "source", "patch",
        "sourcePreparation", "toolchain", "kiekerApi", "registryClient", "services",
        "postBuild",
    }
    _keys(contract, top_keys, "input contract", blockers)
    _record(blockers, contract.get("schema") == "teastore.patched-image-inputs",
            "input schema differs")
    _record(blockers, contract.get("schemaVersion") == 2, "input schema version differs")
    _record(blockers, contract.get("claimCeiling") == "local-build-input-verification-only",
            "claim ceiling differs")
    _record(blockers, contract.get("platform") == PLATFORM, "platform differs from linux/amd64")

    source = contract.get("source")
    if _keys(source, {"repositoryPath", "commit", "sourceLockPath", "sourceLockSha256"},
             "source", blockers):
        _record(blockers, source["repositoryPath"] == "upstream/teastore",
                "source repository path differs")
        _record(blockers, source["commit"] == SOURCE_COMMIT, "source commit differs")
        _record(blockers, source["sourceLockPath"] == "modules/teastore/source.lock",
                "source lock path differs")
        _record(blockers, source["sourceLockSha256"] == SOURCE_LOCK_SHA256,
                "source lock digest differs")
        source_lock = root / source["sourceLockPath"]
        try:
            _record(blockers, _sha256(source_lock) == SOURCE_LOCK_SHA256,
                    "source lock bytes differ")
            lock = _read_yaml(source_lock)
            _record(blockers, isinstance(lock, dict) and lock.get("commit") == SOURCE_COMMIT,
                    "source lock commit differs")
        except (OSError, ValueError, yaml.YAMLError) as exc:
            blockers.append(f"source lock is unreadable: {type(exc).__name__}: {exc}")

    patch = contract.get("patch")
    if _keys(patch, {"manifestPath", "manifestSha256", "path", "sha256"},
             "patch", blockers):
        expected_patch = {
            "manifestPath": "modules/teastore/witness/patch-manifest-v3.json",
            "manifestSha256": PATCH_MANIFEST_SHA256,
            "path": "modules/teastore/witness/teastore-app-witness-v3.patch",
            "sha256": PATCH_SHA256,
        }
        _record(blockers, patch == expected_patch, "patch binding differs")
        manifest_path = root / patch["manifestPath"]
        patch_path = root / patch["path"]
        try:
            _record(blockers, _sha256(manifest_path) == PATCH_MANIFEST_SHA256,
                    "patch manifest bytes differ")
            manifest = _read_json(manifest_path)
            _record(blockers, manifest.get("source", {}).get("commit") == SOURCE_COMMIT,
                    "patch manifest source commit differs")
            _record(blockers, manifest.get("patch", {}).get("path") == patch["path"],
                    "patch manifest path differs")
            _record(blockers, manifest.get("patch", {}).get("sha256") == PATCH_SHA256,
                    "patch manifest digest differs")
            _record(blockers, manifest.get("schemaVersion") == 3,
                    "patch manifest version differs")
            _record(blockers, manifest.get("predecessor") == {
                "manifestPath": "modules/teastore/witness/patch-manifest-v2.json",
                "manifestSha256": V2_PATCH_MANIFEST_SHA256,
                "patchPath": "modules/teastore/witness/teastore-app-witness-v2.patch",
                "patchSha256": V2_PATCH_SHA256,
            }, "v2 patch predecessor binding differs")
            _record(blockers, _sha256(patch_path) == PATCH_SHA256, "patch bytes differ")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            blockers.append(f"patch binding is unreadable: {type(exc).__name__}: {exc}")

    source_preparation = contract.get("sourcePreparation")
    expected_preparation = expected_source_preparation()
    _record(blockers, source_preparation == expected_preparation,
            "source preparation sequence or arguments differ")
    if isinstance(source_preparation, dict):
        before_build = source_preparation.get("beforeBuild")
        ids = ([step.get("id") for step in before_build]
               if isinstance(before_build, list)
               and all(isinstance(step, dict) for step in before_build) else [])
        _record(blockers, ids == [step["id"] for step in expected_preparation["beforeBuild"]],
                "source preparation ordering differs")
        _record(blockers, ids.index("apply-witness-patch") < ids.index(
            "verify-no-unstaged-diff") if (
                "apply-witness-patch" in ids and "verify-no-unstaged-diff" in ids
            ) else False, "patch application is absent or not completed before build admission")

    toolchain = contract.get("toolchain")
    tool_keys = {
        "workingDirectory", "command", "executedByValidator", "networkAccessByValidator",
        "requiresCompletedPreparationStep", "reproducibleBuildClaim", "blocker",
    }
    if _keys(toolchain, tool_keys, "toolchain", blockers):
        _record(blockers, toolchain["workingDirectory"] == "<EPHEMERAL_SOURCE>",
                "Maven working directory differs")
        _record(blockers, toolchain["command"] == MAVEN_COMMAND, "Maven command differs")
        _record(blockers, toolchain["requiresCompletedPreparationStep"]
                == "verify-no-unstaged-diff",
                "Maven is not gated on completed patched-source preparation")
        _record(blockers, toolchain["executedByValidator"] is False,
                "validator must not execute Maven")
        _record(blockers, toolchain["networkAccessByValidator"] is False,
                "validator must not access the network")
        _record(blockers, toolchain["reproducibleBuildClaim"] is False,
                "unfrozen toolchain must not claim reproducibility")
        _record(blockers, toolchain["blocker"] == (
            "Maven wrapper, dependency closure, and build toolchain image are not frozen"),
            "toolchain blocker differs")

    kieker_api_expected = {
        "jarPath": (
            "upstream/teastore/utilities/tools.descartes.teastore.dockerbase/"
            "kieker-2.0.0-aspectj.jar"
        ),
        "jarSha256": KIEKER_JAR_SHA256,
        "javaTarget": 11,
        "imports": [
            "kieker.monitoring.core.controller.MonitoringController",
            "kieker.monitoring.core.registry.ControlFlowRegistry",
        ],
        "requiredMethods": [
            "getInstance", "isMonitoringEnabled", "recallThreadLocalTraceId",
        ],
        "verification": "read-only pinned-JAR classfile inspection",
        "javaCompilationClaim": False,
    }
    kieker_api = contract.get("kiekerApi")
    _record(blockers, kieker_api == kieker_api_expected, "Kieker API contract differs")
    if kieker_api == kieker_api_expected:
        try:
            jar_path = root / kieker_api["jarPath"]
            jar_bytes = jar_path.read_bytes()
            _record(blockers, _sha256_bytes(jar_bytes) == KIEKER_JAR_SHA256,
                    "pinned Kieker JAR digest differs")
            class_contracts = {
                (
                    "kieker/monitoring/core/controller/MonitoringController.class"
                ): ["getInstance", "isMonitoringEnabled"],
                (
                    "kieker/monitoring/core/registry/ControlFlowRegistry.class"
                ): ["recallThreadLocalTraceId"],
            }
            with zipfile.ZipFile(io.BytesIO(jar_bytes)) as kieker_jar:
                members = _zip_members(kieker_jar, "pinned Kieker JAR", blockers)
                for class_path, markers in class_contracts.items():
                    if class_path not in members:
                        blockers.append(f"pinned Kieker JAR is missing {class_path}")
                        continue
                    try:
                        _require_class_markers(
                            kieker_jar.read(class_path), class_path, markers,
                            expected_major=None,
                        )
                    except ClassFileError as exc:
                        blockers.append(f"pinned Kieker API class is invalid: {exc}")
            pom = (
                root
                / "upstream/teastore/utilities/tools.descartes.teastore.registryclient/pom.xml"
            ).read_text(encoding="utf-8")
            _record(blockers, "<maven.compiler.source>11</maven.compiler.source>" in pom
                    and "<maven.compiler.target>11</maven.compiler.target>" in pom,
                    "registryclient Java target differs from 11")
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            blockers.append(f"pinned Kieker API input is unreadable: {type(exc).__name__}: {exc}")

    registry = contract.get("registryClient")
    registry_expected = {
        "warEntry": REGISTRY_ENTRY,
        "expectedClasses": REGISTRY_CLASSES,
        "requiredUtf8Markers": REGISTRY_MARKERS,
    }
    _record(blockers, registry == registry_expected, "registryclient contract differs")

    services = contract.get("services")
    if not isinstance(services, dict) or set(services) != set(SERVICE_INPUTS):
        blockers.append("service set differs from auth/persistence/webui")
    else:
        for service, expected in SERVICE_INPUTS.items():
            _record(blockers, services.get(service) == expected,
                    f"{service} service input differs")
            parent = services[service].get("parentImage")
            _record(blockers, isinstance(parent, str) and REPOSITORY_DIGEST_RE.fullmatch(parent),
                    f"{service} parent is mutable or malformed")
            dockerfile = root / expected["dockerfilePath"]
            try:
                blockers.extend(dockerfile_blockers(
                    service, dockerfile.read_text(encoding="utf-8")))
            except OSError as exc:
                blockers.append(f"{service} Dockerfile is unreadable: {exc}")

    post_build = contract.get("postBuild")
    _record(blockers, post_build == {
        "lockSchema": "teastore.patched-image-lock",
        "composeOverridePolicy": "exact-repository-digest-and-platform-only",
        "dockerInspectionRequiredForRuntime": True,
    }, "post-build boundary differs")

    source_repo = root / "upstream/teastore"
    if source_repo.is_dir():
        try:
            head = subprocess.run(
                ["git", "-C", str(source_repo), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            _record(blockers, head == SOURCE_COMMIT, "checked-out TeaStore commit differs")
            status = subprocess.run(
                ["git", "-C", str(source_repo), "status", "--porcelain", "--untracked-files=no"],
                check=True, capture_output=True, text=True,
            ).stdout
            _record(blockers, status == "", "checked-out TeaStore tracked files are dirty")
            apply_check = subprocess.run(
                ["git", "-C", str(source_repo), "apply", "--check",
                 "--ignore-space-change",
                 str(root / "modules/teastore/witness/teastore-app-witness-v3.patch")],
                check=False, capture_output=True, text=True,
            )
            _record(blockers, apply_check.returncode == 0,
                    "witness patch does not apply cleanly to the checked-out source")
        except (OSError, subprocess.CalledProcessError) as exc:
            blockers.append(f"local source check failed: {type(exc).__name__}: {exc}")
    else:
        blockers.append("TeaStore source checkout is absent")

    blockers = sorted(set(blockers))
    return {
        "schema": "teastore.patched-image-input-report",
        "schemaVersion": 1,
        "outcome": "pass" if not blockers else "blocked",
        "claimCeiling": "local-build-input-verification-only",
        "runtimeReady": False,
        "toolchainFrozen": False,
        "contractSha256": _sha256(path),
        "platform": contract.get("platform"),
        "services": sorted(SERVICE_INPUTS),
        "blockers": blockers,
        "runtimeBoundary": (
            "No Maven, Docker, SSH, or network action was executed; image construction and "
            "Docker-side content/platform inspection remain required."
        ),
    }


def _zip_members(archive: zipfile.ZipFile, where: str, blockers: list[str]) -> set[str]:
    names = [entry.filename for entry in archive.infolist()]
    if len(names) != len(set(names)):
        blockers.append(f"{where} contains duplicate ZIP members")
    bad = archive.testzip()
    if bad is not None:
        blockers.append(f"{where} has a bad CRC member: {bad}")
    return set(names)


def validate_wars(
    artifact_root: Path,
    *,
    root: Path = ROOT,
    contract_path: Path | None = None,
) -> dict[str, Any]:
    """Validate exact WAR names, classes, and identical nested registryclient JARs."""
    root = root.resolve()
    artifact_root = artifact_root.resolve()
    path = _contract_path(root, contract_path)
    try:
        contract = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schema": "teastore.patched-war-report", "schemaVersion": 1,
            "outcome": "blocked", "blockers": [f"input contract is unreadable: {exc}"],
        }
    blockers: list[str] = []
    artifacts: dict[str, dict[str, Any]] = {}
    registry_digests: dict[str, str] = {}
    services = contract.get("services") if isinstance(contract, dict) else None
    registry = contract.get("registryClient") if isinstance(contract, dict) else None
    if services != SERVICE_INPUTS:
        blockers.append("service contract differs")
        services = SERVICE_INPUTS
    if registry != {
        "warEntry": REGISTRY_ENTRY,
        "expectedClasses": REGISTRY_CLASSES,
        "requiredUtf8Markers": REGISTRY_MARKERS,
    }:
        blockers.append("registryclient contract differs")

    for service, expected in SERVICE_INPUTS.items():
        artifact = artifact_root / expected["artifactPath"]
        try:
            artifact.resolve().relative_to(artifact_root)
        except ValueError:
            blockers.append(f"{service} artifact escapes the artifact root")
            continue
        if not artifact.is_file():
            blockers.append(f"{service} WAR is missing at the exact artifact path")
            continue
        try:
            registry_bytes: bytes | None = None
            service_logical = expected["serviceClass"].removeprefix("WEB-INF/classes/")
            required_logical = [service_logical, *REGISTRY_CLASSES]
            locations: dict[str, list[str]] = {name: [] for name in required_logical}
            payloads: dict[tuple[str, str], bytes] = {}
            with zipfile.ZipFile(artifact) as war:
                members = _zip_members(war, f"{service} WAR", blockers)
                registry_entries = sorted(
                    name for name in members
                    if name.startswith("WEB-INF/lib/") and "registryclient" in name
                )
                if registry_entries != [REGISTRY_ENTRY]:
                    blockers.append(f"{service} WAR registryclient entry differs")
                for logical in required_logical:
                    top_level = f"WEB-INF/classes/{logical}"
                    if top_level in members:
                        location = top_level
                        locations[logical].append(location)
                        payloads[(logical, location)] = war.read(top_level)
                for jar_entry in sorted(
                    name for name in members if name.startswith("WEB-INF/lib/")
                    and name.endswith(".jar")
                ):
                    jar_bytes = war.read(jar_entry)
                    if jar_entry == REGISTRY_ENTRY:
                        registry_bytes = jar_bytes
                    with zipfile.ZipFile(io.BytesIO(jar_bytes)) as nested:
                        nested_members = _zip_members(
                            nested, f"{service} nested JAR {jar_entry}", blockers)
                        for logical in required_logical:
                            if logical in nested_members:
                                location = f"{jar_entry}!/{logical}"
                                locations[logical].append(location)
                                payloads[(logical, location)] = nested.read(logical)

            expected_locations = {
                service_logical: expected["serviceClass"],
                **{
                    logical: f"{REGISTRY_ENTRY}!/{logical}"
                    for logical in REGISTRY_CLASSES
                },
            }
            for logical, expected_location in expected_locations.items():
                observed = locations[logical]
                if observed != [expected_location]:
                    blockers.append(
                        f"{service} required class is missing or shadowed: "
                        f"{logical} locations={observed}")
                    continue
                markers = (
                    expected["requiredUtf8Markers"] if logical == service_logical
                    else REGISTRY_MARKERS if logical == REGISTRY_CLASSES[0]
                    else []
                )
                try:
                    _require_class_markers(
                        payloads[(logical, expected_location)], logical, markers)
                except ClassFileError as exc:
                    blockers.append(f"{service} required class is invalid: {logical}: {exc}")

            if registry_bytes is not None:
                registry_digest = _sha256_bytes(registry_bytes)
                registry_digests[service] = registry_digest
                artifacts[service] = {
                    "path": expected["artifactPath"],
                    "sha256": _sha256(artifact),
                    "registryClientSha256": registry_digest,
                }
        except (OSError, zipfile.BadZipFile, RuntimeError, ClassFileError) as exc:
            blockers.append(f"{service} WAR is unreadable: {type(exc).__name__}: {exc}")

    common_digest = None
    if set(registry_digests) == set(SERVICE_INPUTS):
        values = set(registry_digests.values())
        if len(values) != 1:
            blockers.append("nested registryclient JAR bytes differ across the three WARs")
        else:
            common_digest = values.pop()
    blockers = sorted(set(blockers))
    return {
        "schema": "teastore.patched-war-report",
        "schemaVersion": 1,
        "outcome": "pass" if not blockers else "blocked",
        "artifactRoot": str(artifact_root),
        "artifacts": artifacts,
        "registryClientSha256": common_digest,
        "blockers": blockers,
    }


def validate_lock_and_compose(
    artifact_root: Path,
    image_lock_path: Path,
    compose_override_path: Path,
    *,
    root: Path = ROOT,
    contract_path: Path | None = None,
) -> dict[str, Any]:
    """Validate local lock/WAR/Compose consistency without asserting image existence."""
    root = root.resolve()
    contract_file = _contract_path(root, contract_path)
    blockers: list[str] = []
    input_report = validate_inputs(root, contract_file)
    if input_report.get("outcome") != "pass":
        blockers.extend(
            f"frozen image input: {blocker}"
            for blocker in input_report.get("blockers", ["input validation did not pass"])
        )
    try:
        contract = _read_json(contract_file)
        lock = _read_json(image_lock_path)
        if not isinstance(contract, dict):
            raise ValueError("input contract is not an object")
        if not isinstance(lock, dict):
            raise ValueError("image lock is not an object")
        schema = _read_json(root / LOCK_SCHEMA)
        jsonschema.Draft202012Validator.check_schema(schema)
        errors = sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(lock),
            key=lambda error: tuple(str(item) for item in error.absolute_path),
        )
        blockers.extend(
            "image lock schema: "
            + "/".join(str(item) for item in error.absolute_path)
            + (": " if error.absolute_path else "")
            + error.message
            for error in errors
        )
    except (OSError, ValueError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        return {
            "schema": "teastore.patched-image-binding-report", "schemaVersion": 1,
            "outcome": "blocked", "runtimeReady": False,
            "blockers": [f"binding input is unreadable: {type(exc).__name__}: {exc}"],
        }

    wars = validate_wars(
        artifact_root, root=root, contract_path=contract_file,
    )
    blockers.extend(wars["blockers"])

    _record(blockers, lock.get("inputContractSha256") == _sha256(contract_file),
            "image lock input-contract digest differs")
    _record(blockers, lock.get("platform") == PLATFORM, "image lock platform differs")
    _record(blockers, lock.get("sourceCommit") == SOURCE_COMMIT,
            "image lock source commit differs")
    _record(blockers, lock.get("patchSha256") == PATCH_SHA256,
            "image lock patch digest differs")
    _record(blockers, lock.get("registryClientSha256") == wars.get("registryClientSha256"),
            "image lock registryclient digest differs from WARs")

    locked_services = lock.get("services")
    if not isinstance(locked_services, dict) or set(locked_services) != set(SERVICE_INPUTS):
        blockers.append("image lock service set differs")
        locked_services = {}
    output_images: list[str] = []
    image_ids: list[str] = []
    for service, expected in SERVICE_INPUTS.items():
        row = locked_services.get(service)
        if not isinstance(row, dict):
            continue
        _record(blockers, row.get("parentImage") == expected["parentImage"],
                f"{service} locked parent image differs")
        _record(blockers, row.get("platform") == PLATFORM,
                f"{service} locked platform differs")
        _record(blockers, row.get("overlayPath") == expected["overlayPath"],
                f"{service} locked overlay path differs")
        artifact_row = wars.get("artifacts", {}).get(service, {})
        _record(blockers, row.get("artifactSha256") == artifact_row.get("sha256"),
                f"{service} locked WAR digest differs")
        try:
            dockerfile_sha256 = _sha256(root / expected["dockerfilePath"])
        except OSError as exc:
            blockers.append(f"{service} Dockerfile is unreadable: {exc}")
            dockerfile_sha256 = None
        _record(blockers, row.get("dockerfileSha256") == dockerfile_sha256,
                f"{service} locked Dockerfile digest differs")
        output = row.get("outputImage")
        _record(blockers, isinstance(output, str) and REPOSITORY_DIGEST_RE.fullmatch(output),
                f"{service} output image is mutable or malformed")
        if isinstance(output, str):
            output_images.append(output)
            _record(blockers, output.split("@", 1)[0] == expected["outputRepository"],
                    f"{service} output repository differs")
            _record(blockers, output != expected["parentImage"],
                    f"{service} output image aliases its parent")
        image_id = row.get("imageId")
        if isinstance(image_id, str):
            image_ids.append(image_id)
    _record(blockers, len(output_images) == len(set(output_images)),
            "output image digests are not unique by service")
    _record(blockers, len(image_ids) == len(set(image_ids)),
            "image IDs are not unique by service")

    try:
        compose = _read_yaml(compose_override_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        blockers.append(f"Compose override is unreadable: {type(exc).__name__}: {exc}")
        compose = None
    if not isinstance(compose, dict) or set(compose) != {"services"}:
        blockers.append("Compose override must contain only services")
    else:
        compose_services = compose.get("services")
        if not isinstance(compose_services, dict) or set(compose_services) != set(SERVICE_INPUTS):
            blockers.append("Compose override service set differs")
        else:
            for service in SERVICE_INPUTS:
                row = compose_services[service]
                if not isinstance(row, dict) or set(row) != {"image", "platform"}:
                    blockers.append(
                        f"{service} Compose override must contain only image and platform")
                    continue
                _record(blockers, row["platform"] == PLATFORM,
                        f"{service} Compose platform differs")
                locked_row = locked_services.get(service)
                if not isinstance(locked_row, dict):
                    locked_row = {}
                _record(blockers, row["image"] == locked_row.get("outputImage"),
                        f"{service} Compose image differs from the image lock")
                _record(blockers, isinstance(row["image"], str)
                        and REPOSITORY_DIGEST_RE.fullmatch(row["image"]),
                        f"{service} Compose image is mutable or malformed")

    blockers = sorted(set(blockers))
    return {
        "schema": "teastore.patched-image-binding-report",
        "schemaVersion": 1,
        "outcome": "pass" if not blockers else "blocked",
        "claimCeiling": "local-lock-and-compose-consistency-only",
        "runtimeReady": False,
        "provesImageExists": False,
        "provesImageContents": False,
        "platform": PLATFORM,
        "services": sorted(SERVICE_INPUTS),
        "blockers": blockers,
        "runtimeBoundary": (
            "Fresh Docker inspection must prove each child image ID, repository digest, "
            "linux/amd64 platform, digest-pinned parent, and overlaid WAR bytes before GATE-RUN."
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--contract", type=Path)
    subparsers = parser.add_subparsers(dest="stage", required=True)
    subparsers.add_parser("inputs")
    wars = subparsers.add_parser("wars")
    wars.add_argument("--artifact-root", type=Path, required=True)
    binding = subparsers.add_parser("binding")
    binding.add_argument("--artifact-root", type=Path, required=True)
    binding.add_argument("--image-lock", type=Path, required=True)
    binding.add_argument("--compose-override", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.stage == "inputs":
        report = validate_inputs(args.root, args.contract)
    elif args.stage == "wars":
        report = validate_wars(
            args.artifact_root, root=args.root, contract_path=args.contract,
        )
    else:
        report = validate_lock_and_compose(
            args.artifact_root, args.image_lock, args.compose_override,
            root=args.root, contract_path=args.contract,
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
