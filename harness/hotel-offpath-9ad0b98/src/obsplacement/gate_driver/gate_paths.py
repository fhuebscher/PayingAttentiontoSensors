"""Conventional gate-document filenames, factored out of repeated `GATES / "..."` literals.

Every canonical driver builds these paths by string-joining a module-level
`GATES` constant (e.g. `GATES / "gate-plan.json"`) at each call site. Naming
them once means a SUT's `gates_dir` is the only per-SUT knob, and
`archive_live_documents` (fs_guards.py) can be handed the same name list a
new SUT would otherwise have to retype from campaign_setup.py:222-223 by eye.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .fs_guards import archive_live_documents

__all__ = ["GatePaths"]

# campaign_setup.py:222-223's `live` list, generalized.
#
# `run-authorization.json`, its derivation receipt, and `runtime-package.json`
# are archived too: all three are regenerated on every derivation, and leaving
# a previous attempt's copy in place across a re-run of `cmd_auto` means the
# next `cmd_execute` can find a stale authorization beside a freshly installed
# release.
#
# `gate-run.json` is deliberately NOT in this list. It is the one-shot guard:
# `cmd_execute` writes it with `write_new_json` and a second execute against
# an unmoved gate-run.json fails closed. Archiving it here would let a
# `cmd_auto` re-run quietly clear that guard, which is the opposite of what
# this list is for.
LIVE_SETUP_DOCUMENT_NAMES = (
    "gate-plan.json", "gate-setup.json", "setup-authorization.json",
    "install-receipt.json", "capture-spec.tar", "readiness-admission.json",
    "run-authorization.json", "run-authorization-receipt.json",
    "runtime-package.json",
)
LIVE_SETUP_DIRECTORY_NAMES = ("fetched-readiness",)


@dataclass(frozen=True)
class GatePaths:
    gates_dir: Path

    @property
    def target_proof(self) -> Path:
        return self.gates_dir / "target-proof.json"

    @property
    def release_bundle(self) -> Path:
        return self.gates_dir / "release-bundle.tar"

    @property
    def release_manifest(self) -> Path:
        return self.gates_dir / "release-manifest.json"

    @property
    def gate_plan(self) -> Path:
        return self.gates_dir / "gate-plan.json"

    @property
    def setup_authorization(self) -> Path:
        return self.gates_dir / "setup-authorization.json"

    @property
    def gate_setup(self) -> Path:
        return self.gates_dir / "gate-setup.json"

    @property
    def install_receipt(self) -> Path:
        return self.gates_dir / "install-receipt.json"

    @property
    def capture_spec(self) -> Path:
        return self.gates_dir / "capture-spec.tar"

    @property
    def readiness_admission(self) -> Path:
        return self.gates_dir / "readiness-admission.json"

    @property
    def fetched_readiness(self) -> Path:
        return self.gates_dir / "fetched-readiness"

    @property
    def fetched_readiness_document(self) -> Path:
        return self.fetched_readiness / "readiness.json"

    @property
    def run_authorization(self) -> Path:
        return self.gates_dir / "run-authorization.json"

    @property
    def run_authorization_receipt(self) -> Path:
        """What the run authorization was derived from, and when.

        Written by `gate_run_flow.derive_run_authorization` beside the
        authorization itself and re-checked by `cmd_execute`. It is a separate
        file rather than extra keys inside `run-authorization.json` because
        that document is the SUT adapter's, byte-for-byte: a SUT whose
        validator recomputes the authorization and compares it (Hotel's
        `validate_gate_run` does) refuses any document carrying a key the
        adapter did not put there.
        """
        return self.gates_dir / "run-authorization-receipt.json"

    @property
    def gate_run(self) -> Path:
        return self.gates_dir / "gate-run.json"

    @property
    def runtime_package(self) -> Path:
        return self.gates_dir / "runtime-package.json"

    @property
    def campaign_result(self) -> Path:
        return self.gates_dir / "campaign-result"

    @property
    def campaign_terminal(self) -> Path:
        return self.gates_dir / "campaign-terminal.json"

    @property
    def setup_campaign_authorization(self) -> Path:
        return self.gates_dir / "setup-campaign-authorization.json"

    @property
    def setup_campaign_pending(self) -> Path:
        return self.gates_dir / "setup-campaign-pending.json"

    @property
    def setup_campaign_audit(self) -> Path:
        return self.gates_dir / "setup-campaign-audit.jsonl"

    @property
    def auto_lock(self) -> Path:
        """Guards every flow that mutates the *setup*-phase documents."""
        return self.gates_dir / ".auto.lock"

    @property
    def run_lock(self) -> Path:
        """Guards every flow that mutates the *run*-phase documents.

        Separate from `auto_lock` on purpose: `gate_run_flow.cmd_refresh`
        re-runs setup (which takes `auto_lock`, in a subprocess) and then
        derives the run authorization, so one lock for both phases would
        either deadlock or have to be re-entrant.
        """
        return self.gates_dir / ".run.lock"

    def archive_previous_setup(self, *, commit: str):
        """Move the live setup-phase documents aside; see fs_guards.archive_live_documents."""
        return archive_live_documents(
            self.gates_dir, LIVE_SETUP_DOCUMENT_NAMES, commit=commit,
            extra_dirs=LIVE_SETUP_DIRECTORY_NAMES,
        )
