import importlib.util
from pathlib import Path


MODULE = Path(__file__).parents[1] / "modules/teastore/validation/performance_receipt.py"
SPEC = importlib.util.spec_from_file_location("performance_receipt", MODULE)
performance_receipt = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(performance_receipt)


def receipt():
    return {
        "posture": "none", "source": {"dirty": False},
        "workload": {"offered": 10, "completed": 10, "failed": 0, "concurrency": 1},
        "latencyMs": {"count": 10, "p50": 1, "p95": 2, "p99": 3},
        "resources": {"applicationCpuSeconds": 1, "applicationMemoryPeakBytes": 2, "hostCpuSeconds": 3},
        "telemetry": {"records": 0, "bytes": 0, "uniqueSignatures": 0, "parseFailures": 0},
        "queue": {"purgedBefore": True, "messagesBefore": 0, "messagesAfter": 0, "exclusiveConsumer": True},
    }


def test_accepts_complete_matched_receipt():
    assert performance_receipt.validate(receipt())["verdict"] == "pass"


def test_blocks_denominator_and_none_posture_violation():
    value = receipt()
    value["latencyMs"]["count"] = 9
    value["telemetry"]["records"] = 1
    report = performance_receipt.validate(value)
    assert report["verdict"] == "blocked"
    assert len(report["blockers"]) == 2
