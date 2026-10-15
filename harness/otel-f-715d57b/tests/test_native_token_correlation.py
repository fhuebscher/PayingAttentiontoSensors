from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def _nested_secret_log(layers: int) -> str:
    value = '{"password":"planted-not-a-real-secret"}'
    for _ in range(layers):
        value = json.dumps(value)
    return "normal-log-prefix " + value + "\n"


def _load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


extractor = _load(
    "native_token_extractor_tests",
    "modules/teastore/witness/extract_native_token_correlation.py",
)
validator = _load(
    "native_token_validator_tests",
    "modules/teastore/validation/native_token_correlation.py",
)
fixture = _load(
    "native_token_candidate_fixture",
    "tests/test_candidate_pilot_evidence.py",
)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def test_retained_selected_mapping_replays_in_ledger_order(tmp_path: Path):
    root = fixture.make_run(tmp_path / "run", posture="selected")

    report = validator.validate_retained(root)
    rows = _json(root / "native-token-correlation.json")

    assert report["outcome"] == "pass", report["blockers"]
    assert len(rows) == 90
    assert [row["token"] for row in rows] == [
        f"journey-{index:032x}" for index in range(90)
    ]
    assert all(row["service"] == "auth" for row in rows)
    assert all(len(row["mappingId"]) == 64 for row in rows)


def test_none_posture_is_an_explicit_empty_mapping(tmp_path: Path):
    root = fixture.make_run(tmp_path / "run", posture="none")

    assert _json(root / "native-token-correlation.json") == []
    assert validator.validate_retained(root)["outcome"] == "pass"


def test_effect_mapping_excludes_the_unscored_fault_window(tmp_path: Path):
    root = fixture.make_run(
        tmp_path / "run", posture="selected", regime="auth-freeze-effect")

    rows = _json(root / "native-token-correlation.json")
    tokens = {row["token"] for row in rows}

    assert validator.validate_retained(root)["outcome"] == "pass"
    assert len(rows) == 67
    assert f"journey-{27:032x}" not in tokens
    assert f"journey-{50:032x}" in tokens


def test_selected_cost_extractor_rejects_a_missing_required_bridge(tmp_path: Path):
    root = fixture.make_run(tmp_path / "run", posture="selected")
    lines = (root / "auth.log").read_text().splitlines()
    removed = False
    retained = []
    for line in lines:
        if not removed and extractor.MARKER in line:
            removed = True
            continue
        retained.append(line)
    (root / "auth.log").write_text("\n".join(retained) + "\n")
    capture = _json(root / "service-log-capture.json")
    import hashlib
    capture["capturedLog"]["sha256"] = hashlib.sha256(
        (root / "auth.log").read_bytes()).hexdigest()
    _write(root / "service-log-capture.json", capture)
    (root / "native-token-correlation.json").unlink()
    (root / "native-token-correlation-extraction.json").unlink()

    with pytest.raises(extractor.CorrelationError, match="required scored tokens"):
        extractor.extract(
            auth_log=root / "auth.log",
            journey_ledger=root / "journey-ledger.jsonl",
            traces=root / "traces.json",
            run_receipt=root / "receipt.json",
            service_log_capture_receipt=root / "service-log-capture.json",
            output=root / "native-token-correlation.json",
            extraction_receipt=root / "native-token-correlation-extraction.json",
        )


def test_native_extractor_rejects_non_marker_secret_bearing_raw_text(tmp_path: Path):
    root = fixture.make_run(tmp_path / "run", posture="selected")
    (root / "native-token-correlation.json").unlink()
    (root / "native-token-correlation-extraction.json").unlink()
    (root / "auth.log").write_text(
        "Authorization: Bearer planted-not-a-real-token\n"
        + (root / "auth.log").read_text(),
        encoding="utf-8",
    )
    capture = _json(root / "service-log-capture.json")
    import hashlib
    capture["capturedLog"]["sha256"] = hashlib.sha256(
        (root / "auth.log").read_bytes()).hexdigest()
    _write(root / "service-log-capture.json", capture)

    with pytest.raises(extractor.CorrelationError, match="secret-bearing raw text"):
        extractor.extract(
            auth_log=root / "auth.log",
            journey_ledger=root / "journey-ledger.jsonl",
            traces=root / "traces.json",
            run_receipt=root / "receipt.json",
            service_log_capture_receipt=root / "service-log-capture.json",
            output=root / "native-token-correlation.json",
            extraction_receipt=root / "native-token-correlation-extraction.json",
        )


def test_native_extractor_rejects_quoted_json_secret_bearing_raw_text(tmp_path: Path):
    root = fixture.make_run(tmp_path / "run", posture="selected")
    (root / "native-token-correlation.json").unlink()
    (root / "native-token-correlation-extraction.json").unlink()
    (root / "auth.log").write_text(
        '{"password":"planted-not-a-real-secret"}\n'
        + (root / "auth.log").read_text(),
        encoding="utf-8",
    )
    capture = _json(root / "service-log-capture.json")
    import hashlib
    capture["capturedLog"]["sha256"] = hashlib.sha256(
        (root / "auth.log").read_bytes()).hexdigest()
    _write(root / "service-log-capture.json", capture)

    with pytest.raises(extractor.CorrelationError, match="secret-bearing raw text"):
        extractor.extract(
            auth_log=root / "auth.log",
            journey_ledger=root / "journey-ledger.jsonl",
            traces=root / "traces.json",
            run_receipt=root / "receipt.json",
            service_log_capture_receipt=root / "service-log-capture.json",
            output=root / "native-token-correlation.json",
            extraction_receipt=root / "native-token-correlation-extraction.json",
        )


@pytest.mark.parametrize("planted", [
    '{"pass\\u0077ord":"planted-not-a-real-secret"}\n',
    '{"message":"{\\"password\\":\\"planted-not-a-real-secret\\"}"}\n',
    'prefix {"password"\n : "planted-not-a-real-secret"}\n',
    "normal-log-prefix " + json.dumps(json.dumps(
        '{"pass\\u0077ord":"planted-not-a-real-secret"}')) + "\n",
    _nested_secret_log(10),
    'normal-log-prefix {"pass_word":"planted-not-a-real-secret"}\n',
    'normal-log-prefix {"db_password":"planted-not-a-real-secret"}\n',
    'normal-log-prefix {"_password_":"planted-not-a-real-secret"}\n',
    'normal-log-prefix {"paßword":"planted-not-a-real-secret"}\n',
])
def test_native_extractor_rejects_encoded_or_multiline_secret_text(
        tmp_path: Path, planted: str):
    root = fixture.make_run(tmp_path / "run", posture="selected")
    (root / "native-token-correlation.json").unlink()
    (root / "native-token-correlation-extraction.json").unlink()
    (root / "auth.log").write_text(
        planted + (root / "auth.log").read_text(), encoding="utf-8")
    capture = _json(root / "service-log-capture.json")
    import hashlib
    capture["capturedLog"]["sha256"] = hashlib.sha256(
        (root / "auth.log").read_bytes()).hexdigest()
    _write(root / "service-log-capture.json", capture)

    with pytest.raises(extractor.CorrelationError, match="secret-bearing raw text"):
        extractor.extract(
            auth_log=root / "auth.log",
            journey_ledger=root / "journey-ledger.jsonl",
            traces=root / "traces.json",
            run_receipt=root / "receipt.json",
            service_log_capture_receipt=root / "service-log-capture.json",
            output=root / "native-token-correlation.json",
            extraction_receipt=root / "native-token-correlation-extraction.json",
        )


def test_real_validator_cli_accepts_retained_fixture(tmp_path: Path, capsys):
    root = fixture.make_run(tmp_path / "run")

    result = validator.main([str(root)])

    assert result == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "pass"


@pytest.mark.parametrize(
    ("plant", "expected"),
    (
        ("duplicate-token", "one token maps more than once"),
        ("trace-shared-by-tokens", "one native trace maps to multiple tokens"),
        ("token-smuggling", "forbidden token fields"),
        ("synthetic-trace-id", "original Kieker provenance"),
        ("log-parameters-true", "LOG_PARAMETERS"),
        ("unscoped-log", "scope"),
    ),
)
def test_extractor_rejects_planted_bridge_provenance_and_capture_defects(
    tmp_path: Path, plant: str, expected: str,
):
    root = fixture.make_run(tmp_path / "run")
    (root / "native-token-correlation.json").unlink()
    (root / "native-token-correlation-extraction.json").unlink()
    if plant == "duplicate-token":
        first = next(
            line for line in (root / "auth.log").read_text().splitlines()
            if extractor.MARKER in line
        )
        with (root / "auth.log").open("a", encoding="utf-8") as stream:
            stream.write(first + "\n")
    elif plant == "trace-shared-by-tokens":
        lines = (root / "auth.log").read_text().splitlines()
        bridge_indexes = [i for i, line in enumerate(lines) if extractor.MARKER in line]
        first = json.loads(lines[bridge_indexes[0]].split(extractor.MARKER, 1)[1])
        second = json.loads(lines[bridge_indexes[1]].split(extractor.MARKER, 1)[1])
        second["nativeTraceId"] = first["nativeTraceId"]
        lines[bridge_indexes[1]] = extractor.MARKER + json.dumps(second)
        (root / "auth.log").write_text("\n".join(lines) + "\n")
    elif plant == "token-smuggling":
        traces = _json(root / "traces.json")
        traces[0]["opaqueToken"] = "journey-" + "0" * 32
        _write(root / "traces.json", traces)
    elif plant == "synthetic-trace-id":
        traces = _json(root / "traces.json")
        traces[0]["source"] = "scraper"
        _write(root / "traces.json", traces)
    else:
        capture = _json(root / "service-log-capture.json")
        if plant == "log-parameters-true":
            capture["logParameters"].update(
                state="true", rawValue="true", parameterLoggingEnabled=True)
        else:
            capture["capturedLog"]["scope"] = "container-lifetime"
        _write(root / "service-log-capture.json", capture)
    if plant in {"duplicate-token", "trace-shared-by-tokens"}:
        capture = _json(root / "service-log-capture.json")
        import hashlib
        capture["capturedLog"]["sha256"] = hashlib.sha256(
            (root / "auth.log").read_bytes()).hexdigest()
        _write(root / "service-log-capture.json", capture)

    with pytest.raises(extractor.CorrelationError, match=expected):
        extractor.extract(
            auth_log=root / "auth.log",
            journey_ledger=root / "journey-ledger.jsonl",
            traces=root / "traces.json",
            run_receipt=root / "receipt.json",
            service_log_capture_receipt=root / "service-log-capture.json",
            output=root / "native-token-correlation.json",
            extraction_receipt=root / "native-token-correlation-extraction.json",
        )


def test_extractor_cli_returns_nonzero_for_a_real_planted_defect(
    tmp_path: Path, capsys,
):
    root = fixture.make_run(tmp_path / "run")
    (root / "native-token-correlation.json").unlink()
    (root / "native-token-correlation-extraction.json").unlink()
    capture = _json(root / "service-log-capture.json")
    capture["logParameters"].update(
        state="true", rawValue="true", parameterLoggingEnabled=True)
    _write(root / "service-log-capture.json", capture)

    result = extractor.main([
        "--auth-log", str(root / "auth.log"),
        "--journey-ledger", str(root / "journey-ledger.jsonl"),
        "--traces", str(root / "traces.json"),
        "--run-receipt", str(root / "receipt.json"),
        "--service-log-capture-receipt", str(root / "service-log-capture.json"),
        "--output", str(root / "native-token-correlation.json"),
        "--extraction-receipt", str(root / "native-token-correlation-extraction.json"),
    ])

    assert result == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"


def test_extractor_script_process_returns_nonzero_for_a_planted_defect(
    tmp_path: Path,
):
    root = fixture.make_run(tmp_path / "run")
    (root / "native-token-correlation.json").unlink()
    (root / "native-token-correlation-extraction.json").unlink()
    capture = _json(root / "service-log-capture.json")
    capture["logParameters"].update(
        state="true", rawValue="true", parameterLoggingEnabled=True)
    _write(root / "service-log-capture.json", capture)

    result = subprocess.run([
        sys.executable,
        str(ROOT / "modules/teastore/witness/extract_native_token_correlation.py"),
        "--auth-log", str(root / "auth.log"),
        "--journey-ledger", str(root / "journey-ledger.jsonl"),
        "--traces", str(root / "traces.json"),
        "--run-receipt", str(root / "receipt.json"),
        "--service-log-capture-receipt", str(root / "service-log-capture.json"),
        "--output", str(root / "native-token-correlation.json"),
        "--extraction-receipt",
        str(root / "native-token-correlation-extraction.json"),
    ], check=False, capture_output=True, text=True)

    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "blocked"
    assert not (root / "native-token-correlation.json").exists()


def test_validator_cli_returns_nonzero_on_mapping_id_tampering(
    tmp_path: Path, capsys,
):
    root = fixture.make_run(tmp_path / "run")
    rows = _json(root / "native-token-correlation.json")
    rows[0]["mappingId"] = "0" * 64
    _write(root / "native-token-correlation.json", rows)

    result = validator.main([str(root)])

    assert result == 2
    assert json.loads(capsys.readouterr().out)["outcome"] == "blocked"


def test_validator_script_process_returns_nonzero_on_mapping_id_tampering(
    tmp_path: Path,
):
    root = fixture.make_run(tmp_path / "run")
    rows = _json(root / "native-token-correlation.json")
    rows[0]["mappingId"] = "0" * 64
    _write(root / "native-token-correlation.json", rows)

    result = subprocess.run([
        sys.executable,
        str(ROOT / "modules/teastore/validation/native_token_correlation.py"),
        str(root),
    ], check=False, capture_output=True, text=True)

    assert result.returncode == 2
    assert json.loads(result.stdout)["outcome"] == "blocked"


def test_output_refuses_overwrite_and_symlink(tmp_path: Path):
    root = fixture.make_run(tmp_path / "run")
    target = root / "target.json"
    target.write_text("[]\n")
    output = root / "new-output.json"
    output.symlink_to(target)
    with pytest.raises(FileExistsError):
        extractor.extract(
            auth_log=root / "auth.log",
            journey_ledger=root / "journey-ledger.jsonl",
            traces=root / "traces.json",
            run_receipt=root / "receipt.json",
            service_log_capture_receipt=root / "service-log-capture.json",
            output=output,
            extraction_receipt=root / "new-receipt.json",
        )
