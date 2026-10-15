from obsplacement.paired_analysis import analyze


def receipt(block: int, posture: str, value: float) -> dict:
    return {
        "runId": f"b{block:02d}-{posture}", "posture": posture,
        "canonicality": {"blockers": []},
        "latencyMs": {"mean": value, "p95": value},
        "resources": {"applicationCpuSeconds": value, "hostCpuSeconds": value},
        "telemetry": {"records": value, "bytes": value},
        "window": {"startedAt": f"2026-08-{block:02d}T00:00:00+00:00"},
    }


def test_uses_block_paired_differences():
    receipts = []
    for block in range(1, 6):
        receipts.extend((receipt(block, "none", block), receipt(block, "selected", block + 2),
                         receipt(block, "full", block + 5)))
    report = analyze(receipts, seed=1)
    assert report["verdict"] == "pass"
    assert report["comparisons"]["selected_minus_none"]["latency_mean_ms"]["meanDifference"] == 2
    assert report["comparisons"]["selected_minus_full"]["telemetry_bytes"]["meanDifference"] == -3
    assert len(report["diagnostics"]["executionOrder"]) == 15
    assert report["diagnostics"]["postureDrift"]["latency_mean_ms"]["none"]["slopePerRun"] == 1


def test_flags_paired_mad_outlier():
    receipts = []
    for block in range(1, 6):
        full = block + (100 if block == 4 else 5)
        receipts.extend((receipt(block, "none", block), receipt(block, "selected", block + 2),
                         receipt(block, "full", full)))
    influence = analyze(receipts)["comparisons"]["full_minus_none"]["host_cpu_seconds"]["influence"]
    assert influence["madOutlierBlocks"] == ["b04"]


def test_rejects_incomplete_blocks():
    assert analyze([receipt(1, "none", 1), receipt(1, "full", 2)])["verdict"] == "blocked"
