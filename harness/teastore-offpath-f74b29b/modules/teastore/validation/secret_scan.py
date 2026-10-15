"""Fail-closed scanner for secret-bearing retained service-log text.

The scanner operates on the complete bounded capture, not individual lines.
It checks raw and repeatedly unescaped text, then recursively inspects JSON
objects and JSON strings.  This makes quoted, Unicode-escaped, nested, and
multiline key assignments equivalent for the privacy gate.
"""
from __future__ import annotations

import json
import re
from typing import Any


SECRET_KEYS = frozenset({
    "authorization", "setcookie", "cookie", "credential", "password",
    "requestbody", "session", "sessionid", "sid", "accesstoken", "apikey",
    "apitoken", "bearertoken", "clientsecret", "secretkey",
})
# Longer credential-bearing names remain sensitive when embedded in a compound
# key (for example ``db_password`` or ``passwordHash``).  ``sid`` stays exact:
# treating that three-letter token as a substring would reject ordinary words
# such as ``consideration`` without improving the credential boundary.
EMBEDDED_SECRET_KEYS = SECRET_KEYS - {"sid"}
BEARER_TEXT = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*")
QUOTED_KEY_ASSIGNMENT = re.compile(
    r"(?<!\\)(?:\"(?P<double>(?:\\.|[^\"\\])+)\"|"
    r"'(?P<single>(?:\\.|[^'\\])+)'"
    r")\s*[:=]",
    re.DOTALL,
)
UNQUOTED_KEY_ASSIGNMENT = re.compile(
    r"(?<![A-Za-z0-9_-])(?P<key>[^\s:=,\"'{}\[\]]+)\s*[:=]"
)
# JVM stack-frame source locations (traffic sweep only; TeaStore relaunch 1, cell 11, 2026-10-03).  In a frame
# line such as ``at org.example.internal.sessions.Store.load(Store.java:123)`` the unquoted-assignment rule reads
# ``org.example.internal.sessions.Store.load(Store.java`` as a key and the ``:`` as an assignment; the normalized
# key embeds ``session``, so a stack trace under load blocked the cell although it carries no field value.  With
# ``jvm_source_locations=True`` one match is skipped only when ALL of these hold:
#   * the matched text is the key immediately followed by ``:`` (no whitespace, never ``=``);
#   * the key contains exactly one ``(``, has text before it, and the text after it is a file name ending in
#     ``.java``, ``.kt``, ``.scala`` or ``.groovy`` (JVM_SOURCE_KEY);
#   * the text right after the ``:`` is one or more ASCII digits, then ``)``, then whitespace or the end of the
#     text (JVM_SOURCE_LINE; nothing may be glued to the ``)``);
#   * the key is within MAX_ASSIGNMENT_KEY_CHARS (an overlong key blocks before the frame test).
# Everything else stays flagged, including a frame-shaped location with any other value and every other
# assignment on the same line (the scan continues after the skipped match).
# Ceiling: the rule accepts a digits-only value after a ``(<File>.java:`` key, closed by ``)`` and whitespace.  A JVM
# frame cannot carry a secret there (the JVM prints the class file's line number), but application text that writes
# a digits-only secret into exactly that shape (``password(x.java:1234)``) would not be flagged.  A frame inside a
# JSON string is followed by a quote or an escape at the raw-text layer, so it still blocks there (fail closed).
JVM_SOURCE_KEY = re.compile(r"[^()]+\([^()]+\.(?:java|kt|scala|groovy)")
JVM_SOURCE_LINE = re.compile(r"[0-9]+\)(?=\s|\Z)")
UNICODE_ESCAPE = re.compile(r"(?<!\\)\\u([0-9a-fA-F]{4})")
HEX_ESCAPE = re.compile(r"(?<!\\)\\x([0-9a-fA-F]{2})")
JSON_WHITESPACE_ESCAPE = re.compile(r"(?<!\\)\\([tnrf])")
JSON_WHITESPACE = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}
MAX_ASSIGNMENT_KEY_CHARS = 256
MAX_NESTING = 8
MAX_VARIANTS = 512


def _normalized_key(value: Any) -> str:
    # Treat punctuation/spacing as presentation, not as a way to split a
    # credential-bearing key.  Keep Unicode word characters until casefolding
    # so confusable spellings such as ``paßword`` remain detectable.
    return re.sub(r"[\W_]+", "", str(value), flags=re.UNICODE).casefold()


def _is_secret_key(value: Any) -> bool:
    normalized = _normalized_key(value)
    return (
        normalized in SECRET_KEYS
        or any(secret in normalized for secret in EMBEDDED_SECRET_KEYS)
    )


def _is_jvm_source_location(value: str, match: Any) -> bool:
    key = match.group("key")
    return (
        match.group(0) == key + ":"
        and JVM_SOURCE_KEY.fullmatch(key) is not None
        and JVM_SOURCE_LINE.match(value, match.end()) is not None
    )


def _secret_in_layer(value: str, jvm_source_locations: bool = False) -> bool:
    if BEARER_TEXT.search(value):
        return True
    quoted_keys = (
        match.group("double") if match.group("double") is not None
        else match.group("single")
        for match in QUOTED_KEY_ASSIGNMENT.finditer(value)
    )
    for key in quoted_keys:
        # Any escape in an assignment key is ambiguous at this raw-text layer;
        # decoded alternatives are inspected separately, so fail closed here.
        if "\\" in key or len(key) > MAX_ASSIGNMENT_KEY_CHARS or _is_secret_key(key):
            return True
    for match in UNQUOTED_KEY_ASSIGNMENT.finditer(value):
        key = match.group("key")
        # The scanner must never make an overlong assignment key invisible
        # merely because its normalization budget was exceeded.
        if len(key) > MAX_ASSIGNMENT_KEY_CHARS:
            return True
        if jvm_source_locations and _is_jvm_source_location(value, match):
            continue
        if _is_secret_key(key):
            return True
    return False


def _one_step_layers(value: str) -> set[str]:
    """Return distinct one-operation decodings without destroying alternatives."""

    candidates = {
        value.replace("\\\\", "\\"),
        value.replace('\\"', '"'),
        value.replace("\\'", "'"),
        UNICODE_ESCAPE.sub(lambda match: chr(int(match.group(1), 16)), value),
        HEX_ESCAPE.sub(lambda match: chr(int(match.group(1), 16)), value),
        JSON_WHITESPACE_ESCAPE.sub(
            lambda match: JSON_WHITESPACE[match.group(1)], value
        ),
    }
    try:
        decoded = json.loads(value)
    except (json.JSONDecodeError, UnicodeError):
        decoded = None
    if isinstance(decoded, str):
        candidates.add(decoded)
    candidates.discard(value)
    return candidates


def _text_layers(value: str) -> tuple[tuple[str, ...], bool]:
    """Enumerate bounded decoding branches and report an exhausted bound."""

    seen = {value}
    frontier = {value}
    for _ in range(MAX_NESTING):
        following: set[str] = set()
        for candidate in frontier:
            following.update(_one_step_layers(candidate))
        following.difference_update(seen)
        if not following:
            return tuple(seen), False
        seen.update(following)
        if len(seen) > MAX_VARIANTS:
            return tuple(seen), True
        frontier = following
    return tuple(seen), any(_one_step_layers(candidate) for candidate in frontier)


def _walk_json(value: Any, depth: int = 0, jvm_source_locations: bool = False) -> bool:
    if depth > MAX_NESTING:
        return True
    if isinstance(value, dict):
        return any(
            _is_secret_key(key) or _walk_json(child, depth + 1, jvm_source_locations)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_walk_json(child, depth + 1, jvm_source_locations) for child in value)
    if not isinstance(value, str):
        return False
    layers, exhausted = _text_layers(value)
    if exhausted or any(_secret_in_layer(layer, jvm_source_locations) for layer in layers):
        return True
    for layer in layers:
        try:
            nested = json.loads(layer)
        except (json.JSONDecodeError, UnicodeError):
            continue
        if nested != layer and _walk_json(nested, depth + 1, jvm_source_locations):
            return True
    return False


def contains_secret_text(value: str, *, jvm_source_locations: bool = False) -> bool:
    """Return true when a complete retained log can disclose a secret field.

    ``jvm_source_locations`` (default False, the frozen epoch's behaviour) lets JVM stack-frame source locations
    through (JVM_SOURCE_KEY / JVM_SOURCE_LINE); the callers pass True only when the traffic-sweep epoch is active.
    """

    if not isinstance(value, str):
        raise TypeError("secret scanner input must be text")
    if type(jvm_source_locations) is not bool:
        raise TypeError("jvm_source_locations must be a bool")
    layers, exhausted = _text_layers(value)
    if exhausted or any(_secret_in_layer(layer, jvm_source_locations) for layer in layers):
        return True
    candidates = [
        *layers,
        *(line for layer in layers for line in layer.splitlines() if line.strip()),
    ]
    for candidate in candidates:
        try:
            decoded = json.loads(candidate)
        except (json.JSONDecodeError, UnicodeError):
            continue
        if _walk_json(decoded, jvm_source_locations=jvm_source_locations):
            return True
    return False
