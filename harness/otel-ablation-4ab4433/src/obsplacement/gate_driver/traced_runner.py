"""Wrap a SUT transport's subprocess runner so every remote command is traced.

The same ~12-line closure appears four times across the canonical drivers
(gate_setup.py cmd_install:180-191, cmd_readiness:242-253; gate_run.py
cmd_execute's `tracing_runner`:198-215; campaign_setup.py's module-level
`tracing_runner`:237-253). Preserving every argv, return code, and stream to
a trace file exists for one reason stated directly in gate_setup.py's
cmd_install comment: "a full trace makes a third failure diagnosable without
spending another typed approval on instrumentation." A campaign is one-shot;
its trace file may be the only diagnostic evidence after it exits.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

__all__ = ["traced_runner"]


def traced_runner(subprocess_runner: Callable, trace_path: Path, *,
                   stream_limit: int | None = None) -> Callable:
    """Return a runner with `subprocess_runner`'s exact signature that also
    appends a human-readable trace of every call to `trace_path`.

    `subprocess_runner(argv, data=None) -> CommandResult` is the SUT
    transport's own runner (per `contract.TransportProtocol`); this function
    does not know or care what it does, only that it returns something with
    `.returncode`, `.stdout`, and `.stderr`. `stream_limit` mirrors
    gate_run.py's `tracing_runner`, which truncates each stream to 20000
    characters in the trace (campaign trace files can otherwise be huge);
    leave it `None` (no truncation) to match gate_setup.py's and
    campaign_setup.py's untruncated variants.
    """
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace = trace_path.open("w")

    def run(argv, data=None):
        result = subprocess_runner(argv, data)
        trace.write(f"\n=== argv: {[str(a)[:160] for a in argv]}\n")
        trace.write(f"    rc={result.returncode}\n")
        for stream_name in ("stdout", "stderr"):
            value = getattr(result, stream_name, None)
            if isinstance(value, bytes):
                value = value.decode("utf-8", "replace")
            if value:
                if stream_limit is not None:
                    value = value[:stream_limit]
                trace.write(f"--- {stream_name} ---\n{value}\n")
        trace.flush()
        return result

    return run
