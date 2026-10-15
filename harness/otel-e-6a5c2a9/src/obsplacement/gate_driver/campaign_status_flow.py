"""One read-only status poll of a running campaign, factored out of campaign_status.py.

campaign_status.py itself is a tiny standalone script (51 lines) that: loads
`runtime-package.json`, ssh's the target's installed `campaign-status` CLI,
prints one summary line, and exits 3 on a terminal state so
`campaign_watch.sh` stops polling. The only two things worth generalizing are
the terminal-state boolean (`terminal_status.is_terminal`, already extracted)
and the shape of "ask the transport for status, given the runtime package and
its own sha256" -- `poll_once` below. Everything else (the exact ssh
invocation) is the transport's `remote_status`, per contract.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .contract import SutConfig
from .gate_paths import GatePaths
from .json_io import read_json
from .terminal_status import is_terminal

__all__ = ["PollResult", "poll_once"]


@dataclass(frozen=True)
class PollResult:
    status: dict
    terminal: bool


def poll_once(config: SutConfig, transport, paths: GatePaths) -> PollResult:
    """Read `runtime-package.json`, ask the transport for status, classify terminality.

    Reproduces campaign_status.py:14-24,33-50. The package sha is computed
    over the exact bytes on disk (matching `hashlib.sha256((GATES /
    "runtime-package.json").read_bytes())`, campaign_status.py:17), not a
    re-serialization -- a byte-for-byte identical round trip is the point,
    since the remote status endpoint is keyed on that hash to make sure the
    watcher is asking about the package that was actually launched.
    """
    package_path = paths.runtime_package
    remote_input = read_json(package_path)
    package_sha256 = hashlib.sha256(package_path.read_bytes()).hexdigest()
    status = transport.remote_status(remote_input, package_sha256)
    return PollResult(status=status, terminal=is_terminal(status))
