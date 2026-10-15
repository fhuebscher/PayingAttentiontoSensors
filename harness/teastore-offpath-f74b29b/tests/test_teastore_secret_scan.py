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


# --------------------------------------------- JVM stack-frame source locations (traffic sweep, relaunch 1 cell 11)
# Synthesized frames (no retained log text): packages, classes and methods embed every secret name the scanner
# knows, as EclipseLink's internal.sessions package did in TeaStore relaunch 1, cell 11 (2026-10-03).
def _frames() -> str:
    lines = ["org.example.store.LockTimeoutError: lock wait exceeded after 3 attempts"]
    for number, (package, clazz, method, extension) in enumerate([
        ("org.example.internal.sessions", "SessionCache", "lookupSession", "java"),
        ("org.example.internal.sessions", "UnitOfWork", "commit", "java"),
        ("org.example.auth.password", "PasswordCheck", "verifyPassword", "kt"),
        ("org.example.credentials", "CredentialVault", "open", "scala"),
        ("org.example.web.cookie", "CookieFilter", "doFilter", "groovy"),
        ("org.example.authorization", "AuthorizationGate", "lambda$check$0", "java"),
        ("org.example.sessions", "SessionPool$Lease", "acquire", "kt"),
    ], start=1):
        lines.append(f"\tat {package}.{clazz}.{method}({clazz.split('$')[0]}.{extension}:{number * 37})")
    lines += [
        "\tat java.base/org.example.sessions.Store.load(Store.java:1)",
        "\tat app//org.example.sessions.Store.save(Store.java:65535)",
        "\tat org.example.sessions.NativeBridge.call(Native Method)",
        "Caused by: org.example.store.StoreFailure: retry budget spent",
        "\tat org.example.internal.sessions.SessionCache.evict(SessionCache.java:12)",
        "\t... 7 more",
    ]
    return "\n".join(lines) + "\n"


def test_jvm_stack_frames_are_not_assignments_in_the_sweep_mode():
    assert secret_scan.contains_secret_text(_frames(), jvm_source_locations=True) is False
    for line in _frames().splitlines():
        assert secret_scan.contains_secret_text(line, jvm_source_locations=True) is False, line


def test_jvm_stack_frames_still_block_with_the_frozen_default():
    assert secret_scan.contains_secret_text(_frames()) is True
    assert secret_scan.contains_secret_text(_frames(), jvm_source_locations=False) is True


@pytest.mark.parametrize("payload", [
    # frame-shaped locations whose value is not ASCII digits + ")" or whose key is not a source file
    "\tat org.example.internal.sessions.Store.load(Store.java:abc)",
    "\tat org.example.internal.sessions.Store.load(Store.java:12x)",
    "\tat org.example.internal.sessions.Store.load(Store.java:)",
    "\tat org.example.internal.sessions.Store.load(Store.java:-1)",
    "\tat org.example.internal.sessions.Store.load(Store.java: 12)",
    "\tat org.example.internal.sessions.Store.load(Store.java:12",
    "\tat org.example.internal.sessions.Store.load(Store.java:١٢)",
    "\tat org.example.internal.sessions.Store.load(Store.java=12)",
    "\tat org.example.internal.sessions.Store.load(Store.java :12)",
    "\tat org.example.internal.sessions.Store.load(Store.txt:12)",
    "\tat org.example.internal.sessions.Store.load(Store.javascript:12)",
    "\tat org.example.internal.sessions.Store.load(.java:12)",
    "\tat org.example.internal.sessions.Store.java:12)",
    "\tat org.example.sessions.Store.load((Store.java:12)",
    "(Session.java:12)",
    # plain secrets
    "password=planted-not-a-real-secret",
    "session: planted-not-a-real-secret",
    '"password": 1',
    "Authorization: Bearer planted-not-a-real-token",
    "bearer planted-not-a-real-token",
    # compound keys with an embedded secret name that are not source locations
    "db_password=planted-not-a-real-secret",
    "sessionToken: planted-not-a-real-secret",
    "org.example.sessions.SessionFailure: planted-not-a-real-secret",
    # a real frame does not hide another assignment on its line or the next one
    "\tat org.example.sessions.Store.load(Store.java:12) password=planted-not-a-real-secret",
    "\tat org.example.sessions.Store.load(Store.java:12)\nsession: planted-not-a-real-secret",
    '{"stack":"at org.example.Session.load(Session.java:1)","password":"planted-not-a-real-secret"}',
    '{"at org.example.sessions.Store.load(Store.java": 12}',
    # nothing may be glued to the frame's ")" (review of 1a3ca07, finding A1)
    "password(Store.java:1)=planted-not-a-real-secret",
    "password(Store.java:1)planted-not-a-real-secret",
    "\tat org.example.sessions.Store.load(Store.java:12)x",
    "\tat org.example.sessions.Store.load(Store.java:12)):",
    # a frame inside a JSON string is followed by a quote or an escape at the raw layer: fail closed
    '{"stack":"at org.example.sessions.Store.load(Store.java:1)"}',
    '{"stack":"at org.example.sessions.Store.load(Store.java:1)\\n\\tat org.example.sessions.Store.save(Store.java:2)"}',
    # an overlong key blocks before the frame test (review of 1a3ca07, finding A2)
    "x" * 300 + "password(Store.java:12)",
    "\tat org.example." + "a" * 300 + ".Store.load(Store.java:12)",
])
def test_the_jvm_frame_rule_is_narrow(payload):
    assert secret_scan.contains_secret_text(payload, jvm_source_locations=True) is True


def test_the_switch_reaches_the_json_walk():
    # Raw layer: the frame is followed by a space, so it is skipped there; the per-line JSON walk then decodes the
    # string value and must apply the same switch (review of 1a3ca07, finding B1: a mutant that dropped the flag
    # in _walk_json survived every other test).
    payload = '{"stack":"at org.example.sessions.Store.load(Store.java:1) "}'
    assert secret_scan.contains_secret_text(payload, jvm_source_locations=True) is False
    assert secret_scan.contains_secret_text(payload) is True
    nested = json.dumps({"outer": payload})                  # the switch also reaches a nested JSON string
    assert secret_scan.contains_secret_text(nested, jvm_source_locations=True) is False
    assert secret_scan.contains_secret_text(nested) is True


def test_the_jvm_frame_rule_ceiling_is_a_digits_only_value():
    # Documented ceiling (secret_scan.JVM_SOURCE_KEY): a digits-only value in exactly the frame shape passes; one
    # non-digit in that slot blocks.  A JVM frame prints a source line number there, never request data.
    assert secret_scan.contains_secret_text("password(Store.java:1234)", jvm_source_locations=True) is False
    assert secret_scan.contains_secret_text("password(Store.java:1234) \n", jvm_source_locations=True) is False
    assert secret_scan.contains_secret_text("password(Store.java:12a4)", jvm_source_locations=True) is True
    assert secret_scan.contains_secret_text("password(Store.java:1234)5", jvm_source_locations=True) is True
    assert secret_scan.contains_secret_text("password(Store.java:1234)") is True


@pytest.mark.parametrize("flag", [1, "yes", None])
def test_the_jvm_frame_switch_must_be_a_bool(flag):
    with pytest.raises(TypeError):
        secret_scan.contains_secret_text(_frames(), jvm_source_locations=flag)
