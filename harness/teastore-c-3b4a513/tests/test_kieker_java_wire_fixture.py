"""Independent real-writer wire fixture for the native Kieker parser.

The checked-in payload was emitted by a small Java fixture using the Kieker
writer from the TeaStore-pinned dependency, rather than by the Python fixture
builder under test.  It contains synthetic identifiers and the literal
``secret-redacted``; no retained application or credential data is present.
"""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/teastore/collectors/kieker_native.py"
SPEC = importlib.util.spec_from_file_location("kieker_native_java_fixture", MODULE)
kieker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(kieker)

FIXTURE = ROOT / "tests/fixtures/teastore-kieker-java-writer.b64"
GENERATOR = ROOT / "tests/fixtures/RealKiekerFixture.java"
PROVENANCE = ROOT / "tests/fixtures/teastore-kieker-java-writer.provenance.json"
FIXTURE_SHA256 = "cb88cc65b54285e56ea8135dad0b70020e8317e3abb9ddfd3049c818ed8c31cc"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _toolchain_version(command: str) -> str:
    completed = subprocess.run(
        [command, "-version"], cwd=ROOT, check=True, capture_output=True, text=True,
    )
    match = re.search(r"(?<![0-9])([0-9]+(?:\.[0-9]+){1,3})(?![0-9])",
                      completed.stdout + completed.stderr)
    assert match is not None, f"cannot normalize {command} -version output"
    return match.group(1)


def test_real_java_writer_fixture_has_reproducible_bound_provenance(tmp_path):
    provenance = json.loads(PROVENANCE.read_text())
    assert set(provenance) == {
        "schemaVersion", "generator", "inputs", "toolchain",
        "compileCommand", "runCommand", "output",
    }
    assert provenance["schemaVersion"] == 1
    assert provenance["generator"]["path"] == str(GENERATOR.relative_to(ROOT))
    assert _sha256(GENERATOR) == provenance["generator"]["sha256"]
    for item in provenance["inputs"]:
        assert _sha256(ROOT / item["path"]) == item["sha256"]
    assert _sha256(FIXTURE) == provenance["output"]["byteSha256"]

    if shutil.which("javac") is None or shutil.which("java") is None:
        pytest.skip("exact Java fixture reproduction requires java and javac")
    current_toolchain = {
        "javac": _toolchain_version("javac"),
        "java": _toolchain_version("java"),
    }
    if current_toolchain != provenance["toolchain"]:
        pytest.skip(
            "exact Java fixture reproduction requires recorded toolchain "
            f"{provenance['toolchain']}, found {current_toolchain}"
        )
    classes = tmp_path / "classes"
    classes.mkdir()
    compile_argv = [part.replace("{classes}", str(classes))
                    for part in provenance["compileCommand"]]
    subprocess.run(compile_argv, cwd=ROOT, check=True, capture_output=True, text=True)
    run_argv = [part.replace("{classes}", str(classes))
                for part in provenance["runCommand"]]
    completed = subprocess.run(
        run_argv, cwd=ROOT, check=True, capture_output=True, text=True,
    )
    assert completed.stdout.splitlines() == [
        "count=477 bytes=477", FIXTURE.read_text().strip(),
    ]


def test_real_java_writer_container_parses_with_exact_fields():
    body = base64.b64decode(FIXTURE.read_text().strip(), validate=True)
    provenance = json.loads(PROVENANCE.read_text())
    assert len(body) == provenance["output"]["decodedBytes"]
    assert hashlib.sha256(body).hexdigest() == FIXTURE_SHA256
    assert FIXTURE_SHA256 == provenance["output"]["decodedSha256"]

    assert kieker.parse_container(body) == [
        {
            "_class": kieker.OER_CLASS,
            "_ok": True,
            "loggingTimestamp": -1,
            "operationSignature": (
                "public void tools.descartes.teastore.auth.A.login()"
            ),
            "sessionId": "sess",
            "traceId": 123,
            "tin": 1000,
            "tout": 2000,
            "hostname": "auth-host",
            "eoi": 0,
            "ess": 0,
        },
        {
            "_class": kieker.OEWPR_CLASS,
            "_ok": True,
            "loggingTimestamp": -1,
            "operationSignature": (
                "public boolean tools.descartes.teastore.auth.A.login("
                "java.lang.String)"
            ),
            "sessionId": "sess",
            "traceId": 123,
            "tin": 1100,
            "tout": 1900,
            "hostname": "auth-host",
            "eoi": 1,
            "ess": 1,
            "parameterTypes": ["java.lang.String"],
            "parameterValues": ["secret-redacted"],
            "returnType": "boolean",
            "returnValue": "true",
        },
    ]
