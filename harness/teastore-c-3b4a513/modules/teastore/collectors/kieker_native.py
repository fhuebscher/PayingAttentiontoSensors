#!/usr/bin/env python
"""Kieker-NATIVE trace collector for TeaStore (real per-request causality).

The legacy scraper (collect_kieker_traces.py) regex-greps method signatures out
of the raw binary AMQP payload and stamps synthetic ``scraped_<uuid>`` trace ids,
discarding the real ``traceId``/``eoi``/``ess``/``tin``/``tout`` that TeaStore's
Kieker probes serialize. This collector deserializes the Kieker 2.0.0 binary wire
format properly, recovering the native call-tree so TeaStore becomes per-trace
clusterable like the OTel/HR SUTs (``build_propagation_paths --flow-clustering
trace``).

WIRE FORMAT (Kieker 2.0.0, verified by disassembling kieker-2.0.0-aspectj.jar:
BinarySerializer / AbstractContainerFormatSerializer / BinaryValueSerializer /
VariableLengthEncoding / RegistryRecord / OperationExecutionRecord).

Each AMQP message body (queue ``kieker``, published by ChunkingAmqpWriter) is one
serialized *container*, big-endian throughout (Java ByteBuffer default):

    [CONTAINER_IDENTIFIER int32 = 1263094593]      # header (8 bytes)
    [FORMAT_IDENTIFIER    int32 = 1145457748]
    <records region>                               # length = recordsLength
      per record:
        [classId       int32]                      # string-registry id of FQCN
        [loggingTs     int64]
        [record fields ...]                        # strings = int32 registry id
    <string-registry region>
      [count varint]
      per entry: [byteLen varint][UTF-8 bytes]     # id == its 0-based position
    [recordsLength int32]                          # byte length of records region

Because the string registry is written AFTER the records that reference it, the
trailing ``recordsLength`` int32 is what lets a reader split the two regions:

    records  = body[8 : 8 + recordsLength]
    registry = body[8 + recordsLength : len(body) - 4]

The registry id of a string == its 0-based index in the registry list. A record's
class id is itself a registry id resolving to the fully-qualified class name (e.g.
``tools.descartes.teastore.kieker.probes.records.OperationExecutionWithParametersRecord``
or ``kieker.common.record.controlflow.OperationExecutionRecord``).

Field order (OperationExecutionRecord.serialize, confirmed from bytecode):
    operationSignature:String, sessionId:String, traceId:long, tin:long,
    tout:long, hostname:String, eoi:int, ess:int
The WithParameters subclass appends: parameterTypes:String[], parameterValues:
String[], returnType:String, returnValue:String, where a String[] is
[int32 count][count * String] (String = int32 registry id).

Parent inference: eoi/ess encode the dynamic call tree. Within one traceId the
records share eoi (execution-order index, 0-based) and ess (execution-stack size
/ depth). span_id surrogate = ``{traceId}:{eoi}``; parent = the active prior
record at ``ess - 1`` after globally ordering every record observed for that
trace. The correlator is deliberately stateful because one native trace commonly
crosses several AMQP containers. Missing and conflicting native identities are
reported as unresolved/ambiguous instead of being silently turned into roots.

Emits the unified event schema (see tools/collectors/collect_jaeger_traces.py and
collectors/__init__.py): real ``trace_id=str(traceId)``, ``span_id``,
``parent_span_id``, ``duration_s=(tout-tin)/1e9``, ``timestamp`` from tin,
``service`` primarily from the runtime container-id/hostname map, checked against
the declaring class in the actual method signature (never the return type),
``source="kieker_native"``, plus
the native-only schema optionals ``kieker_trace_id``, ``eoi``, ``ess``, ``tin``,
``tout``, ``session_id``, ``hostname``. Unparseable records are counted and
skipped, never crash the stream; parse-success ratio is reported at exit.

QUEUE-SHARING CONSTRAINT: this collector and the legacy scraper consume the SAME
RabbitMQ queue (``kieker``). They must NEVER run simultaneously — messages would
be split round-robin between the two consumers and both datasets would be
incomplete. collect_empirical_data.py dispatches on ``collector:`` either/or.

Self-check: ``python tools/collectors/collect_kieker_native.py --self-check``
builds a synthetic binary fixture and round-trips it (no server needed).
"""

from __future__ import annotations

import argparse
import datetime as datetime_module
import decimal
import hashlib
import json
import math
import os
import re
import stat
import struct
import sys
import time
from pathlib import Path

# ── Kieker 2.0.0 wire constants (from disassembly) ──────────────────────────
CONTAINER_IDENTIFIER = 1263094593   # FormatIdentifier.CONTAINER_FORMAT
FORMAT_IDENTIFIER = 1145457748      # FormatIdentifier.DEFAULT_BINARY_FORMAT
REGISTRY_CLASS_ID = -1              # RegistryRecord.CLASS_ID (not used inline; kept for ref)

OER_CLASS = "kieker.common.record.controlflow.OperationExecutionRecord"
OEWPR_CLASS = ("tools.descartes.teastore.kieker.probes.records."
               "OperationExecutionWithParametersRecord")

DEFAULT_SERVICE_REGEX = r'tools\.descartes\.teastore\.([a-zA-Z0-9_]+)\.'
DEFAULT_SERVICE_MAP = {"store": "auth", "entities": "persistence",
                       "registryclient": "registry"}
FROZEN_SERVICE_MAP_JSON = json.dumps(
    DEFAULT_SERVICE_MAP, sort_keys=True, separators=(",", ":"),
)
SHARED_SIGNATURE_PACKAGES = frozenset({"entities", "registryclient"})
CANONICAL_RUNTIME_SERVICES = frozenset({
    "auth", "db", "image", "persistence", "rabbitmq", "recommender",
    "registry", "webui",
})
CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{64}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

SPOOL_MAGIC = b"KIEKER-AMQP-SPOOL-V1\n"
SPOOL_FRAME_MAGIC = b"KSP1"
SPOOL_ZERO_DIGEST = "0" * 64
SPOOL_ARTIFACT_NAME = "kieker-amqp.spool"
SPOOL_METADATA_LIMIT = 1024 * 1024
SPOOL_BODY_LIMIT = 512 * 1024 * 1024


class KiekerSpoolError(RuntimeError):
    """A durable Kieker body spool cannot be trusted or completed."""


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _identity_value(value: object) -> object:
    """Normalize AMQP field-table values without lossy string coercion."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise KiekerSpoolError("AMQP identity contains a non-finite float")
        return {"type": "float-hex", "value": value.hex()}
    if isinstance(value, bytes):
        return {"type": "bytes-hex", "value": value.hex()}
    if isinstance(value, decimal.Decimal):
        return {"type": "decimal", "value": str(value)}
    if isinstance(value, datetime_module.datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, (list, tuple)):
        return [_identity_value(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise KiekerSpoolError("AMQP identity mapping keys must be strings")
        return {key: _identity_value(value[key]) for key in sorted(value)}
    raise KiekerSpoolError(
        f"AMQP identity contains unsupported value type {type(value).__name__}"
    )


def amqp_delivery_identity(method: object, properties: object | None) -> dict:
    """Return the exact deterministic identity fields retained with one body."""

    delivery_tag = getattr(method, "delivery_tag", None)
    if (not isinstance(delivery_tag, int) or isinstance(delivery_tag, bool)
            or delivery_tag < 0):
        raise KiekerSpoolError("AMQP delivery tag is missing or invalid")
    method_identity = {
        "consumerTag": getattr(method, "consumer_tag", None),
        "deliveryTag": delivery_tag,
        "redelivered": getattr(method, "redelivered", None),
        "exchange": getattr(method, "exchange", None),
        "routingKey": getattr(method, "routing_key", None),
    }
    property_names = (
        "content_type", "content_encoding", "headers", "delivery_mode",
        "priority", "correlation_id", "reply_to", "expiration", "message_id",
        "timestamp", "type", "user_id", "app_id", "cluster_id",
    )
    property_identity = {
        name: getattr(properties, name, None) if properties is not None else None
        for name in property_names
    }
    identity = {
        "schemaVersion": 1,
        "method": _identity_value(method_identity),
        "properties": _identity_value(property_identity),
    }
    # Force canonical serialization here so unsupported values fail before a
    # body can be framed or acknowledged.
    _canonical_json_bytes(identity)
    return identity


def _path_without_symlinks(path: Path, *, must_exist: bool) -> Path:
    """Return an absolute path only when no existing component is a symlink."""

    candidate = Path(os.path.abspath(os.fspath(path)))
    components = candidate.parts
    current = Path(components[0])
    for component in components[1:]:
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            if must_exist or current != candidate:
                raise KiekerSpoolError(f"spool path component does not exist: {current}")
            break
        if stat.S_ISLNK(info.st_mode):
            raise KiekerSpoolError(f"spool path contains a symbolic link: {current}")
        if current != candidate and not stat.S_ISDIR(info.st_mode):
            raise KiekerSpoolError(f"spool parent is not a directory: {current}")
    return candidate


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("spool write made no progress")
        offset += written


def _spool_frame(metadata: dict, body: bytes) -> tuple[bytes, str]:
    metadata_bytes = _canonical_json_bytes(metadata)
    if len(metadata_bytes) > SPOOL_METADATA_LIMIT:
        raise KiekerSpoolError("spool frame metadata exceeds the hard limit")
    if len(body) > SPOOL_BODY_LIMIT:
        raise KiekerSpoolError("spool body exceeds the hard limit")
    prefix = (
        SPOOL_FRAME_MAGIC
        + struct.pack(">I", len(metadata_bytes))
        + struct.pack(">Q", len(body))
    )
    digest = hashlib.sha256(prefix + metadata_bytes + body).digest()
    return prefix + metadata_bytes + body + digest, digest.hex()


def _replayed_identity_value_is_normalized(value: object) -> bool:
    if value is None or type(value) in {bool, int, str}:
        return True
    if isinstance(value, float):
        return False
    if isinstance(value, list):
        return all(_replayed_identity_value_is_normalized(item) for item in value)
    if not isinstance(value, dict):
        return False
    if set(value) == {"type", "value"}:
        kind = value.get("type")
        encoded = value.get("value")
        if not isinstance(kind, str) or not isinstance(encoded, str):
            return False
        try:
            if kind == "float-hex":
                decoded = float.fromhex(encoded)
                return math.isfinite(decoded) and decoded.hex() == encoded
            if kind == "bytes-hex":
                return bytes.fromhex(encoded).hex() == encoded
            if kind == "decimal":
                decoded_decimal = decimal.Decimal(encoded)
                return decoded_decimal.is_finite() and str(decoded_decimal) == encoded
            if kind == "datetime":
                decoded_datetime = datetime_module.datetime.fromisoformat(encoded)
                return decoded_datetime.isoformat() == encoded
        except (ValueError, decimal.InvalidOperation):
            return False
        return False
    return (
        all(isinstance(key, str) for key in value)
        and all(_replayed_identity_value_is_normalized(item) for item in value.values())
    )


def _replayed_identity_is_typed(identity: object) -> bool:
    if not isinstance(identity, dict) or set(identity) != {
        "schemaVersion", "method", "properties",
    }:
        return False
    if type(identity.get("schemaVersion")) is not int or identity["schemaVersion"] != 1:
        return False
    method = identity.get("method")
    properties = identity.get("properties")
    if not isinstance(method, dict) or set(method) != {
        "consumerTag", "deliveryTag", "redelivered", "exchange", "routingKey",
    }:
        return False
    if (type(method.get("deliveryTag")) is not int or method["deliveryTag"] < 0
            or type(method.get("redelivered")) is not bool
            or any(method.get(field) is not None and not isinstance(method.get(field), str)
                   for field in ("consumerTag", "exchange", "routingKey"))):
        return False
    property_fields = {
        "content_type", "content_encoding", "headers", "delivery_mode",
        "priority", "correlation_id", "reply_to", "expiration", "message_id",
        "timestamp", "type", "user_id", "app_id", "cluster_id",
    }
    if not isinstance(properties, dict) or set(properties) != property_fields:
        return False
    for field in ("delivery_mode", "priority", "timestamp"):
        value = properties.get(field)
        if value is not None and (type(value) is not int or value < 0):
            return False
    for field in property_fields - {"headers", "delivery_mode", "priority", "timestamp"}:
        value = properties.get(field)
        if value is not None and not isinstance(value, str):
            return False
    headers = properties.get("headers")
    return headers is None or (
        isinstance(headers, dict) and _replayed_identity_value_is_normalized(headers)
    )


class KiekerBodySpool:
    """Exclusive append-only body journal with an fsynced terminal seal."""

    def __init__(self, path: Path):
        self.path = _path_without_symlinks(path, must_exist=False)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        self._descriptor = os.open(self.path, flags, 0o600)
        self._fsync = os.fsync
        self._write_all = _write_all
        self._poisoned = False
        self._sealed = False
        self._sequence = 0
        self._last_digest = SPOOL_ZERO_DIGEST
        self._delivery_count = 0
        self._body_bytes = 0
        self._body_hashes: dict[str, bytes] = {}
        self._stable_identities: dict[str, str] = {}
        try:
            self._write_all(self._descriptor, SPOOL_MAGIC)
            self._fsync(self._descriptor)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                self._fsync(directory)
            finally:
                os.close(directory)
        except Exception:
            self._poisoned = True
            os.close(self._descriptor)
            self._descriptor = -1
            raise

    @staticmethod
    def _stable_identity(identity: dict) -> str | None:
        properties = identity.get("properties", {})
        if not isinstance(properties, dict):
            return None
        message_id = properties.get("message_id")
        correlation_id = properties.get("correlation_id")
        if message_id is None and correlation_id is None:
            return None
        return hashlib.sha256(_canonical_json_bytes({
            "messageId": message_id,
            "correlationId": correlation_id,
        })).hexdigest()

    def _append_frame(self, metadata: dict, body: bytes) -> str:
        if self._descriptor < 0 or self._poisoned or self._sealed:
            raise KiekerSpoolError("spool is closed, poisoned, or already sealed")
        frame, digest = _spool_frame(metadata, body)
        try:
            self._write_all(self._descriptor, frame)
            # This is the acknowledgement boundary. The caller must not ack
            # unless this exact frame and its raw body have crossed fsync.
            self._fsync(self._descriptor)
        except Exception as exc:
            self._poisoned = True
            raise KiekerSpoolError(
                f"durable spool append failed: {type(exc).__name__}: {exc}"
            ) from exc
        self._sequence += 1
        self._last_digest = digest
        return digest

    def append_delivery(self, body: bytes, identity: dict) -> str:
        if not isinstance(body, bytes):
            raise TypeError("spooled AMQP body must be bytes")
        body_sha256 = hashlib.sha256(body).hexdigest()
        identity_sha256 = hashlib.sha256(_canonical_json_bytes(identity)).hexdigest()
        stable_identity = self._stable_identity(identity)
        if stable_identity is not None:
            prior_body = self._stable_identities.get(stable_identity)
            if prior_body is not None and prior_body != body_sha256:
                self._poisoned = True
                raise KiekerSpoolError("stable AMQP identity changed raw body hash")
        prior_bytes = self._body_hashes.get(body_sha256)
        if prior_bytes is not None and prior_bytes != body:
            self._poisoned = True
            raise KiekerSpoolError("SHA-256 collision across raw AMQP bodies")
        metadata = {
            "schemaVersion": 1,
            "kind": "delivery",
            "sequence": self._sequence + 1,
            "previousFrameSha256": self._last_digest,
            "identity": identity,
            "identitySha256": identity_sha256,
            "bodyBytes": len(body),
            "bodySha256": body_sha256,
        }
        digest = self._append_frame(metadata, body)
        self._delivery_count += 1
        self._body_bytes += len(body)
        self._body_hashes.setdefault(body_sha256, body)
        if stable_identity is not None:
            self._stable_identities.setdefault(stable_identity, body_sha256)
        return digest

    def seal(self) -> str:
        if self._sealed:
            raise KiekerSpoolError("spool terminal seal already exists")
        metadata = {
            "schemaVersion": 1,
            "kind": "terminal",
            "sequence": self._sequence + 1,
            "previousFrameSha256": self._last_digest,
            "deliveryCount": self._delivery_count,
            "rawBodyBytes": self._body_bytes,
            "uniqueBodyCount": len(self._body_hashes),
            "duplicateBodyCount": self._delivery_count - len(self._body_hashes),
        }
        digest = self._append_frame(metadata, b"")
        self._sealed = True
        os.close(self._descriptor)
        self._descriptor = -1
        return digest

    def close_unsealed(self) -> None:
        if self._descriptor >= 0:
            os.close(self._descriptor)
            self._descriptor = -1


def replay_kieker_spool(path: Path) -> tuple[list[bytes], dict]:
    """Strictly replay all frames and return bodies plus typed spool evidence."""

    requested = Path(path)
    report = {
        "schemaVersion": 1,
        "path": requested.name,
        "deliveryCount": 0,
        "uniqueBodyCount": 0,
        "duplicateBodyCount": 0,
        "rawBodyBytes": 0,
        "spoolBytes": None,
        "artifactSha256": None,
        "terminalDigestSha256": None,
        "sealed": False,
        "complete": False,
        "blockers": [],
    }
    bodies: list[bytes] = []
    blockers = report["blockers"]
    try:
        absolute = _path_without_symlinks(requested, must_exist=True)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(absolute, flags)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise KiekerSpoolError("spool is not a singly-linked regular file")
            payload = bytearray()
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                payload.extend(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        observed = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if identity != observed:
            raise KiekerSpoolError("spool changed while being replayed")
        raw = bytes(payload)
        report["spoolBytes"] = len(raw)
        report["artifactSha256"] = hashlib.sha256(raw).hexdigest()
        if not raw.startswith(SPOOL_MAGIC):
            raise KiekerSpoolError("spool header differs")
        offset = len(SPOOL_MAGIC)
        sequence = 0
        previous_digest = SPOOL_ZERO_DIGEST
        body_hashes: set[str] = set()
        stable_identities: dict[str, str] = {}
        terminal: dict | None = None
        while offset < len(raw):
            frame_start = offset
            fixed = len(SPOOL_FRAME_MAGIC) + 4 + 8
            if len(raw) - offset < fixed:
                raise KiekerSpoolError("spool has a truncated frame header")
            if raw[offset:offset + 4] != SPOOL_FRAME_MAGIC:
                raise KiekerSpoolError("spool frame magic differs")
            offset += 4
            metadata_bytes = struct.unpack_from(">I", raw, offset)[0]
            offset += 4
            body_bytes = struct.unpack_from(">Q", raw, offset)[0]
            offset += 8
            if metadata_bytes > SPOOL_METADATA_LIMIT or body_bytes > SPOOL_BODY_LIMIT:
                raise KiekerSpoolError("spool frame length exceeds the hard limit")
            end = offset + metadata_bytes + body_bytes
            if end + 32 > len(raw):
                raise KiekerSpoolError("spool has a truncated frame payload or digest")
            metadata_payload = raw[offset:offset + metadata_bytes]
            offset += metadata_bytes
            body = raw[offset:offset + body_bytes]
            offset += body_bytes
            retained_digest = raw[offset:offset + 32]
            offset += 32
            computed_digest = hashlib.sha256(raw[frame_start:offset - 32]).digest()
            if retained_digest != computed_digest:
                raise KiekerSpoolError("spool frame hash differs")
            def no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
                result: dict = {}
                for key, value in pairs:
                    if key in result:
                        raise KiekerSpoolError(
                            f"duplicate spool metadata key: {key!r}"
                        )
                    result[key] = value
                return result

            def reject_nonfinite(value: str) -> None:
                raise KiekerSpoolError(
                    f"non-finite spool metadata value: {value}"
                )

            try:
                metadata = json.loads(
                    metadata_payload.decode("utf-8"),
                    object_pairs_hook=no_duplicate_keys,
                    parse_constant=reject_nonfinite,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, KiekerSpoolError) as exc:
                raise KiekerSpoolError(f"spool frame metadata is invalid: {exc}") from exc
            if _canonical_json_bytes(metadata) != metadata_payload:
                raise KiekerSpoolError("spool frame metadata is not canonical")
            sequence += 1
            if (not isinstance(metadata, dict)
                    or type(metadata.get("schemaVersion")) is not int
                    or metadata.get("schemaVersion") != 1
                    or type(metadata.get("sequence")) is not int
                    or metadata.get("sequence") != sequence
                    or not isinstance(metadata.get("previousFrameSha256"), str)
                    or not SHA256_RE.fullmatch(metadata["previousFrameSha256"])
                    or metadata.get("previousFrameSha256") != previous_digest):
                raise KiekerSpoolError("spool sequence or digest chain differs")
            kind = metadata.get("kind")
            if kind == "delivery":
                expected_fields = {
                    "schemaVersion", "kind", "sequence", "previousFrameSha256",
                    "identity", "identitySha256", "bodyBytes", "bodySha256",
                }
                if set(metadata) != expected_fields:
                    raise KiekerSpoolError("spool delivery metadata fields differ")
                identity_document = metadata.get("identity")
                if (not _replayed_identity_is_typed(identity_document)
                        or not isinstance(metadata.get("identitySha256"), str)
                        or not SHA256_RE.fullmatch(metadata["identitySha256"])
                        or metadata.get("identitySha256")
                        != hashlib.sha256(_canonical_json_bytes(identity_document)).hexdigest()):
                    raise KiekerSpoolError("spool delivery identity type or hash differs")
                body_digest = hashlib.sha256(body).hexdigest()
                if (type(metadata.get("bodyBytes")) is not int
                        or metadata["bodyBytes"] < 0
                        or metadata.get("bodyBytes") != len(body)
                        or not isinstance(metadata.get("bodySha256"), str)
                        or not SHA256_RE.fullmatch(metadata["bodySha256"])
                        or metadata.get("bodySha256") != body_digest):
                    raise KiekerSpoolError("spool raw body length or hash differs")
                stable_identity = KiekerBodySpool._stable_identity(identity_document)
                if stable_identity is not None:
                    prior = stable_identities.get(stable_identity)
                    if prior is not None and prior != body_digest:
                        raise KiekerSpoolError("stable AMQP identity changed raw body hash")
                    stable_identities.setdefault(stable_identity, body_digest)
                bodies.append(body)
                report["deliveryCount"] += 1
                report["rawBodyBytes"] += len(body)
                body_hashes.add(body_digest)
            elif kind == "terminal":
                expected_fields = {
                    "schemaVersion", "kind", "sequence", "previousFrameSha256",
                    "deliveryCount", "rawBodyBytes", "uniqueBodyCount",
                    "duplicateBodyCount",
                }
                if set(metadata) != expected_fields or body:
                    raise KiekerSpoolError("spool terminal frame fields differ")
                count_fields = (
                    "deliveryCount", "rawBodyBytes", "uniqueBodyCount",
                    "duplicateBodyCount",
                )
                if any(type(metadata.get(field)) is not int or metadata[field] < 0
                       for field in count_fields):
                    raise KiekerSpoolError("spool terminal counters are not integers")
                if (metadata["uniqueBodyCount"] > metadata["deliveryCount"]
                        or metadata["duplicateBodyCount"]
                        != metadata["deliveryCount"] - metadata["uniqueBodyCount"]):
                    raise KiekerSpoolError("spool terminal counters are impossible")
                if terminal is not None:
                    raise KiekerSpoolError("spool contains more than one terminal frame")
                terminal = metadata
                report["terminalDigestSha256"] = computed_digest.hex()
                report["sealed"] = True
                if offset != len(raw):
                    raise KiekerSpoolError("spool contains bytes after its terminal frame")
            else:
                raise KiekerSpoolError("spool frame kind is invalid")
            previous_digest = computed_digest.hex()
        report["uniqueBodyCount"] = len(body_hashes)
        report["duplicateBodyCount"] = report["deliveryCount"] - len(body_hashes)
        if terminal is None:
            blockers.append("spool has no terminal seal")
        else:
            expected_terminal = {
                "deliveryCount": report["deliveryCount"],
                "rawBodyBytes": report["rawBodyBytes"],
                "uniqueBodyCount": report["uniqueBodyCount"],
                "duplicateBodyCount": report["duplicateBodyCount"],
            }
            if any(terminal.get(key) != value for key, value in expected_terminal.items()):
                blockers.append("spool terminal counters differ from replay")
        if report["duplicateBodyCount"]:
            blockers.append(
                f"spool contains {report['duplicateBodyCount']} duplicate raw body deliveries"
            )
    except (OSError, ValueError, TypeError, KiekerSpoolError) as exc:
        blockers.append(f"spool replay failed: {type(exc).__name__}: {exc}")
    report["complete"] = bool(report["sealed"] and not blockers)
    return bodies, report


# ── Low-level readers (big-endian) ──────────────────────────────────────────
class _Reader:
    """Position-tracking big-endian reader over a bytes buffer."""

    __slots__ = ("buf", "pos", "end")

    def __init__(self, buf: bytes, start: int = 0, end: int | None = None):
        self.buf = buf
        self.pos = start
        self.end = len(buf) if end is None else end

    def remaining(self) -> int:
        return self.end - self.pos

    def int32(self) -> int:
        if self.pos + 4 > self.end:
            raise EOFError("int32 past end")
        v = struct.unpack_from(">i", self.buf, self.pos)[0]
        self.pos += 4
        return v

    def int64(self) -> int:
        if self.pos + 8 > self.end:
            raise EOFError("int64 past end")
        v = struct.unpack_from(">q", self.buf, self.pos)[0]
        self.pos += 8
        return v

    def varint(self) -> int:
        """VariableLengthEncoding.decodeInt: 7 bits/byte, MSB=continuation.

        Mirrors the decompiled decoder: the final byte is the one whose value is
        >= 0 (top bit clear); its 7 low bits are OR'd in at the current shift.
        """
        result = 0
        shift = 0
        while True:
            if self.pos >= self.end:
                raise EOFError("varint past end")
            b = self.buf[self.pos]
            self.pos += 1
            if b < 0x80:                      # last byte (top bit clear)
                result |= b << shift
                break
            result |= (b & 0x7F) << shift
            shift += 7
            if shift > 28:
                raise ValueError("varint too long")
        return result

    def raw(self, n: int) -> bytes:
        if n < 0:
            raise ValueError("negative raw length")
        if self.pos + n > self.end:
            raise EOFError("raw past end")
        b = self.buf[self.pos:self.pos + n]
        self.pos += n
        return b


# ── String registry ─────────────────────────────────────────────────────────
def parse_string_registry(reader: _Reader) -> list[str]:
    """[count varint] then count * ([byteLen varint][UTF-8 bytes]).

    Registry id of a string == its 0-based index in the returned list.
    """
    count = reader.varint()
    strings: list[str] = []
    for _ in range(count):
        blen = reader.varint()
        strings.append(reader.raw(blen).decode("utf-8", errors="strict"))
    return strings


class _ValueReader:
    """Field reader over the records region using a resolved string registry."""

    __slots__ = ("r", "registry")

    def __init__(self, reader: _Reader, registry: list[str]):
        self.r = reader
        self.registry = registry

    def string(self) -> str:
        sid = self.r.int32()
        if 0 <= sid < len(self.registry):
            return self.registry[sid]
        raise ValueError(f"string registry id out of range: {sid}")

    def long(self) -> int:
        return self.r.int64()

    def int(self) -> int:
        return self.r.int32()

    def string_array(self) -> list[str]:
        n = self.r.int32()
        if n < 0:
            raise ValueError(f"negative string-array length: {n}")
        return [self.string() for _ in range(n)]


# ── Container parse ─────────────────────────────────────────────────────────
class ContainerParseError(Exception):
    pass


def parse_container(body: bytes) -> list[dict]:
    """Parse one AMQP message body (a Kieker binary container) into raw record
    dicts. Raises ContainerParseError on a malformed frame; per-record errors
    inside a valid frame are surfaced as records with ``_ok=False``.
    """
    if len(body) < 12:
        raise ContainerParseError(f"body too short ({len(body)} bytes)")

    head = _Reader(body)
    cid = head.int32()
    fid = head.int32()
    if cid != CONTAINER_IDENTIFIER:
        raise ContainerParseError(
            f"bad container id {cid} (want {CONTAINER_IDENTIFIER})")
    if fid != FORMAT_IDENTIFIER:
        raise ContainerParseError(
            f"bad format id {fid} (want {FORMAT_IDENTIFIER})")

    records_len = struct.unpack_from(">i", body, len(body) - 4)[0]
    rec_start = 8
    rec_end = 8 + records_len
    if records_len < 0 or rec_end < rec_start:
        raise ContainerParseError(
            f"negative/overlapping recordsLength {records_len}")
    if rec_end > len(body) - 4:
        raise ContainerParseError(
            f"recordsLength {records_len} exceeds body {len(body)}")

    # string registry lives between the records region and the trailing int32
    reg_reader = _Reader(body, rec_end, len(body) - 4)
    try:
        registry = parse_string_registry(reg_reader)
        if reg_reader.remaining() != 0:
            raise ValueError(
                f"{reg_reader.remaining()} trailing string-registry bytes")
    except (EOFError, UnicodeDecodeError, ValueError) as exc:
        raise ContainerParseError(f"malformed string registry: {exc}") from exc

    out: list[dict] = []
    rr = _Reader(body, rec_start, rec_end)
    while rr.remaining() >= 12:
        rec_pos = rr.pos
        try:
            class_id = rr.int32()
            logging_ts = rr.int64()
            if not 0 <= class_id < len(registry):
                raise ValueError(
                    f"record class registry id out of range: {class_id}")
            class_name = registry[class_id]
            rec = _parse_record(rr, _ValueReader(rr, registry),
                                 class_name, logging_ts)
            rec["_ok"] = True
            out.append(rec)
        except Exception as exc:  # noqa: BLE001 - never crash the stream
            out.append({"_ok": False, "_class": None, "_pos": rec_pos,
                        "_err": f"{type(exc).__name__}: {exc}"})
            break  # a mis-parsed record desyncs the rest of the region
    if rr.remaining() != 0:
        raise ContainerParseError(
            f"{rr.remaining()} unconsumed records-region bytes")
    return out


# A rejected container is otherwise an anonymous counter: ``containers_bad``
# says one body was discarded but not which container emitted it, when, or
# whether anything measurable went with it (F-ADH-084). These helpers turn the
# counter into typed evidence so a gate can decide instead of guess. They never
# change a parse outcome and never resurrect a discarded record.
CONTAINER_ID_PATTERN = re.compile(r"[0-9a-f]{12}|[0-9a-f]{64}")
# Kieker record classes that carry no execution and therefore no measurement.
# ``KiekerMetadataRecord`` is the monitoring controller's own startup banner
# (version/controller/hostname/experiment/timeUnit); this parser deliberately
# refuses to deserialize it, which is why a container carrying one is rejected.
NON_EXECUTION_RECORD_CLASSES = frozenset({
    "kieker.common.record.misc.KiekerMetadataRecord",
})


def container_parse_diagnostic(body: bytes, *, sequence: int) -> dict:
    """Describe ONE body that :func:`parse_container` rejects.

    Everything reported is read back out of the rejected bytes themselves: the
    record-class names the container declared, how many *execution* records
    parsed successfully before the desync (i.e. how much measurable telemetry
    the rejection discards), the earliest logging timestamp, and the container
    identifiers named in the string registry. A field is ``None``/empty only
    when the bytes genuinely do not carry it.
    """

    try:
        parse_container(body)
    except ContainerParseError as exc:
        error = str(exc)
    else:  # pragma: no cover - callers only pass rejected bodies
        raise ValueError("container parses cleanly and has no diagnostic")

    diagnostic = {
        "schemaVersion": 1,
        "sequence": int(sequence),
        "bodyBytes": len(body),
        "bodySha256": hashlib.sha256(body).hexdigest(),
        "error": error,
        "recordClasses": [],
        "parsedExecutionRecords": 0,
        "loggingTimestampNs": None,
        "registryContainerIds": [],
    }
    registry: list[str] = []
    try:
        records_len = struct.unpack_from(">i", body, len(body) - 4)[0]
        rec_start, rec_end = 8, 8 + records_len
        if records_len < 0 or rec_end > len(body) - 4:
            return diagnostic
        registry = parse_string_registry(_Reader(body, rec_end, len(body) - 4))
    except Exception:  # noqa: BLE001 - a diagnostic must never raise
        return diagnostic
    diagnostic["registryContainerIds"] = sorted(
        {name for name in registry if CONTAINER_ID_PATTERN.fullmatch(name)}
    )
    classes: list[str] = []
    timestamps: list[int] = []
    executions = 0
    rr = _Reader(body, rec_start, rec_end)
    while rr.remaining() >= 12:
        try:
            class_id = rr.int32()
            logging_ts = rr.int64()
            if not 0 <= class_id < len(registry):
                break
            class_name = registry[class_id]
            classes.append(class_name)
            timestamps.append(logging_ts)
            _parse_record(rr, _ValueReader(rr, registry), class_name, logging_ts)
        except Exception:  # noqa: BLE001 - the desync point is the diagnostic
            break
        executions += 1
    diagnostic["recordClasses"] = classes
    diagnostic["parsedExecutionRecords"] = executions
    if timestamps:
        diagnostic["loggingTimestampNs"] = min(timestamps)
    return diagnostic


def spool_container_parse_diagnostics(path: Path) -> list[dict]:
    """Replay one sealed spool and describe every body the parser rejects.

    Reads only retained bytes, so every validator can recompute the identical
    list without trusting a producer-authored summary.
    """

    bodies, report = replay_kieker_spool(path)
    if report["complete"] is not True:
        raise KiekerSpoolError(
            f"spool is incomplete: {report['blockers']}"
        )
    diagnostics: list[dict] = []
    for sequence, body in enumerate(bodies, start=1):
        try:
            parse_container(body)
        except ContainerParseError:
            diagnostics.append(container_parse_diagnostic(body, sequence=sequence))
    return diagnostics


def _parse_record(rr: _Reader, vr: _ValueReader, class_name: str,
                  logging_ts: int) -> dict:
    """Deserialize an OperationExecutionRecord (or WithParameters subclass)."""
    is_oer = class_name == OER_CLASS
    is_oewpr = class_name == OEWPR_CLASS
    if not (is_oer or is_oewpr):
        raise ValueError(f"unhandled record class {class_name!r}")

    operation_signature = vr.string()
    session_id = vr.string()
    trace_id = vr.long()
    tin = vr.long()
    tout = vr.long()
    hostname = vr.string()
    eoi = vr.int()
    ess = vr.int()

    rec = {
        "_class": class_name,
        "operationSignature": operation_signature,
        "sessionId": session_id,
        "traceId": trace_id,
        "tin": tin,
        "tout": tout,
        "hostname": hostname,
        "eoi": eoi,
        "ess": ess,
        "loggingTimestamp": logging_ts,
    }
    _validate_native_identity_and_timing(rec)
    if is_oewpr:
        rec["parameterTypes"] = vr.string_array()
        rec["parameterValues"] = vr.string_array()
        rec["returnType"] = vr.string()
        rec["returnValue"] = vr.string()
    return rec


def _validate_native_identity_and_timing(record: dict) -> None:
    for field in ("traceId", "tin", "tout"):
        if type(record.get(field)) is not int:
            raise ValueError(f"native {field} must be an integer")
    if record["traceId"] == -1:
        raise ValueError("native traceId uses the Kieker no-trace sentinel -1")
    if record["tout"] < record["tin"]:
        raise ValueError("native tout precedes tin")


# ── Record -> unified event ─────────────────────────────────────────────────
_SIG_METHOD = re.compile(r'([\w\.$<>\[\]]+)\(')


def _operation_name(signature: str) -> str:
    """`public X a.b.C.method(args)` -> `C.method` (matches scraper convention)."""
    m = _SIG_METHOD.search(signature)
    method_path = m.group(1) if m else signature
    parts = method_path.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else method_path


class ServiceAttributionError(ValueError):
    """The runtime host-to-service evidence is malformed or contradictory."""


def _normalise_host(value: str) -> str:
    host = value.strip().lower()
    return host.removeprefix("sha256:")


def _bind_host_alias(mapping: dict[str, str], alias: str, service: str) -> None:
    alias = _normalise_host(alias)
    if not alias:
        raise ServiceAttributionError("runtime hostname alias is empty")
    if not isinstance(service, str) or not service.strip():
        raise ServiceAttributionError(f"runtime service for {alias!r} is empty")
    service = service.strip()
    if service not in CANONICAL_RUNTIME_SERVICES:
        raise ServiceAttributionError(
            f"runtime service is not canonical for {alias!r}: {service!r}")
    previous = mapping.get(alias)
    if previous is not None and previous != service:
        raise ServiceAttributionError(
            f"runtime hostname alias collision for {alias}: {previous} != {service}")
    mapping[alias] = service


def runtime_host_service_map(document: dict) -> dict[str, str]:
    """Derive exact/full and Docker-short hostname aliases from runtime proof.

    Docker's default container hostname is the first twelve characters of its
    native 64-hex container id. Both forms are bound, and a prefix collision is
    rejected rather than resolved by iteration order.
    """
    if (not isinstance(document, dict) or document.get("schemaVersion") != 1
            or not isinstance(document.get("services"), dict)
            or not document["services"]):
        raise ServiceAttributionError(
            "runtime image proof schema/services are invalid")
    mapping: dict[str, str] = {}
    for service, item in sorted(document["services"].items()):
        if not isinstance(service, str) or not isinstance(item, dict):
            raise ServiceAttributionError("runtime service entry is malformed")
        if service not in CANONICAL_RUNTIME_SERVICES:
            raise ServiceAttributionError(
                f"runtime service is not a canonical TeaStore service: {service!r}")
        container_id = item.get("containerId")
        if not isinstance(container_id, str) or not CONTAINER_ID_RE.fullmatch(container_id):
            raise ServiceAttributionError(
                f"runtime container id is invalid for {service!r}")
        _bind_host_alias(mapping, container_id, service)
        _bind_host_alias(mapping, container_id[:12], service)
    return mapping


def load_runtime_host_service_map(path: Path) -> dict[str, str]:
    def no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        document: dict = {}
        for key, value in pairs:
            if key in document:
                raise ServiceAttributionError(
                    f"duplicate JSON key in runtime image proof: {key!r}")
            document[key] = value
        return document

    def reject_nonfinite(value: str) -> None:
        raise ServiceAttributionError(
            f"non-finite JSON value in runtime image proof: {value}")

    try:
        document = json.loads(
            path.read_text(),
            object_pairs_hook=no_duplicate_keys,
            parse_constant=reject_nonfinite,
        )
    except (OSError, json.JSONDecodeError, ServiceAttributionError) as exc:
        raise ServiceAttributionError(
            f"cannot read runtime image proof {path}: {exc}") from exc
    return runtime_host_service_map(document)


def _merge_host_service_maps(*maps: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for mapping in maps:
        if not isinstance(mapping, dict):
            raise ServiceAttributionError("runtime host map is not an object")
        for alias, service in mapping.items():
            if not isinstance(alias, str):
                raise ServiceAttributionError("runtime hostname alias is not a string")
            _bind_host_alias(merged, alias, service)
    return merged


def _canonical_host_aliases() -> dict[str, str]:
    return {
        service: service for service in sorted(CANONICAL_RUNTIME_SERVICES)
    }


def _canonical_json_sha256(document: dict) -> str:
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def frozen_attribution_configuration(
    runtime_host_aliases: dict[str, str],
    explicit_host_aliases: dict[str, str] | None = None,
) -> tuple[dict, str]:
    """Return the complete, canonically hashed service-attribution inputs.

    Candidate collection has exactly two host-attribution sources: the fixed
    canonical TeaStore aliases and aliases derived from ``runtime-images.json``.
    ``explicit_host_aliases`` remains visible for local parser fixtures; a
    candidate replayer requires it to be empty and therefore cannot silently
    admit an injected alias.
    """

    explicit = explicit_host_aliases or {}
    canonical = _canonical_host_aliases()
    runtime = _merge_host_service_maps(runtime_host_aliases)
    explicit = _merge_host_service_maps(explicit)
    effective = _merge_host_service_maps(canonical, runtime, explicit)
    configuration = {
        "schemaVersion": 1,
        "serviceRegex": DEFAULT_SERVICE_REGEX,
        "serviceMap": dict(sorted(DEFAULT_SERVICE_MAP.items())),
        "canonicalHostAliases": canonical,
        "runtimeHostAliases": dict(sorted(runtime.items())),
        "explicitHostAliases": dict(sorted(explicit.items())),
        "effectiveHostAliases": dict(sorted(effective.items())),
    }
    return configuration, _canonical_json_sha256(configuration)


def _strict_service_map_from_environment(value: str) -> dict:
    def no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, item in pairs:
            if key in result:
                raise ServiceAttributionError(
                    f"duplicate key in SUT_TRACE_SERVICE_MAP: {key!r}"
                )
            result[key] = item
        return result

    try:
        parsed = json.loads(value, object_pairs_hook=no_duplicate_keys)
    except (json.JSONDecodeError, ServiceAttributionError) as exc:
        raise ServiceAttributionError(
            f"SUT_TRACE_SERVICE_MAP is not valid strict JSON: {exc}"
        ) from exc
    if parsed != DEFAULT_SERVICE_MAP:
        raise ServiceAttributionError(
            "SUT_TRACE_SERVICE_MAP differs from the frozen collector map"
        )
    return parsed


def _require_frozen_attribution_environment() -> None:
    configured_regex = os.getenv("SUT_TRACE_SERVICE_REGEX")
    if configured_regex is not None and configured_regex != DEFAULT_SERVICE_REGEX:
        raise ServiceAttributionError(
            "SUT_TRACE_SERVICE_REGEX differs from the frozen collector regex"
        )
    configured_map = os.getenv("SUT_TRACE_SERVICE_MAP")
    if configured_map is not None:
        _strict_service_map_from_environment(configured_map)
    if "SUT_TRACE_HOST_SERVICE_MAP" in os.environ:
        raise ServiceAttributionError(
            "SUT_TRACE_HOST_SERVICE_MAP is forbidden; runtime-images.json is the "
            "only non-canonical host-alias source"
        )


def _declaring_method_path(signature: str) -> str | None:
    """Return the declaring-class-and-method token immediately before ``(``.

    Searching the whole signature for a TeaStore package is wrong whenever the
    return type is itself a TeaStore class. The method token is the syntactic
    location that identifies the executing code.
    """
    match = _SIG_METHOD.search(signature)
    return match.group(1) if match else None


def _signature_service(signature: str, svc_re: re.Pattern,
                       svc_map: dict) -> tuple[str | None, str | None]:
    declaring_method = _declaring_method_path(signature)
    match = svc_re.search(declaring_method or "")
    if not match:
        return None, None
    package = match.group(1)
    service = package
    for substring, canonical in svc_map.items():
        if substring in package:
            service = canonical
            break
    return service, package


def _service_attribution(signature: str, hostname: str, svc_re: re.Pattern,
                         svc_map: dict, host_service_map: dict[str, str]) -> dict:
    signature_service, signature_package = _signature_service(
        signature, svc_re, svc_map)
    runtime_service = host_service_map.get(_normalise_host(hostname))
    shared_signature = signature_package in SHARED_SIGNATURE_PACKAGES
    errors: list[str] = []

    if runtime_service is not None:
        service = runtime_service
        if signature_service is None:
            status = "runtime-host-only"
        elif signature_service == runtime_service:
            status = "runtime-host-and-signature-agree"
        elif shared_signature:
            # registryclient/entities are libraries executed in several service
            # containers; their package cannot override observed runtime identity.
            status = "runtime-host-overrides-shared-signature"
        else:
            status = "runtime-host-signature-conflict"
            errors.append("runtime-host-signature-conflict")
    elif signature_service is None:
        service = "unknown"
        status = "unresolved"
        errors.append("runtime-host-and-declaring-signature-unresolved")
    elif shared_signature:
        service = "unknown"
        status = "ambiguous-shared-signature"
        errors.append("shared-declaring-package-without-runtime-host-map")
    else:
        service = signature_service
        status = "declaring-signature-fallback"
        errors.append("runtime-host-unmapped")

    return {
        "service": service,
        "signature_package": signature_package,
        "signature_service": signature_service,
        "runtime_host_service": runtime_service,
        "service_attribution_status": status,
        "service_attribution_errors": errors,
    }


def _record_to_event(record: dict, svc_re: re.Pattern, svc_map: dict,
                     host_service_map: dict[str, str], message_sha1: str) -> dict:
    _validate_native_identity_and_timing(record)
    trace_id = record["traceId"]
    eoi, ess = record["eoi"], record["ess"]
    signature = record["operationSignature"]
    tin, tout = record["tin"], record["tout"]
    attribution = _service_attribution(
        signature, record.get("hostname", ""), svc_re, svc_map,
        host_service_map)
    return {
        # REQUIRED_FIELDS (collectors/__init__.py)
        "timestamp": tin / 1e9,
        # Retain a replay-stable producer observation timestamp from the raw
        # Kieker record. Falling back to tin keeps synthetic/legacy records
        # deterministic when their logging timestamp is the zero sentinel.
        "collector_timestamp": (
            (record.get("loggingTimestamp") or tin) / 1e9
        ),
        "service": attribution.pop("service"),
        "operation": _operation_name(signature),
        "trace_id": str(trace_id),
        "source": "kieker_native",
        # OPTIONAL_FIELDS — span context derived globally from native eoi/ess
        "span_id": f"{trace_id}:{eoi}",
        "parent_span_id": None,
        "status_code": None,
        "duration_s": (tout - tin) / 1e9,
        "args": list(record.get("parameterTypes") or []),
        "full_signature": signature,
        "message_sha1": message_sha1,
        "signature_sha1": hashlib.sha1(signature.encode("utf-8")).hexdigest(),
        "signature_ordinal": None,
        # Native identity/provenance and explicit inference state.
        "kieker_trace_id": trace_id,
        "eoi": eoi,
        "ess": ess,
        "tin": tin,
        "tout": tout,
        "session_id": record.get("sessionId", ""),
        "hostname": record.get("hostname", ""),
        "native_record_class": record.get("_class"),
        "parent_resolution": "unresolved",
        "correlation_errors": [],
        "correlation_warnings": [],
        "native_identity_occurrences": 1,
        "native_identity_message_bodies": 1,
        **attribution,
    }


def _native_identity_fingerprint(event: dict) -> tuple:
    return (
        event["ess"], event["tin"], event["tout"], event["hostname"],
        event["full_signature"], event["session_id"],
        event["native_record_class"],
    )


def collect_trace_eois(events: object) -> dict:
    """Group execution-order indices by trace, exactly as every reader must.

    The collector holds these dictionaries in memory while the independent
    validators reload them from JSON, where the integer trace id is
    ``kieker_trace_id`` and ``trace_id`` is its string mirror. Sharing one
    extraction is what keeps the producer and the three separate validators
    that recompute this summary from drifting apart.
    """

    trace_eois: dict = {}
    for event in events:
        eoi = event.get("eoi")
        if not isinstance(eoi, int) or isinstance(eoi, bool) or eoi < 0:
            continue
        trace_id = event.get("kieker_trace_id", event.get("trace_id"))
        trace_eois.setdefault(trace_id, set()).add(eoi)
    return trace_eois


def trace_completeness(trace_eois: dict) -> dict:
    """Single authority for native execution-order-index completeness.

    Density is measured inside each trace's own observed index window rather
    than from zero. A posture that forbids the entry-point activation group
    leaves nothing to open or close a request trace, so Kieker's index runs for
    the life of a worker thread instead of resetting per request, and the queue
    purge that separates warmup from measurement then discards each thread's
    earliest indices. A retained stream therefore begins mid-sequence through
    no fault of the run.

    The check keeps its power where it matters: a hole strictly inside the
    observed window still means telemetry was lost between the first and last
    retained index, and still fails closed. The offset is not discarded either
    - it is reported as ``tracesNotStartingAtZero`` so the shortfall stays
    visible evidence rather than becoming an unrecorded assumption.
    """

    traces_with_gaps = 0
    missing_eoi_count = 0
    traces_not_starting_at_zero = 0
    for eois in trace_eois.values():
        if not eois:
            continue
        first = min(eois)
        if first != 0:
            traces_not_starting_at_zero += 1
        missing = set(range(first, max(eois) + 1)) - eois
        if missing:
            traces_with_gaps += 1
            missing_eoi_count += len(missing)
    return {
        "traces": len(trace_eois),
        "tracesWithEoiGaps": traces_with_gaps,
        "missingEoiCount": missing_eoi_count,
        "tracesNotStartingAtZero": traces_not_starting_at_zero,
    }


# The activation group(s) whose sensor opens and closes a request trace (the
# HTTP entry point). When none of these is woven, no execution starts at native
# stack depth 0, so each trace's shallowest observed execution legitimately has
# no observed parent. This is TeaStore-specific and is the single place to change
# if the entry point ever moves.
TRACE_ROOT_ACTIVATION_GROUPS = frozenset({"aspectj:webui"})
UNWOVEN_ROOT_PARENT_ERROR = "missing-parent-at-depth-0"

# F-ADH-083: the harness's wait_ready() curls the WebUI /status page after every
# fault recovery. StatusServlet.isImageFinished / isRecommenderFinished reach the
# image and recommender readiness endpoints through
# ServiceLoadBalancer.multicastRESTOperation, which dispatches on
# servers.parallelStream(): Kieker's control-flow context is thread-local and is
# lost on the fork-join worker, so the callee starts a fresh trace id while still
# carrying eoi>=1/ess>=1. No depth-0 record ever existed to lose. (The same
# page's isDatabaseFinished uses the same-thread loadBalanceRESTOperation and
# propagates correctly, and its target is excluded from weaving by aop.xml, so it
# is deliberately NOT declared.) The candidate-pilot v1 descriptor is frozen by
# candidate_pilot.frozen_descriptor() and cannot be amended in place, so these
# constants ARE the preregistration, bound into every receipt by the framework
# commit; tests/test_kieker_native_correlation.py pins their contents.
READINESS_PROBE_OPERATIONS = frozenset({
    "ImageProviderEndpoint.isFinished",
    "TrainEndpoint.isReady",
})
READINESS_PROBE_CALLERS = frozenset({
    "StatusServlet.isImageFinished",
    "StatusServlet.isRecommenderFinished",
})


def probe_orphan_root_indices(events: object) -> frozenset:
    """Indices of unwoven-root events that are the harness's own readiness probes.

    A subset of :func:`count_unwoven_root_parents`. An event qualifies only when
    ALL hold: (1) its sole correlation error is the missing depth-0 parent and
    its parent resolution is ``missing``; (2) its operation is in
    :data:`READINESS_PROBE_OPERATIONS`; (3) no event of its trace has
    ``eoi == 0`` or ``ess == 0``; (4) every shallowest execution of its trace
    is a declared probe, so no workload execution shares the trace; (5) a
    retained execution of a :data:`READINESS_PROBE_CALLERS` operation encloses
    its start time (``caller.tin <= tin <= caller.tout``), which is what
    separates "never minted a root" from "lost the root": a lost root leaves no
    enclosing status-page caller. Anything else stays a missing root.
    """
    by_trace: dict = {}
    caller_windows = []
    for index, event in enumerate(events):
        trace = event.get("kieker_trace_id", event.get("trace_id"))
        by_trace.setdefault(trace, []).append((index, event))
        if (event.get("operation") in READINESS_PROBE_CALLERS
                and _is_int(event.get("tin")) and _is_int(event.get("tout"))):
            caller_windows.append((event["tin"], event["tout"]))
    accepted = set()
    for members in by_trace.values():
        if any(e.get("eoi") == 0 or e.get("ess") == 0 for _, e in members):
            continue
        depths = [e.get("ess") for _, e in members if _is_int(e.get("ess"))]
        if not depths:
            continue
        shallowest = min(depths)
        roots = [(i, e) for i, e in members if e.get("ess") == shallowest]
        if any(e.get("operation") not in READINESS_PROBE_OPERATIONS for _, e in roots):
            continue
        for index, event in roots:
            errors = event.get("correlation_errors") or []
            tin = event.get("tin")
            if (errors and all(error == UNWOVEN_ROOT_PARENT_ERROR for error in errors)
                    and event.get("parent_resolution") == "missing"
                    and _is_int(tin)
                    and any(low <= tin <= high for low, high in caller_windows)):
                accepted.add(index)
    return frozenset(accepted)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def count_probe_orphan_roots(events: object) -> int:
    """``len(probe_orphan_root_indices(events))``; see that function (F-ADH-083)."""
    return len(probe_orphan_root_indices(list(events)))


def count_unwoven_root_parents(events: object) -> int:
    """Count events whose only correlation error is a missing depth-0 parent.

    In a posture that does not weave the trace-starting (entry-point) sensor,
    the shallowest observed execution of each trace has no observed root and
    carries exactly this one error. A missing parent at any deeper depth, or any
    other correlation error alongside it, is a genuine defect and is excluded
    here so it still counts against ``eventsWithCorrelationErrors``.
    """
    count = 0
    for event in events:
        errors = event.get("correlation_errors") or []
        if errors and all(error == UNWOVEN_ROOT_PARENT_ERROR for error in errors):
            count += 1
    return count


def entry_point_woven(closure_groups: object) -> bool:
    """True when the woven closure includes a trace-starting entry-point sensor.

    When it does not, a single :data:`UNWOVEN_ROOT_PARENT_ERROR` per trace root
    is expected rather than data loss; see :func:`count_unwoven_root_parents`.
    An unknown closure is treated as woven so the gate stays strict when it
    cannot prove the entry point was deliberately omitted.
    """
    if closure_groups is None:
        return True
    return bool(TRACE_ROOT_ACTIVATION_GROUPS & set(closure_groups))


class NativeTraceCorrelator:
    """Accumulate native records and repair parent links across AMQP bodies.

    Returned event dictionaries remain owned by this correlator and are updated
    in place when a previously absent ancestor arrives. A caller that aggregates
    the returned dictionaries therefore receives the globally repaired result.

    Correlation fields are only defined at flush points: ``add_records`` stages
    records and marks their traces dirty, and ``flush`` recomputes each dirty
    trace exactly once. Every read path (``report`` and the collector's read
    methods) flushes first, so callers observe the same terminal state as the
    previous eager per-message recompute.
    """

    def __init__(self, svc_re: re.Pattern, svc_map: dict,
                 host_service_map: dict[str, str]):
        self.svc_re = svc_re
        self.svc_map = svc_map
        self.host_service_map = host_service_map
        self.events: list[dict] = []
        self._by_trace: dict[int, list[dict]] = {}
        self._dirty: set[int] = set()

    def add_records(self, records: list[dict], message_sha1: str) -> list[dict]:
        added: list[dict] = []
        for record in records:
            if not record.get("_ok") or "traceId" not in record:
                continue
            event = _record_to_event(
                record, self.svc_re, self.svc_map, self.host_service_map,
                message_sha1)
            self.events.append(event)
            self._by_trace.setdefault(record["traceId"], []).append(event)
            self._dirty.add(record["traceId"])
            added.append(event)
        return added

    def flush(self) -> None:
        """Recompute correlation for every trace touched since the last flush.

        Deferring the per-trace recompute keeps ingestion linear in the number
        of records (F-ADH-060); the result is value-identical to recomputing on
        every message because ``_recompute_trace`` fully overwrites every
        correlation field of every event in the trace.
        """
        for trace_id in self._dirty:
            self._recompute_trace(trace_id)
        self._dirty.clear()

    def _recompute_trace(self, trace_id: int) -> None:
        trace_events = self._by_trace[trace_id]
        by_eoi: dict[int, list[dict]] = {}
        invalid_eoi: list[dict] = []
        for event in trace_events:
            if isinstance(event.get("eoi"), int):
                by_eoi.setdefault(event["eoi"], []).append(event)
            else:
                invalid_eoi.append(event)

        root_eois = {
            eoi for eoi, group in by_eoi.items()
            if len({_native_identity_fingerprint(event) for event in group}) == 1
            and group[0].get("ess") == 0
        }
        trace_errors = ["multiple-native-roots"] if len(root_eois) > 1 else []
        stack: dict[int, str | None] = {}

        for event in invalid_eoi:
            event.update({
                "parent_span_id": None,
                "parent_resolution": "ambiguous",
                "correlation_errors": [*trace_errors, "invalid-native-eoi"],
                "correlation_warnings": [],
            })

        for eoi in sorted(by_eoi):
            group = by_eoi[eoi]
            fingerprints = {_native_identity_fingerprint(event) for event in group}
            conflict = len(fingerprints) != 1
            message_count = len({event["message_sha1"] for event in group})
            warnings = (["duplicate-native-identity-observation"]
                        if len(group) > 1 and not conflict else [])
            for event in group:
                event.update({
                    "parent_span_id": None,
                    "parent_resolution": "unresolved",
                    "correlation_errors": list(trace_errors),
                    "correlation_warnings": list(warnings),
                    "native_identity_occurrences": len(group),
                    "native_identity_message_bodies": message_count,
                })

            representative = group[0]
            ess = representative.get("ess")
            if (not isinstance(ess, int) or ess < 0 or eoi < 0):
                for event in group:
                    event["parent_resolution"] = "ambiguous"
                    event["correlation_errors"].append("invalid-native-eoi-or-ess")
                continue

            # A new record at depth d closes the preceding record at d and every
            # deeper record. This prevents a malformed depth jump from binding
            # to a stale parent left over from an earlier branch.
            for depth in [depth for depth in stack if depth >= ess]:
                del stack[depth]

            if conflict:
                for event in group:
                    event["parent_resolution"] = "ambiguous"
                    event["correlation_errors"].append(
                        "conflicting-native-identity")
                stack[ess] = None
                continue

            if ess == 0:
                for event in group:
                    event["parent_span_id"] = ""
                    event["parent_resolution"] = (
                        "ambiguous" if trace_errors else "root")
                stack[0] = representative["span_id"]
                continue

            if ess - 1 not in stack:
                for event in group:
                    event["parent_resolution"] = "missing"
                    event["correlation_errors"].append(
                        f"missing-parent-at-depth-{ess - 1}")
            elif stack[ess - 1] is None:
                for event in group:
                    event["parent_resolution"] = "ambiguous"
                    event["correlation_errors"].append(
                        "ambiguous-parent-native-identity")
            else:
                for event in group:
                    event["parent_span_id"] = stack[ess - 1]
                    event["parent_resolution"] = "resolved"
            stack[ess] = representative["span_id"]

    def report(self) -> dict:
        self.flush()
        parent_states: dict[str, int] = {}
        attribution_states: dict[str, int] = {}
        correlation_error_events = 0
        correlation_warning_events = 0
        attribution_error_events = 0
        for event in self.events:
            parent = event["parent_resolution"]
            attribution = event["service_attribution_status"]
            parent_states[parent] = parent_states.get(parent, 0) + 1
            attribution_states[attribution] = attribution_states.get(attribution, 0) + 1
            correlation_error_events += bool(event["correlation_errors"])
            correlation_warning_events += bool(event["correlation_warnings"])
            attribution_error_events += bool(event["service_attribution_errors"])
        return {
            "events": len(self.events),
            "parentResolution": dict(sorted(parent_states.items())),
            "serviceAttribution": dict(sorted(attribution_states.items())),
            "eventsWithCorrelationErrors": correlation_error_events,
            "eventsWithUnwovenRootParent": count_unwoven_root_parents(self.events),
            "eventsWithProbeOrphanRoot": count_probe_orphan_roots(self.events),
            "eventsWithCorrelationWarnings": correlation_warning_events,
            "eventsWithServiceAttributionErrors": attribution_error_events,
            "traceCompleteness": trace_completeness(
                collect_trace_eois(self.events)),
        }

    def finalize_report(self) -> dict:
        """Return terminal completeness; callers must invoke after queue drain."""
        return self.report()


def records_to_events(records: list[dict], svc_re: re.Pattern, svc_map: dict,
                      message_sha1: str,
                      host_service_map: dict[str, str] | None = None) -> list[dict]:
    """One-shot conversion for a complete record set.

    Live collection uses one persistent :class:`NativeTraceCorrelator`; callers
    of this helper must provide all messages for a trace together if they expect
    terminal parent resolution.
    """
    if host_service_map is None:
        host_service_map = {
            service: service for service in CANONICAL_RUNTIME_SERVICES
        }
    correlator = NativeTraceCorrelator(svc_re, svc_map, host_service_map)
    correlator.add_records(records, message_sha1)
    correlator.flush()
    return correlator.events


def collector_heartbeat_path(spool_path: Path) -> Path:
    """Single authority for the watchdog heartbeat's location beside a spool."""
    return Path(spool_path).with_name(Path(spool_path).name + ".heartbeat")


# ── AMQP transport (mirrors collect_kieker_traces.py) ───────────────────────
class KiekerNativeCollector:
    def __init__(self, runtime_images_path: Path | None = None,
                 host_service_map: dict[str, str] | None = None,
                 spool_path: Path | None = None):
        self.host = os.getenv("RABBITMQ_HOST", "localhost")
        self.port = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.user = os.getenv("RABBITMQ_USER", "admin")
        self.password = os.getenv("RABBITMQ_PASSWORD", "nimda")
        self.queue_name = os.getenv("RABBITMQ_QUEUE", "kieker")
        self.auto_ack = os.getenv("RABBITMQ_AUTO_ACK", "False").lower() in (
            "true", "1", "yes")

        _require_frozen_attribution_environment()
        self.svc_re = re.compile(DEFAULT_SERVICE_REGEX)
        self.svc_map = dict(DEFAULT_SERVICE_MAP)

        runtime_mapping = (
            load_runtime_host_service_map(runtime_images_path)
            if runtime_images_path is not None else {}
        )
        explicit_mapping = host_service_map or {}
        self.attribution_configuration, self.attribution_configuration_sha256 = (
            frozen_attribution_configuration(runtime_mapping, explicit_mapping)
        )
        self.host_service_map = dict(
            self.attribution_configuration["effectiveHostAliases"]
        )
        self.runtime_images_path = runtime_images_path
        self.correlator = NativeTraceCorrelator(
            self.svc_re, self.svc_map, self.host_service_map)
        if spool_path is not None and self.auto_ack:
            raise KiekerSpoolError(
                "durable spooling requires manual AMQP acknowledgement"
            )
        self.spool = KiekerBodySpool(spool_path) if spool_path is not None else None
        self.spool_path = Path(spool_path) if spool_path is not None else None
        self.heartbeat_path = (
            collector_heartbeat_path(self.spool_path)
            if self.spool_path is not None else None)
        self._spool_report: dict | None = None

        # parse accounting
        self.n_messages = 0
        self.n_containers_ok = 0
        self.n_containers_bad = 0
        self.n_records_ok = 0
        self.n_records_bad = 0

    def touch_heartbeat(self) -> None:
        """Prove liveness to the campaign's no-progress watchdog (F-ADH-061).

        The supervising parent kills this process when the heartbeat file's
        mtime stops advancing, so every data-proportional phase (drain, flush,
        terminal spool replay) must beat while it works.
        """
        if self.heartbeat_path is not None:
            self.heartbeat_path.touch()

    def purge_queue(self) -> int | None:
        """Purge the configured queue (mirrors KiekerScraper.purge_queue).

        Returns the purged message count, or None on error. Used by
        collect_empirical_data.py before a run so stale backlog from a previous
        experiment cannot leak into the new trace set.
        """
        import pika  # local import: only needed for the live path
        try:
            params = pika.ConnectionParameters(
                host=self.host, port=self.port,
                credentials=pika.PlainCredentials(self.user, self.password))
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue=self.queue_name, passive=True)
            result = channel.queue_purge(queue=self.queue_name)
            connection.close()
            return int(getattr(result, "method", result).message_count)
        except Exception as e:  # noqa: BLE001 - never crash the orchestrator
            print(f"⚠️  Could not purge RabbitMQ queue '{self.queue_name}': {e}",
                  file=sys.stderr)
            return None

    def consume_traces(self, max_messages: int = 500,
                       timeout: float = 1.0) -> list[dict]:
        """Poll-style consume for collect_empirical_data.py's consumer thread.

        Drop-in for KiekerScraper.consume_traces(): connect, drain up to
        max_messages (ack each), return unified-schema events, close. Any
        transport or spool failure closes the spool without a terminal seal and
        propagates the failure; partial events must never look like a completed
        collection.
        NOTE: shares the queue with the scraper — the orchestrator must run
        exactly ONE of the two (either/or dispatch), never both.
        """
        import pika  # local import: only needed for the live path
        self._require_durable_manual_ack()
        events: list[dict] = []
        try:
            params = pika.ConnectionParameters(
                host=self.host, port=self.port,
                credentials=pika.PlainCredentials(self.user, self.password))
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue=self.queue_name, passive=True)
            msg_count = 0
            for method, _props, body in channel.consume(
                    self.queue_name, inactivity_timeout=timeout,
                    auto_ack=self.auto_ack):
                self.touch_heartbeat()
                if method is None:            # inactivity timeout: queue drained
                    break
                msg_count += 1
                events.extend(self.handle_delivery(
                    channel, method, _props, bytes(body)
                ))
                if msg_count >= max_messages:
                    break
            try:
                channel.cancel()
            except Exception:
                pass
            connection.close()
            self.touch_heartbeat()
            self.correlator.flush()
            return events
        except KiekerSpoolError:
            if self.spool is not None:
                self.spool.close_unsealed()
            raise
        except Exception:  # noqa: BLE001 - fail closed on every transport failure
            if self.spool is not None:
                self.spool.close_unsealed()
            raise

    def consume(self, duration: float = 150.0, max_messages: int = 10_000_000,
                inactivity_timeout: float = 5.0) -> list[dict]:
        import pika  # local import: only needed for the live path
        self._require_durable_manual_ack()

        params = pika.ConnectionParameters(
            host=self.host, port=self.port,
            credentials=pika.PlainCredentials(self.user, self.password))
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.queue_declare(queue=self.queue_name, passive=True)
        print(f"consuming '{self.queue_name}' on {self.host}:{self.port} "
              f"for up to {duration:.0f}s", file=sys.stderr)

        events: list[dict] = []
        deadline = time.time() + duration
        try:
            for method, _props, body in channel.consume(
                    self.queue_name, inactivity_timeout=inactivity_timeout,
                    auto_ack=self.auto_ack):
                self.touch_heartbeat()
                if method is None:                    # inactivity timeout
                    if time.time() >= deadline:
                        break
                    continue
                events.extend(self.handle_delivery(
                    channel, method, _props, bytes(body)
                ))
                if self.n_messages >= max_messages or time.time() >= deadline:
                    break
            try:
                channel.cancel()
            except Exception:
                pass
        except Exception:
            if self.spool is not None:
                self.spool.close_unsealed()
            raise
        finally:
            connection.close()
        self.touch_heartbeat()
        self.correlator.flush()
        if self.spool is None or self.spool_path is None:  # pragma: no cover - guarded above
            raise KiekerSpoolError("collector lost its durable spool")
        self.touch_heartbeat()
        self.spool.seal()
        replayed_events, replay_report, replay_counts = replay_spooled_events(
            self.spool_path, self.svc_re, self.svc_map, self.host_service_map,
            progress=self.touch_heartbeat,
        )
        self._spool_report = replay_report
        live_counts = {
            "messages": self.n_messages,
            "containers_ok": self.n_containers_ok,
            "containers_bad": self.n_containers_bad,
            "records_ok": self.n_records_ok,
            "records_bad": self.n_records_bad,
        }
        if not replay_report["complete"]:
            raise KiekerSpoolError(
                f"terminal spool replay is incomplete: {replay_report['blockers']}"
            )
        if replay_counts != live_counts:
            raise KiekerSpoolError(
                f"terminal spool replay counts differ: {replay_counts} != {live_counts}"
            )
        if replayed_events != events:
            raise KiekerSpoolError("terminal spool replay differs from live correlated events")
        return replayed_events

    def _require_durable_manual_ack(self) -> None:
        if self.auto_ack:
            raise KiekerSpoolError("automatic acknowledgement is forbidden")
        if self.spool is None or self.spool_path is None:
            raise KiekerSpoolError(
                "manual acknowledgement requires an exclusive durable spool path"
            )

    def handle_delivery(self, channel: object, method: object,
                        properties: object | None, body: bytes) -> list[dict]:
        """Durably frame one exact delivery, then acknowledge, then parse it.

        The order is intentionally observable in tests. Any identity, write,
        or fsync failure propagates and therefore leaves the delivery unacked.
        An acknowledgement failure also propagates and prevents a terminal seal.
        """

        self._require_durable_manual_ack()
        if self.spool is None:  # pragma: no cover - guarded above
            raise KiekerSpoolError("collector lost its durable spool")
        identity = amqp_delivery_identity(method, properties)
        self.spool.append_delivery(body, identity)
        self.n_messages += 1
        try:
            channel.basic_ack(delivery_tag=getattr(method, "delivery_tag"))
        except Exception as exc:
            self.spool.close_unsealed()
            raise KiekerSpoolError(
                f"manual AMQP acknowledgement failed after durable framing: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        return self.handle_body(body)

    def handle_body(self, body: bytes) -> list[dict]:
        message_sha1 = hashlib.sha1(body).hexdigest()
        try:
            records = parse_container(body)
        except ContainerParseError:
            self.n_containers_bad += 1
            return []
        self.n_containers_ok += 1
        self.n_records_ok += sum(1 for r in records if r.get("_ok"))
        self.n_records_bad += sum(1 for r in records if not r.get("_ok"))
        return self.correlator.add_records(records, message_sha1)

    def correlated_events(self) -> list[dict]:
        """Return all observations; previously returned dicts are the same objects."""
        self.correlator.flush()
        return list(self.correlator.events)

    def stats(self) -> dict:
        total_rec = self.n_records_ok + self.n_records_bad
        total_cont = self.n_containers_ok + self.n_containers_bad
        result = {
            "messages": self.n_messages,
            "containers_ok": self.n_containers_ok,
            "containers_bad": self.n_containers_bad,
            "records_ok": self.n_records_ok,
            "records_bad": self.n_records_bad,
            "record_parse_success_ratio": (
                self.n_records_ok / total_rec if total_rec else 0.0),
            "container_parse_success_ratio": (
                self.n_containers_ok / total_cont if total_cont else 0.0),
            "acknowledgement_mode": "automatic" if self.auto_ack else "manual",
            "runtime_host_map_loaded": self.runtime_images_path is not None,
            "attribution_configuration": self.attribution_configuration,
            "attribution_configuration_sha256": self.attribution_configuration_sha256,
            "correlation": self.correlator.finalize_report(),
        }
        if self.spool_path is not None or self._spool_report is not None:
            result["spool"] = self._spool_report
        return result


def replay_spooled_events(
    path: Path,
    svc_re: re.Pattern,
    svc_map: dict,
    host_service_map: dict[str, str],
    progress: object | None = None,
) -> tuple[list[dict], dict, dict]:
    """Rebuild the final correlated event set only from retained spool bytes.

    ``progress`` is called periodically while replaying so a supervising
    watchdog can distinguish data-proportional work from a hang (F-ADH-061).
    """

    bodies, report = replay_kieker_spool(path)
    correlator = NativeTraceCorrelator(svc_re, svc_map, host_service_map)
    counts = {
        "messages": 0,
        "containers_ok": 0,
        "containers_bad": 0,
        "records_ok": 0,
        "records_bad": 0,
    }
    for body in bodies:
        if progress is not None and counts["messages"] % 200 == 0:
            progress()
        counts["messages"] += 1
        try:
            records = parse_container(body)
        except ContainerParseError:
            counts["containers_bad"] += 1
            continue
        counts["containers_ok"] += 1
        counts["records_ok"] += sum(1 for record in records if record.get("_ok"))
        counts["records_bad"] += sum(1 for record in records if not record.get("_ok"))
        correlator.add_records(records, hashlib.sha1(body).hexdigest())
    if progress is not None:
        progress()
    correlator.flush()
    report = dict(report)
    report["replayedEventCount"] = len(correlator.events)
    report["replayedRecordFailures"] = counts["records_bad"]
    return list(correlator.events), report, counts


# ── Synthetic fixture + self-check ──────────────────────────────────────────
def _encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def build_fixture(records: list[dict]) -> bytes:
    """Serialize records into a Kieker binary container (mirrors the writer).

    Each record dict: class_name, operationSignature, sessionId, traceId, tin,
    tout, hostname, eoi, ess, and (for WithParameters) parameterTypes,
    parameterValues, returnType, returnValue. Used only by the self-check.
    """
    registry: list[str] = []
    index: dict[str, int] = {}

    def sid(s: str) -> int:
        if s not in index:
            index[s] = len(registry)
            registry.append(s)
        return index[s]

    rec_buf = bytearray()

    def put_string(s: str) -> None:
        rec_buf.extend(struct.pack(">i", sid(s)))

    for r in records:
        rec_buf.extend(struct.pack(">i", sid(r["class_name"])))   # classId
        rec_buf.extend(struct.pack(">q", r.get("loggingTimestamp", 0)))
        put_string(r["operationSignature"])
        put_string(r["sessionId"])
        rec_buf.extend(struct.pack(">q", r["traceId"]))
        rec_buf.extend(struct.pack(">q", r["tin"]))
        rec_buf.extend(struct.pack(">q", r["tout"]))
        put_string(r["hostname"])
        rec_buf.extend(struct.pack(">i", r["eoi"]))
        rec_buf.extend(struct.pack(">i", r["ess"]))
        if r["class_name"].endswith("WithParametersRecord"):
            pt = r.get("parameterTypes", [])
            rec_buf.extend(struct.pack(">i", len(pt)))
            for x in pt:
                put_string(x)
            pv = r.get("parameterValues", [])
            rec_buf.extend(struct.pack(">i", len(pv)))
            for x in pv:
                put_string(x)
            put_string(r.get("returnType", "void"))
            put_string(r.get("returnValue", ""))

    reg_buf = bytearray()
    reg_buf.extend(_encode_varint(len(registry)))
    for s in registry:
        sb = s.encode("utf-8")
        reg_buf.extend(_encode_varint(len(sb)))
        reg_buf.extend(sb)

    container = bytearray()
    container.extend(struct.pack(">i", CONTAINER_IDENTIFIER))
    container.extend(struct.pack(">i", FORMAT_IDENTIFIER))
    container.extend(rec_buf)
    container.extend(reg_buf)
    container.extend(struct.pack(">i", len(rec_buf)))     # trailing recordsLength
    return bytes(container)


def self_check() -> int:
    """Round-trip a synthetic fixture through the parser. Returns exit code."""
    # A 3-span trace: webui root (ess0) -> auth (ess1) -> persistence (ess2),
    # plus a second single-span trace, across two record classes.
    src = [
        {"class_name": OER_CLASS,
         "operationSignature": "public void tools.descartes.teastore.webui.servlet.IndexServlet.handleGET()",
         "sessionId": "sess-A", "traceId": 1001, "tin": 1_000_000_000,
         "tout": 1_050_000_000, "hostname": "webui", "eoi": 0, "ess": 0},
        {"class_name": OEWPR_CLASS,
         "operationSignature": "public boolean tools.descartes.teastore.store.rest.AuthResource.login(String)",
         "sessionId": "sess-A", "traceId": 1001, "tin": 1_005_000_000,
         "tout": 1_030_000_000, "hostname": "auth", "eoi": 1, "ess": 1,
         "parameterTypes": ["java.lang.String"], "parameterValues": ["user1"],
         "returnType": "boolean", "returnValue": "true"},
        {"class_name": OER_CLASS,
         "operationSignature": "public Product tools.descartes.teastore.entities.ProductRepository.getEntity(long)",
         "sessionId": "sess-A", "traceId": 1001, "tin": 1_010_000_000,
         "tout": 1_020_000_000, "hostname": "persistence", "eoi": 2, "ess": 2},
        {"class_name": OER_CLASS,
         "operationSignature": "public void tools.descartes.teastore.recommender.rest.RecommendResource.recommend()",
         "sessionId": "sess-B", "traceId": 2002, "tin": 2_000_000_000,
         "tout": 2_040_000_000, "hostname": "recommender", "eoi": 0, "ess": 0},
    ]
    body = build_fixture(src)
    records = parse_container(body)

    assert all(r.get("_ok") for r in records), \
        f"not all records parsed: {[r for r in records if not r.get('_ok')]}"
    assert len(records) == 4, f"expected 4 records, got {len(records)}"

    # field-level checks on the WithParameters record
    login = next(r for r in records if r["hostname"] == "auth")
    assert login["traceId"] == 1001, login["traceId"]
    assert login["eoi"] == 1 and login["ess"] == 1
    assert login["tin"] == 1_005_000_000 and login["tout"] == 1_030_000_000
    assert login["sessionId"] == "sess-A", login["sessionId"]
    assert login["parameterTypes"] == ["java.lang.String"], login["parameterTypes"]
    assert login["returnType"] == "boolean" and login["returnValue"] == "true"

    svc_re = re.compile(DEFAULT_SERVICE_REGEX)
    events = records_to_events(records, svc_re, DEFAULT_SERVICE_MAP,
                               hashlib.sha1(body).hexdigest())
    assert len(events) == 4, len(events)

    ev_by_span = {e["span_id"]: e for e in events}
    root = ev_by_span["1001:0"]
    child = ev_by_span["1001:1"]
    grand = ev_by_span["1001:2"]
    assert root["parent_span_id"] == "", root["parent_span_id"]
    assert child["parent_span_id"] == "1001:0", child["parent_span_id"]
    assert grand["parent_span_id"] == "1001:1", grand["parent_span_id"]
    assert root["service"] == "webui", root["service"]
    assert child["service"] == "auth", child["service"]   # store -> auth map
    assert grand["service"] == "persistence", grand["service"]  # entities -> persistence
    assert abs(child["duration_s"] - 0.025) < 1e-9, child["duration_s"]
    assert child["operation"] == "AuthResource.login", child["operation"]

    # multi-service check: trace 1001 spans 3 services
    svcs_1001 = {e["service"] for e in events if e["trace_id"] == "1001"}
    assert svcs_1001 == {"webui", "auth", "persistence"}, svcs_1001

    # unified-schema check: events must pass the shared validator and carry the
    # REAL Kieker traceId (not a scraper-generated id) + native-only optionals.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from collectors import validate_events, REQUIRED_FIELDS, OPTIONAL_FIELDS
    validate_events(events, "kieker_native")
    for e in events:
        for k in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            assert k in e, f"schema field {k!r} missing after validate_events"
        assert not e["trace_id"].startswith("scraped_"), e["trace_id"]
        assert e["trace_id"] == str(e["kieker_trace_id"]), \
            (e["trace_id"], e["kieker_trace_id"])
        assert e["source"] == "kieker_native", e["source"]
    assert root["kieker_trace_id"] == 1001 and root["trace_id"] == "1001"
    assert child["tin"] == 1_005_000_000 and child["tout"] == 1_030_000_000
    assert child["session_id"] == "sess-A", child["session_id"]

    # malformed container is handled, not crashed
    try:
        parse_container(b"\x00\x00\x00\x01" + b"\x00" * 20)
        raise AssertionError("bad container should have raised")
    except ContainerParseError:
        pass

    # a frame whose recordsLength points past the body is caught, not crashed
    try:
        bad_len = bytearray(body)
        struct.pack_into(">i", bad_len, len(bad_len) - 4, len(bad_len) * 2)
        parse_container(bytes(bad_len))
        raise AssertionError("oversized recordsLength should have raised")
    except ContainerParseError:
        pass

    # a truncated record inside a valid frame -> flagged _ok=False, never crashes.
    # Hand-build a container whose records region holds one full 12-byte header
    # (classId + loggingTs) but then EOFs mid-field (no string/long bytes).
    reg = ["some.Record"]
    reg_bytes = _encode_varint(len(reg))
    for s in reg:
        sb = s.encode("utf-8")
        reg_bytes += _encode_varint(len(sb)) + sb
    rec_region = struct.pack(">i", 0) + struct.pack(">q", 0)  # header only, 12B
    trunc = (struct.pack(">i", CONTAINER_IDENTIFIER)
             + struct.pack(">i", FORMAT_IDENTIFIER)
             + rec_region + reg_bytes
             + struct.pack(">i", len(rec_region)))
    recs2 = parse_container(trunc)
    assert any(not r.get("_ok") for r in recs2), \
        "truncated trailing record should be flagged _ok=False, not crash"

    print("SELF-CHECK PASSED: 4/4 records, eoi/ess parent tree correct, "
          "field round-trip exact, unified schema valid (real trace ids), "
          "malformed frames handled.")
    return 0


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-check", action="store_true",
                    help="round-trip a synthetic fixture and exit (no server)")
    ap.add_argument("--output", type=Path,
                    default=Path("data/experiments/teastore_native_traces.json"))
    ap.add_argument(
        "--spool", type=Path,
        help=("exclusive per-cell raw AMQP spool; required for live collection "
              "and never overwritten"),
    )
    ap.add_argument(
        "--runtime-images", type=Path,
        help=("runtime-images.json used to bind Docker container hostnames to "
              "Compose services; defaults to the file beside --output"),
    )
    ap.add_argument("--duration", type=float, default=150.0,
                    help="seconds to consume the queue")
    ap.add_argument("--max-messages", type=int, default=10_000_000)
    ap.add_argument("--inactivity-timeout", type=float, default=5.0)
    args = ap.parse_args()

    if args.self_check:
        return self_check()

    if args.spool is None:
        print("durable --spool is required for live collection", file=sys.stderr)
        return 2
    if args.output.exists() or args.output.is_symlink():
        print(f"refusing to overwrite trace output: {args.output}", file=sys.stderr)
        return 2

    runtime_images = args.runtime_images
    inferred_runtime_images = args.output.parent / "runtime-images.json"
    if runtime_images is None and inferred_runtime_images.is_file():
        runtime_images = inferred_runtime_images
    try:
        collector = KiekerNativeCollector(
            runtime_images_path=runtime_images, spool_path=args.spool,
        )
        events = collector.consume(duration=args.duration,
                                   max_messages=args.max_messages,
                                   inactivity_timeout=args.inactivity_timeout)
    except Exception as exc:  # noqa: BLE001 - no traces survive an incomplete spool
        print(
            f"durable spool collection failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    stats = collector.stats()
    print(json.dumps(stats, indent=2), file=sys.stderr)

    # enforce the shared event schema (fills absent optional fields with None)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        from collectors import validate_events
        validate_events(events, "kieker_native")
    except Exception as exc:  # noqa: BLE001
        print(f"schema validation failed: {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(args.output, output_flags, 0o600)
    try:
        _write_all(descriptor, json.dumps(events, indent=1).encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    print(f"{len(events)} native events -> {args.output} "
          f"(record parse ratio {stats['record_parse_success_ratio']:.3f})",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
