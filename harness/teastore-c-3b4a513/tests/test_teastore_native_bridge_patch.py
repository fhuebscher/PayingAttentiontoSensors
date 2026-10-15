import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).parents[1]
V1_PATCH = ROOT / "modules/teastore/witness/teastore-app-witness-v1.patch"
V1_MANIFEST = ROOT / "modules/teastore/witness/patch-manifest.json"
V2_PATCH = ROOT / "modules/teastore/witness/teastore-app-witness-v2.patch"
V2_MANIFEST = ROOT / "modules/teastore/witness/patch-manifest-v2.json"
V3_PATCH = ROOT / "modules/teastore/witness/teastore-app-witness-v3.patch"
V3_MANIFEST = ROOT / "modules/teastore/witness/patch-manifest-v3.json"
AOP_RELATIVE = "utilities/tools.descartes.teastore.dockerbase/aop.xml"
AOP_OVERLAY = "/usr/local/tomcat/lib/aop.xml"
WITNESS_PACKAGE = "tools.descartes.teastore.registryclient.observability"
WITNESS_EXCLUDE = f'<exclude within="{WITNESS_PACKAGE}..*" />'
STOCK_AOP = ROOT / "upstream/teastore" / AOP_RELATIVE
KIEKER_JAR = (
    ROOT / "upstream/teastore/utilities/tools.descartes.teastore.dockerbase/"
    "kieker-2.0.0-aspectj.jar"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _patched_aop_xml(tmp_path: Path) -> str:
    """Apply only the aop.xml section of v3 to the pinned stock file."""
    staged = tmp_path / AOP_RELATIVE
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(STOCK_AOP, staged)
    subprocess.run(
        [
            "git", "apply", "--ignore-space-change", f"--include={AOP_RELATIVE}",
            str(V3_PATCH),
        ],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    )
    return staged.read_text(encoding="utf-8")


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


def test_v2_history_is_unchanged_and_v3_is_source_bound():
    manifest = json.loads(V3_MANIFEST.read_text(encoding="utf-8"))

    assert _sha(V2_PATCH) == "c6fbb755ba9f572f4df2197e78eee22f7e2e9768fb8106654a5a79dc08d0bfff"
    assert _sha(V2_MANIFEST) == "ea69ed052bed5fca02c78a796bd9a2fa4cfed221a30e2eefea132cfb7eb5f2df"
    assert _sha(V3_PATCH) == manifest["patch"]["sha256"]
    assert manifest["schemaVersion"] == 3
    assert manifest["predecessor"]["patchSha256"] == _sha(V2_PATCH)
    assert manifest["predecessor"]["manifestSha256"] == _sha(V2_MANIFEST)
    assert manifest["source"]["commit"] == "34b37f7e7be433ce72d5f9455e66922a13116749"
    assert manifest["patch"]["applyOptions"] == ["--ignore-space-change"]
    assert AOP_RELATIVE in manifest["patchedPaths"]


def test_v3_applies_to_the_exact_pinned_source_without_mutating_it():
    source = ROOT / "upstream/teastore"
    before = subprocess.run(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"],
        check=True, capture_output=True, text=True,
    ).stdout
    result = subprocess.run(
        [
            "git", "-C", str(source), "apply", "--check", "--ignore-space-change",
            str(V3_PATCH),
        ],
        check=False, capture_output=True, text=True,
    )
    after = subprocess.run(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"],
        check=True, capture_output=True, text=True,
    ).stdout

    assert result.returncode == 0, result.stderr
    assert before == after == ""


def test_v3_is_v2_plus_only_the_weaving_exclusion():
    """F-ADH-071: v3 changes nothing but the AspectJ weaving configuration."""
    v2 = V2_PATCH.read_text(encoding="utf-8")
    v3 = V3_PATCH.read_text(encoding="utf-8")
    section_header = f"diff --git a/{AOP_RELATIVE} b/{AOP_RELATIVE}\n"

    assert section_header in v3
    aop_section = v3.split(section_header, 1)[1].split("diff --git ", 1)[0]
    assert v3.replace(section_header + aop_section, "") == v2
    added = [line[1:] for line in aop_section.splitlines() if line.startswith("+++") is False
             and line.startswith("+")]
    assert [line.strip() for line in added] == [WITNESS_EXCLUDE]


def test_patched_aop_xml_excludes_the_witness_package_from_sut_weaving(tmp_path):
    """The framework witness helper must never be woven by the SUT (F-ADH-071)."""
    stock = STOCK_AOP.read_text(encoding="utf-8")
    patched = _patched_aop_xml(tmp_path)

    # The stock configuration weaves the whole application, including our helper.
    assert '<include within="tools.descartes.teastore..*" />' in stock
    assert WITNESS_PACKAGE not in stock

    weaver = patched.split("<weaver", 1)[1].split("</weaver>", 1)[0]
    assert WITNESS_EXCLUDE in weaver
    # It sits with the other registryclient excludes, inside the weaver element.
    assert '<exclude within="tools.descartes.teastore.registryclient.loadbalancers..*" />' in weaver
    assert patched.count(WITNESS_EXCLUDE) == 1
    assert patched.replace(f"\t\t{WITNESS_EXCLUDE}\n", "") == stock


def test_patched_images_overlay_the_patched_aop_over_the_woven_path():
    """The base images bake the stock aop.xml, so each Dockerfile must overwrite it."""
    overlay = f"COPY {AOP_RELATIVE} {AOP_OVERLAY}"
    for service in ("auth", "persistence", "webui"):
        text = (ROOT / f"modules/teastore/images/Dockerfile.{service}").read_text(
            encoding="utf-8"
        )
        lines = text.splitlines()
        assert overlay in lines
        war = next(line for line in lines if line.startswith("COPY services/"))
        assert lines.index(war) < lines.index(overlay)
        assert f"LABEL org.observability-placement.patch.sha256={_sha(V3_PATCH)}" in lines

    # The selected posture bind-mounts its own configuration over the same path,
    # which is what keeps that posture unaffected by this overlay.
    override = (
        ROOT / "modules/teastore/postures/auth-subset.override.yaml"
    ).read_text(encoding="utf-8")
    assert f":{AOP_OVERLAY}:ro" in override
    subset = (ROOT / "modules/teastore/postures/auth-subset.aop.xml").read_text(
        encoding="utf-8"
    )
    assert '<include within="tools.descartes.teastore.auth..*" />' in subset
    assert WITNESS_PACKAGE not in subset


def test_manifest_kieker_api_binding_matches_the_pinned_jar_and_java_11():
    manifest = json.loads(V3_MANIFEST.read_text(encoding="utf-8"))
    api = manifest["kiekerApiVerification"]

    assert _sha(KIEKER_JAR) == api["jarSha256"]
    assert api["javaTarget"] == 11
    assert api["javaCompilationClaim"] is False
    with zipfile.ZipFile(KIEKER_JAR) as archive:
        names = set(archive.namelist())
    assert "kieker/monitoring/core/controller/MonitoringController.class" in names
    assert "kieker/monitoring/core/registry/ControlFlowRegistry.class" in names
