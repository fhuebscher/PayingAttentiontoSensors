"""Exception hierarchy for the shared gate-driver library.

Every failure mode here is a *fail-closed* signal: something the operator or a
SUT integrator must look at, never something a caller should catch and paper
over. None of these exceptions carry a "repaired" or "guessed" value -- the
whole point of this module is that the library refuses rather than improvises
(see `sentence.py` for the sharpest example: a mismatch raises, it never
attempts to coerce the typed text into something that matches).
"""
from __future__ import annotations


class GateDriverError(Exception):
    """Base class for every fail-closed condition in this library."""


class SentenceMismatch(GateDriverError):
    """A typed authorization sentence did not match the harness derivation.

    Generalizes the byte-exact check duplicated across gate_setup.py
    (cmd_record_plan, cmd_install), gate_run.py (cmd_execute), and
    campaign_setup.py (cmd_authorize) in scratchpad/gate-drivers/. The
    library never constructs a "corrected" sentence and never falls back to
    a fuzzy match -- `expected` and `typed` are preserved verbatim so the
    caller can show the operator exactly what diverged.
    """

    def __init__(self, expected: str, typed: str):
        self.expected = expected
        self.typed = typed
        super().__init__(
            "typed sentence does not match the harness derivation byte-for-byte"
        )


class PathAlreadyExists(GateDriverError):
    """A fail-closed write or capture refused to overwrite an existing path.

    Generalizes gate_setup.py's cmd_readiness guard ("FATAL: {local_output}
    already exists; move it aside") into a single reusable primitive so every
    gate document and every fetched-artifact directory gets the same
    protection, not just the one path that happened to get it by hand.
    """

    def __init__(self, path):
        self.path = path
        super().__init__(f"refusing to overwrite existing path: {path}")


class ConcurrentRunError(GateDriverError):
    """Another setup/run attempt already holds the single-flight lock.

    Generalizes campaign_setup.py's `.auto.lock` (O_CREAT|O_EXCL) guard,
    added after two overlapping `auto` runs corrupted each other's gate
    documents on 2026-09-01 (one run's gate-plan.json was stolen mid-flight
    by the other). See fs_guards.SingleFlightLock.
    """

    def __init__(self, lock_path):
        self.lock_path = lock_path
        super().__init__(
            f"another run holds the lock at {lock_path}; overlapping runs "
            "corrupt each other's gate documents"
        )


class PreflightExpired(GateDriverError):
    """A preflight/authorization is older than its freshness window allows.

    The runtime preflight is content-addressed and cannot be recaptured
    under an existing setup-id -- a fresh one needs a new setup-id -- so this
    is deliberately a hard stop, not a "recapture and continue."
    """

    def __init__(self, captured_at, max_age_seconds, age_seconds):
        self.captured_at = captured_at
        self.max_age_seconds = max_age_seconds
        self.age_seconds = age_seconds
        super().__init__(
            f"preflight captured at {captured_at} is {age_seconds:.0f}s old, "
            f"exceeding the {max_age_seconds}s freshness window"
        )


class CampaignDrift(GateDriverError):
    """The live SETUP-CAMPAIGN authorization no longer matches campaign identity."""

    def __init__(self, drift: dict):
        self.drift = drift
        super().__init__(f"campaign identity drifted from authorized invariants: {drift}")


class CampaignExpired(GateDriverError):
    """The live SETUP-CAMPAIGN authorization's deadline has passed."""

    def __init__(self, deadline):
        self.deadline = deadline
        super().__init__(f"SETUP-CAMPAIGN authorization expired at {deadline}")


class NoLiveCampaign(GateDriverError):
    """No SETUP-CAMPAIGN authorization has been recorded yet."""


class ContractViolation(GateDriverError):
    """A loaded SUT module does not satisfy the adapter/transport/installer contract."""

    def __init__(self, module_label: str, missing: tuple):
        self.module_label = module_label
        self.missing = missing
        super().__init__(f"{module_label} is missing required contract members: {missing}")


class ModuleLoadError(GateDriverError):
    """A SUT module could not be loaded from its declared path."""


class RunAuthorizationDrift(GateDriverError):
    """What GATE-RUN is about to launch is not what the sentence was derived from.

    A typed GATE-RUN sentence authorizes one exact package: the framework
    commit, the compiled plan, and the run authorization that existed at the
    moment the sentence was derived. Between derivation and execution a
    plan file can be replaced, the framework can move, or a second
    derivation can overwrite the authorization -- and `verify_typed_sentence`
    alone would not notice, because it re-derives the expected text from
    whatever is on disk *now*. This is raised when the derivation receipt and
    the current state disagree; the correct response is always a fresh
    derivation and a fresh sentence, never a retry.
    """

    def __init__(self, field: str, derived, observed):
        self.field = field
        self.derived = derived
        self.observed = observed
        super().__init__(
            f"{field} changed since the run authorization was derived: "
            f"derived={derived!r} observed={observed!r}"
        )


class MissingDerivationReceipt(GateDriverError):
    """No record of when (or against what) the run authorization was derived.

    Fail closed rather than assume freshness: an authorization with no
    derivation receipt beside it is one this library did not write, or one
    whose receipt was removed.
    """

    def __init__(self, path):
        self.path = path
        super().__init__(
            f"no run-authorization derivation receipt at {path}; derive the "
            "run authorization again rather than executing an unrecorded one"
        )

