import importlib.util
import hashlib
import json
import os
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).parents[1]


def _load(relative: str, name: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


kieker = _load(
    "modules/teastore/collectors/kieker_native.py", "kieker_durable_spool_tests"
)
campaign = _load(
    "modules/teastore/execution/performance_campaign.py", "spool_campaign_tests"
)
performance_receipt = _load(
    "modules/teastore/validation/performance_receipt.py", "spool_receipt_tests"
)
terminal = _load(
    "modules/teastore/validation/srv5_terminal.py", "spool_terminal_tests"
)


class Channel:
    def __init__(self, calls=None):
        self.acks = []
        self.calls = calls

    def basic_ack(self, *, delivery_tag):
        if self.calls is not None:
            self.calls.append("ack")
        self.acks.append(delivery_tag)


def method(tag: int, *, redelivered: bool = False):
    return SimpleNamespace(
        consumer_tag="consumer-1",
        delivery_tag=tag,
        redelivered=redelivered,
        exchange="",
        routing_key="kieker",
    )


def properties(message_id: str):
    return SimpleNamespace(
        content_type="application/octet-stream", content_encoding=None,
        headers={"producer": "teastore"}, delivery_mode=2, priority=0,
        correlation_id="campaign-cell", reply_to=None, expiration=None,
        message_id=message_id, timestamp=1, type="kieker", user_id=None,
        app_id="teastore", cluster_id=None,
    )


def body(*, trace_id: int = 42, eoi: int = 0, ess: int = 0,
         hostname: str = "webui") -> bytes:
    return kieker.build_fixture([{
        "class_name": kieker.OER_CLASS,
        "operationSignature": (
            "public void tools.descartes.teastore.webui.Home.render()"
        ),
        "sessionId": "fixture", "traceId": trace_id,
        "tin": 1_000 + eoi, "tout": 2_000 + eoi,
        "hostname": hostname, "eoi": eoi, "ess": ess,
    }])


def collector(tmp_path: Path):
    return kieker.KiekerNativeCollector(
        spool_path=tmp_path / kieker.SPOOL_ARTIFACT_NAME,
    )


def finish(value):
    value.correlator.flush()
    value.spool.seal()
    events, summary, counts = kieker.replay_spooled_events(
        value.spool_path, value.svc_re, value.svc_map, value.host_service_map,
    )
    value._spool_report = summary
    return events, summary, counts


def _rewrite_spool_metadata(path: Path, frame_index: int, mutate):
    raw = path.read_bytes()
    offset = len(kieker.SPOOL_MAGIC)
    frames = []
    while offset < len(raw):
        assert raw[offset:offset + 4] == kieker.SPOOL_FRAME_MAGIC
        metadata_bytes = struct.unpack_from(">I", raw, offset + 4)[0]
        body_bytes = struct.unpack_from(">Q", raw, offset + 8)[0]
        metadata_start = offset + 16
        body_start = metadata_start + metadata_bytes
        body_end = body_start + body_bytes
        metadata = json.loads(raw[metadata_start:body_start])
        frames.append([metadata, raw[body_start:body_end]])
        offset = body_end + 32
    previous = kieker.SPOOL_ZERO_DIGEST
    rewritten = bytearray(kieker.SPOOL_MAGIC)
    for index, (metadata, raw_body) in enumerate(frames):
        metadata["previousFrameSha256"] = previous
        if index == frame_index:
            mutate(metadata)
            if metadata.get("kind") == "delivery":
                metadata["identitySha256"] = hashlib.sha256(
                    kieker._canonical_json_bytes(metadata["identity"])
                ).hexdigest()
        frame, previous = kieker._spool_frame(metadata, raw_body)
        rewritten.extend(frame)
    path.write_bytes(rewritten)


def test_real_callback_fsyncs_exact_frame_before_manual_ack(tmp_path):
    value = collector(tmp_path)
    calls = []
    real_fsync = value.spool._fsync

    def ordered_fsync(descriptor):
        calls.append("fsync")
        real_fsync(descriptor)

    value.spool._fsync = ordered_fsync
    channel = Channel(calls)
    emitted = value.handle_delivery(channel, method(7), properties("message-7"), body())

    assert channel.acks == [7]
    assert calls == ["fsync", "ack"]
    replayed, summary, counts = finish(value)
    assert replayed == emitted
    assert summary["complete"] is True
    assert counts == {
        "messages": 1, "containers_ok": 1, "containers_bad": 0,
        "records_ok": 1, "records_bad": 0,
    }


@pytest.mark.parametrize("failure", ["write", "fsync"])
def test_real_callback_never_acks_when_durable_append_fails(tmp_path, failure):
    value = collector(tmp_path)
    channel = Channel()

    def planted_failure(*_args):
        raise OSError(f"planted {failure} failure")

    if failure == "write":
        value.spool._write_all = planted_failure
    else:
        value.spool._fsync = planted_failure

    with pytest.raises(kieker.KiekerSpoolError, match=f"planted {failure} failure"):
        value.handle_delivery(
            channel, method(8), properties("message-8"), body(trace_id=43)
        )
    assert channel.acks == []
    value.spool.close_unsealed()
    _, report = kieker.replay_kieker_spool(value.spool_path)
    assert report["complete"] is False


def test_crash_after_ack_but_before_terminal_seal_cannot_be_final_evidence(tmp_path):
    value = collector(tmp_path)
    channel = Channel()
    value.handle_delivery(channel, method(9), properties("message-9"), body())
    assert channel.acks == [9]
    value.spool.close_unsealed()  # planted process crash before terminal seal

    _, report = kieker.replay_kieker_spool(value.spool_path)
    assert report["sealed"] is False
    assert report["complete"] is False
    assert report["blockers"] == ["spool has no terminal seal"]


def test_ack_failure_after_fsync_leaves_replayable_but_unsealed_body(tmp_path):
    value = collector(tmp_path)

    class FailingChannel:
        def basic_ack(self, *, delivery_tag):
            raise OSError(f"planted ack failure for {delivery_tag}")

    with pytest.raises(kieker.KiekerSpoolError, match="planted ack failure"):
        value.handle_delivery(
            FailingChannel(), method(10), properties("message-10"), body()
        )

    bodies, report = kieker.replay_kieker_spool(value.spool_path)
    assert bodies == [body()]
    assert report["deliveryCount"] == 1
    assert report["sealed"] is False
    assert report["complete"] is False


def test_poll_consumer_transport_failure_propagates_and_leaves_spool_unsealed(
    tmp_path, monkeypatch,
):
    value = collector(tmp_path)

    class FailingPika:
        @staticmethod
        def PlainCredentials(_user, _password):
            return object()

        @staticmethod
        def ConnectionParameters(**_kwargs):
            return object()

        @staticmethod
        def BlockingConnection(_params):
            raise OSError("planted transport failure")

    monkeypatch.setitem(sys.modules, "pika", FailingPika)
    with pytest.raises(OSError, match="planted transport failure"):
        value.consume_traces()

    _, report = kieker.replay_kieker_spool(value.spool_path)
    assert report["sealed"] is False
    assert report["complete"] is False
    assert report["blockers"] == ["spool has no terminal seal"]


def test_deterministic_replay_repairs_cross_message_parentage(tmp_path):
    value = collector(tmp_path)
    channel = Channel()
    # Deliberately receive the child first. The global correlator repairs it
    # after the root body arrives, and spool replay must reproduce that result.
    child = body(trace_id=77, eoi=1, ess=1)
    root = body(trace_id=77, eoi=0, ess=0)
    value.handle_delivery(channel, method(1), properties("child"), child)
    value.handle_delivery(channel, method(2), properties("root"), root)
    live = value.correlated_events()
    replayed, summary, _ = finish(value)

    assert replayed == live
    assert replayed[0]["parent_span_id"] == "77:0"
    assert replayed[0]["parent_resolution"] == "resolved"
    assert summary["deliveryCount"] == summary["uniqueBodyCount"] == 2
    assert summary["duplicateBodyCount"] == 0


def test_duplicate_delivery_is_retained_but_terminally_rejected(tmp_path):
    value = collector(tmp_path)
    channel = Channel()
    raw = body()
    value.handle_delivery(channel, method(1), properties("same"), raw)
    value.handle_delivery(
        channel, method(2, redelivered=True), properties("same"), raw
    )
    value.spool.seal()

    _, report = kieker.replay_kieker_spool(value.spool_path)
    assert channel.acks == [1, 2]
    assert report["sealed"] is True
    assert report["complete"] is False
    assert report["duplicateBodyCount"] == 1
    assert any("duplicate raw body" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize("defect", ["truncate", "frame-hash", "trailing-bytes"])
def test_spool_replay_rejects_truncation_hash_drift_and_post_terminal_bytes(
    tmp_path, defect,
):
    value = collector(tmp_path)
    value.handle_delivery(Channel(), method(1), properties("message"), body())
    finish(value)
    payload = bytearray(value.spool_path.read_bytes())
    if defect == "truncate":
        payload = payload[:-1]
    elif defect == "frame-hash":
        payload[len(kieker.SPOOL_MAGIC) + 20] ^= 1
    else:
        payload.extend(b"planted")
    value.spool_path.write_bytes(payload)

    _, report = kieker.replay_kieker_spool(value.spool_path)
    assert report["complete"] is False
    assert any(
        marker in " ".join(report["blockers"])
        for marker in ("truncated", "hash differs", "after its terminal")
    )


@pytest.mark.parametrize(
    ("frame_index", "mutation"),
    [
        (0, lambda row: row.update(schemaVersion=True)),
        (0, lambda row: row.update(sequence=True)),
        (0, lambda row: row.update(bodyBytes=True)),
        (1, lambda row: row.update(deliveryCount=True)),
        (1, lambda row: row.update(rawBodyBytes=True)),
        (1, lambda row: row.update(uniqueBodyCount=True)),
        (1, lambda row: row.update(duplicateBodyCount=False)),
    ],
)
def test_spool_replay_rejects_boolean_integer_substitution(
    tmp_path, frame_index, mutation,
):
    value = collector(tmp_path)
    value.handle_delivery(Channel(), method(1), properties("typed"), body())
    finish(value)
    _rewrite_spool_metadata(value.spool_path, frame_index, mutation)

    _, report = kieker.replay_kieker_spool(value.spool_path)
    assert report["complete"] is False
    assert report["blockers"]


@pytest.mark.parametrize(
    "header_value",
    [
        1.5,
        {"type": "float-hex", "value": "not-a-float"},
        {"nested": [{"type": "bytes-hex", "value": "GG"}]},
    ],
)
def test_spool_replay_rejects_non_writer_normalized_nested_identity(
    tmp_path, header_value,
):
    value = collector(tmp_path)
    value.handle_delivery(Channel(), method(1), properties("identity"), body())
    finish(value)

    def plant(metadata):
        metadata["identity"]["properties"]["headers"]["planted"] = header_value

    _rewrite_spool_metadata(value.spool_path, 0, plant)
    _, report = kieker.replay_kieker_spool(value.spool_path)
    assert report["complete"] is False
    assert "identity type or hash" in " ".join(report["blockers"])


def test_spool_creation_rejects_overwrite_and_symlink(tmp_path):
    target = tmp_path / "existing.spool"
    target.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        kieker.KiekerBodySpool(target)

    real = tmp_path / "real.spool"
    real.write_bytes(b"not-a-spool")
    link = tmp_path / "link.spool"
    link.symlink_to(real)
    with pytest.raises(kieker.KiekerSpoolError, match="symbolic link"):
        kieker.KiekerBodySpool(link)
    _, report = kieker.replay_kieker_spool(link)
    assert report["complete"] is False
    assert "symbolic link" in " ".join(report["blockers"])


def test_callback_to_runner_receipt_and_terminal_spool_boundary(tmp_path):
    value = collector(tmp_path)
    emitted = value.handle_delivery(
        Channel(), method(1), properties("boundary"), body()
    )
    replayed, summary, counts = finish(value)
    assert emitted == replayed
    stats = value.stats()
    stats["runtime_host_map_loaded"] = True
    assert counts["records_ok"] == 1

    assert campaign.validate_spool_summary(
        summary, expected_messages=1, expected_events=1,
        expected_bad_records=0,
    ) == summary
    telemetry = {
        "records": 1, "bytes": 1, "uniqueSignatures": 1,
        "parseFailures": 0, "collectorStats": stats, "spool": summary,
    }
    receipt = {
        "schemaVersion": 2, "posture": "full",
        "analysisKind": "cost", "resourceUse": "cost-proxy",
        "source": {
            "dirty": False, "spoolSha256": summary["artifactSha256"],
            "collectorAttributionConfigurationSha256":
                stats["attribution_configuration_sha256"],
        },
        "workload": {
            "offered": 1, "completed": 1, "successful": 1, "failed": 0,
            "timedOut": 0, "settled": 1, "concurrency": 1,
        },
        "latencyMs": {
            "denominator": "successful-journeys", "count": 1,
            "p50": 1, "p95": 1, "p99": 1, "mean": 1,
        },
        "resources": {
            "applicationCpuSeconds": 1, "applicationMemoryPeakBytes": 1,
            "hostCpuSeconds": 1,
        },
        "telemetry": telemetry,
        "queue": {
            "purgedBefore": True, "messagesBefore": 0, "messagesAfter": 0,
            "exclusiveConsumer": True,
        },
    }
    assert performance_receipt.validate(receipt)["verdict"] == "pass"

    runtime_images = tmp_path / "runtime-images.json"
    runtime_images.write_text(json.dumps({"schemaVersion": 1}))
    fake_campaign = SimpleNamespace(
        replay_spool_evidence=lambda spool, runtime: {
            "events": replayed, "summary": summary, "counts": counts,
            "attributionConfiguration": stats["attribution_configuration"],
            "attributionConfigurationSha256":
                stats["attribution_configuration_sha256"],
        }
    )
    assert terminal._durable_spool_blockers(
        value.spool_path, runtime_images, replayed, telemetry, stats,
        fake_campaign, where="boundary",
    ) == []

    planted = dict(summary, complete=False, blockers=["planted truncation"])
    fake_campaign.replay_spool_evidence = lambda spool, runtime: {
        "events": replayed, "summary": planted, "counts": counts,
        "attributionConfiguration": stats["attribution_configuration"],
        "attributionConfigurationSha256":
            stats["attribution_configuration_sha256"],
    }
    blockers = terminal._durable_spool_blockers(
        value.spool_path, runtime_images, replayed, telemetry, stats,
        fake_campaign, where="boundary",
    )
    assert any("incomplete" in blocker for blocker in blockers)
    assert any("summary differs" in blocker for blocker in blockers)


def test_performance_receipt_v2_cannot_downgrade_or_forge_spool_reconciliation(tmp_path):
    value = collector(tmp_path)
    value.handle_delivery(Channel(), method(1), properties("receipt"), body())
    _, summary, _ = finish(value)
    stats = value.stats()
    stats["runtime_host_map_loaded"] = True
    telemetry = {
        "records": 1, "bytes": 1, "uniqueSignatures": 1,
        "parseFailures": 0, "collectorStats": stats, "spool": summary,
    }
    base = {
        "schemaVersion": 2, "posture": "full",
        "analysisKind": "effect", "resourceUse": "diagnostic-only",
        "source": {
            "dirty": False,
            "spoolSha256": summary["artifactSha256"],
            "collectorAttributionConfigurationSha256":
                stats["attribution_configuration_sha256"],
        },
        "workload": {
            "offered": 1, "completed": 1, "successful": 1, "failed": 0,
            "timedOut": 0, "settled": 1, "concurrency": 1,
        },
        "latencyMs": {
            "denominator": "successful-journeys", "count": 1,
            "p50": 1, "p95": 1, "p99": 1, "mean": 1,
        },
        "resources": None,
        "telemetry": telemetry,
        "queue": {
            "purgedBefore": True, "messagesBefore": 0, "messagesAfter": 0,
            "exclusiveConsumer": True,
        },
    }
    assert performance_receipt.validate(base)["verdict"] == "pass"

    forged = json.loads(json.dumps(base))
    forged["telemetry"]["spool"]["deliveryCount"] = 0
    report = performance_receipt.validate(forged)
    assert report["verdict"] == "blocked"
    assert any("do not reconcile" in blocker or "differs" in blocker
               for blocker in report["blockers"])
