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
    result = report["comparisons"]["selected_minus_none"]["latency_mean_ms"]
    assert result["n"] == 5
    assert result["bootstrapPercentileInterval95"] is not None
    assert "bootstrap95Ci" not in result
    assert report["telemetryBytesSource"]["source"] == "telemetry.bytes(traces.json size)"


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


def test_three_blocks_report_t_interval_and_refuse_bootstrap():
    """n=3 percentile bootstrap collapses to the sample range, so it is refused.

    Values are campaign #6's real applicationCpuSeconds, whose full-minus-none
    differences are [-6.2645, -30.8975, -77.6405]: all negative, so the n=3
    bootstrap interval can never contain zero while the t-interval plainly does.
    """
    none = [318.9037, 334.4358, 336.4995]
    full = [312.6392, 303.5383, 258.8590]
    receipts = []
    for index, block in enumerate(range(1, 4)):
        receipts.append(receipt(block, "none", none[index]))
        receipts.append(receipt(block, "selected", none[index]))
        receipts.append(receipt(block, "full", full[index]))
    report = analyze(receipts, seed=1)
    result = report["comparisons"]["full_minus_none"]["application_cpu_seconds"]
    assert result["n"] == 3
    assert result["bootstrapPercentileInterval95"] is None
    low_range, high_range = result["pairedDifferenceRange"]
    assert abs(low_range - -77.6405) < 1e-6 and abs(high_range - -6.2645) < 1e-6
    low, high = result["tInterval95"]
    assert abs(low - -128.3) < 0.2 and abs(high - 51.8) < 0.2
    assert low < 0 < high, "the honest interval includes zero"
    assert report["cautions"][0].startswith("Intervals describe 3 run-level blocks")


def test_mixed_telemetry_byte_sources_block():
    """Legacy telemetry.bytes and nested telemetry.spool must not be pooled."""
    receipts = []
    for block in range(1, 4):
        for posture in ("none", "selected", "full"):
            receipts.append(receipt(block, posture, block))
    nested = receipts[0]
    nested["telemetry"] = {"spool": {"replayedEventCount": 1, "rawBodyBytes": 1}}
    report = analyze(receipts)
    assert report["verdict"] == "blocked"
    assert any("mixed telemetry byte sources" in failure for failure in report["failures"])
