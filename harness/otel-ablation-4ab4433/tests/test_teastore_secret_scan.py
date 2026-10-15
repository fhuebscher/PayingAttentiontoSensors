import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
PATH = ROOT / "modules/teastore/validation/secret_scan.py"
SPEC = importlib.util.spec_from_file_location("teastore_secret_scan_tests", PATH)
secret_scan = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(secret_scan)


def _nested_secret(layers: int) -> str:
    payload = '{"password":"x"}'
    for _ in range(layers):
        payload = json.dumps(payload)
    return "normal-log-prefix " + payload


@pytest.mark.parametrize("payload", [
    "password=x",
    '{"password":"x"}',
    '{"PASSWORD" : "x"}',
    '{"pass\\u0077ord":"x"}',
    '{"message":"{\\"password\\":\\"x\\"}"}',
    "normal-log-prefix " + json.dumps(
        json.dumps('{"pass\\u0077ord":"x"}')),
    _nested_secret(secret_scan.MAX_NESTING + 1),
    '{"outer":{"request_body":"x"}}',
    'normal-log-prefix {"pass_word":"x"}',
    'normal-log-prefix {"session_id":"x"}',
    'normal-log-prefix {"p a s s w o r d":"x"}',
    'normal-log-prefix {"_password_":"x"}',
    'normal-log-prefix {"paßword":"x"}',
    'normal-log-prefix {"pass\\tword":"x"}',
    'normal-log-prefix {"pass\\nword":"x"}',
    'normal-log-prefix {"pass\\rword":"x"}',
    'normal-log-prefix {"pass\\fword":"x"}',
    'normal-log-prefix {"_pa\\tssword_":"x"}',
    'normal-log-prefix {"pa\\u00dfword":"x"}',
    "normal-log-prefix " + json.dumps(json.dumps('{"pass\\tword":"x"}')),
    'normal-log-prefix Authorization: Bearer\\tx',
    'normal-log-prefix {"p' + ('_' * 248) + 'assword":"x"}',
    'normal-log-prefix {"p' + ('_' * 257) + 'assword":"x"}',
    'normal-log-prefix {"db_password":"hunter2"}',
    'normal-log-prefix {"dbPassword":"hunter2"}',
    'normal-log-prefix {"db_credential":"hunter2"}',
    'normal-log-prefix {"db.credential":"hunter2"}',
    'normal-log-prefix {"credentialStore":"hunter2"}',
    'normal-log-prefix {"password_hash":"hunter2"}',
    'normal-log-prefix {"user-password":"hunter2"}',
    'normal-log-prefix {"db.password":"hunter2"}',
    'normal-log-prefix {"pass.word":"hunter2"}',
    'normal-log-prefix {"request.body":"hunter2"}',
    'normal-log-prefix {"db_pass\\\"word":"hunter2"}',
    'normal-log-prefix {"request\\\"body":"hunter2"}',
    'normal-log-prefix {"access_token":"hunter2"}',
    'normal-log-prefix {"apiKey":"hunter2"}',
    'normal-log-prefix {"api_token":"hunter2"}',
    'normal-log-prefix {"bearerToken":"hunter2"}',
    'normal-log-prefix {"clientSecret":"hunter2"}',
    'normal-log-prefix {"client_secret":"hunter2"}',
    'prefix {"password"\n : "x"}',
    'Authorization: Bearer x',
])
def test_secret_scanner_rejects_equivalent_secret_representations(payload):
    assert secret_scan.contains_secret_text(payload) is True


@pytest.mark.parametrize("payload", [
    "ordinary TeaStore log output",
    '{"schema":"teastore.app-witness","journeyId":"journey-abc"}',
    '{"message":"request completed","status":200}',
    'normal-log-prefix {"consideration":"ordinary"}',
    'normal-log-prefix {"token":"journey-fixture"}',
    'normal-log-prefix {"secretary":"ordinary"}',
    'normal-log-prefix {"tokenization":"ordinary"}',
    'normal-log-prefix {"' + ('x' * secret_scan.MAX_ASSIGNMENT_KEY_CHARS)
    + '":"ordinary"}',
    "",
])
def test_secret_scanner_allows_non_secret_log_text(payload):
    assert secret_scan.contains_secret_text(payload) is False


def test_secret_scanner_fails_closed_above_assignment_key_bound():
    payload = (
        'normal-log-prefix {"'
        + ('x' * (secret_scan.MAX_ASSIGNMENT_KEY_CHARS + 1))
        + '":"ordinary"}'
    )
    assert secret_scan.contains_secret_text(payload) is True
