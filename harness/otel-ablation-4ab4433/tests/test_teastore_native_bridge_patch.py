import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).parents[1]
V1_PATCH = ROOT / "modules/teastore/witness/teastore-app-witness-v1.patch"
V1_MANIFEST = ROOT / "modules/teastore/witness/patch-manifest.json"
V2_PATCH = ROOT / "modules/teastore/witness/teastore-app-witness-v2.patch"
V2_MANIFEST = ROOT / "modules/teastore/witness/patch-manifest-v2.json"
KIEKER_JAR = (
    ROOT / "upstream/teastore/utilities/tools.descartes.teastore.dockerbase/"
    "kieker-2.0.0-aspectj.jar"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v1_history_is_unchanged_and_v2_is_source_bound():
    manifest = json.loads(V2_MANIFEST.read_text(encoding="utf-8"))

    assert _sha(V1_PATCH) == "0694a442eb992b5c415416982aea344502a87d79544af8950555494f58916fac"
    assert _sha(V1_MANIFEST) == "7254bb68f05d62af65cbbf14ba93e8421d736078ac8d39aba7837f5bd876fcfb"
    assert _sha(V2_PATCH) == manifest["patch"]["sha256"]
    assert manifest["predecessor"]["patchSha256"] == _sha(V1_PATCH)
    assert manifest["predecessor"]["manifestSha256"] == _sha(V1_MANIFEST)
    assert manifest["source"]["commit"] == "34b37f7e7be433ce72d5f9455e66922a13116749"
    assert manifest["patch"]["applyOptions"] == ["--ignore-space-change"]


def test_v2_patch_is_auth_only_for_native_bridge_and_has_no_parameter_logging():
    patch = V2_PATCH.read_text(encoding="utf-8")
    auth_section, persistence_section = patch.split(
        "diff --git a/services/tools.descartes.teastore.persistence", 1)
    observability_section = patch.split(
        "diff --git a/utilities/tools.descartes.teastore.registryclient/src/main/java/"
        "tools/descartes/teastore/registryclient/observability/ObservabilityJourney.java",
        1,
    )[1].split("diff --git ", 1)[0]

    assert "ObservabilityJourney.emitNativeTraceBridge(LOG, token);" in auth_section
    assert auth_section.index("String token = ObservabilityJourney.validToken") < auth_section.index(
        "ObservabilityJourney.emitNativeTraceBridge") < auth_section.index(
        "LoadBalancedCRUDOperations.getEntityWithProperties")
    assert "emitNativeTraceBridge" not in persistence_section.split("diff --git ", 1)[0]
    assert "ControlFlowRegistry.INSTANCE.recallThreadLocalTraceId()" in observability_section
    assert "MonitoringController.getInstance().isMonitoringEnabled()" in observability_section
    assert "nativeTraceId == -1L" in observability_section
    assert "OBSERVABILITY_NATIVE_TRACE_BRIDGE " in observability_section
    assert '"service\\":\\"auth\\"}' in observability_section
    assert "LOG_PARAMETERS" not in patch


def test_v2_patch_applies_to_the_exact_pinned_source_without_mutating_it():
    source = ROOT / "upstream/teastore"
    before = subprocess.run(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"],
        check=True, capture_output=True, text=True,
    ).stdout
    result = subprocess.run(
        [
            "git", "-C", str(source), "apply", "--check", "--ignore-space-change",
            str(V2_PATCH),
        ],
        check=False, capture_output=True, text=True,
    )
    after = subprocess.run(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"],
        check=True, capture_output=True, text=True,
    ).stdout

    assert result.returncode == 0, result.stderr
    assert before == after == ""


def test_manifest_kieker_api_binding_matches_the_pinned_jar_and_java_11():
    manifest = json.loads(V2_MANIFEST.read_text(encoding="utf-8"))
    api = manifest["kiekerApiVerification"]

    assert _sha(KIEKER_JAR) == api["jarSha256"]
    assert api["javaTarget"] == 11
    assert api["javaCompilationClaim"] is False
    with zipfile.ZipFile(KIEKER_JAR) as archive:
        names = set(archive.namelist())
    assert "kieker/monitoring/core/controller/MonitoringController.class" in names
    assert "kieker/monitoring/core/registry/ControlFlowRegistry.class" in names
