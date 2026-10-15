"""Every attribute the shared gate-driver library reaches for must exist here.

Three SUT-specific bridges were missing when OTel was mated to the shared
library on 2026-09-12, and each was found the hard way, one per failed run
against a real host on 2026-09-15:

  * `GATE_ENVELOPES`      -- documents were built under TeaStore's payload keys
  * `preflight_captured_at` -- the library looked for TeaStore's `capturedAt`
  * (and the same shape twice more in non-adapter code)

`check_adapter_contract` does not require the optional ones, so a SUT that
declares nothing passes it and then fails at run time. This test closes the
class: it derives the required names from the library itself rather than from
a hand-maintained list, so a new library call site fails here instead of on a
host three weeks later.
"""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "modules" / "otel-demo" / "execution" / "candidate_runtime_adapter.py"
LIB = ROOT / "src" / "obsplacement" / "gate_driver"

# `adapter.py` is an attribute access on a local variable named `adapter` that
# is not the SUT adapter; exclude it rather than inventing a fake attribute.
NOT_ADAPTER_ATTRS = {"py"}


def _library_requires():
    names = set()
    for path in sorted(LIB.glob("*.py")):
        for match in re.finditer(r"\badapter\.([A-Za-z_][A-Za-z0-9_]*)", path.read_text()):
            names.add(match.group(1))
    return names - NOT_ADAPTER_ATTRS


@pytest.fixture(scope="module")
def adapter():
    spec = importlib.util.spec_from_file_location("otel_adapter_contract", ADAPTER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_the_library_reaches_for_something(adapter):
    # Guard the guard: a regex that matched nothing would make this file vacuous.
    assert len(_library_requires()) >= 10


def test_adapter_provides_every_attribute_the_library_uses(adapter):
    missing = sorted(name for name in _library_requires() if not hasattr(adapter, name))
    assert not missing, (
        "the shared gate-driver library reaches for these on the adapter and they "
        "are not declared: %s" % missing
    )


def test_gate_envelopes_covers_all_three_gates(adapter):
    # A partial declaration raises ContractViolation at build time rather than
    # falling back, so a missing gate here is a run-time failure, not a default.
    assert set(adapter.GATE_ENVELOPES) == {"GATE-PLAN", "GATE-SETUP", "GATE-RUN"}
    for gate, envelope in adapter.GATE_ENVELOPES.items():
        assert set(envelope) == {"decision", "payload_key", "flags"}, gate
        assert envelope["payload_key"] == "binding", gate


def test_preflight_bridge_reads_this_suts_spelling(adapter):
    assert adapter.preflight_captured_at({"readinessObservedAt": "2026-09-15T12:27:08Z"})
    for bad in ({}, {"readinessObservedAt": ""}, {"readinessObservedAt": 123}, "not-a-mapping"):
        with pytest.raises(Exception):
            adapter.preflight_captured_at(bad)


# ---------------------------------------------------------------------------
# Document KEYS, not just attribute names.
#
# The attribute scan above derives every `adapter.<name>` the library reaches
# for. That is why it did not catch the eighth defect of this class:
# `gate_run_flow.cmd_execute` evaluates `package.readiness["release"]`, which
# is a *document key*, not an attribute access, and OTel's readiness document
# (`_exact()`-pinned, no `release`) raises `KeyError` there -- after
# gate-run.json is already written, i.e. after the one-shot marker is spent.
#
# So this half of the file scans for the other half of the surface: every
# string-literal key the shared library and the SUT's own drivers read out of
# a mapping. The discovered set is pinned against a hand-classified table
# below, so a NEW library call site -- any new key, any new document -- fails
# here rather than on a host three weeks later. Classifying a new row is a
# deliberate act; inheriting a TeaStore spelling silently is what cost eight
# campaign attempts.
#
# WHAT THIS SCAN CANNOT SEE, stated rather than implied:
#   * dynamic keys: `receipt[key] for key in binding_keys`
#     (campaign_setup_flow:186, gate_setup_flow:199), `observed[key]`
#     (campaign_authorization:130-131), `authorization[name]`
#     (drivers/gate_run.py:130). `DYNAMIC_SITES` pins those separately so a
#     new one is at least noticed; what they resolve to at run time is not
#     checkable here.
#   * value-format conflicts: a key that IS supplied with a value the library
#     rejects. Defect 7 (`_SAFE_CAMPAIGN_SLUG` accepting hyphens, not
#     underscores) was exactly this and no key scan can see it.
#   * argument-arity conflicts: `authorize_from_files` takes four paths on the
#     contract and six on OTel.
#   * producer classification below is by reading the write site, not by
#     executing every path that can reach a read.
# ---------------------------------------------------------------------------

import ast

SCAN_DIRS = (
    LIB,
    ROOT / "modules" / "otel-demo" / "drivers",
)


class _KeyReads(ast.NodeVisitor):
    """Literal-key reads, keyed by the dotted/subscript chain they read from."""

    def __init__(self, module):
        self.module = module
        self.sites = set()
        self.dynamic = set()
        self.call_bases = set()

    def _chain(self, node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = self._chain(node.value)
            return f"{base}.{node.attr}" if base else None
        if isinstance(node, ast.Subscript):
            base = self._chain(node.value)
            if base is None:
                return None
            index = node.slice
            if isinstance(index, ast.Constant) and isinstance(index.value, str):
                return f"{base}[{index.value!r}]"
            return f"{base}[?]"
        return None  # ast.Call and anything else: reported as a call base

    def _record(self, node, base_node, key):
        base = self._chain(base_node)
        if base is None:
            # Previously invisible: a literal key read off a call result.
            self.call_bases.add((self.module, ast.unparse(base_node)[:80], key))
        else:
            self.sites.add((base, key))

    def visit_Subscript(self, node):
        index = node.slice
        if isinstance(index, ast.Constant) and isinstance(index.value, str):
            self._record(node, node.value, index.value)
        elif not isinstance(index, ast.Slice) and not (
            isinstance(index, ast.Constant) and isinstance(index.value, int)
        ):
            base = self._chain(node.value)
            if base is not None and base not in _TYPING_BASES:
                self.dynamic.add((self.module, node.lineno, base))
        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in ("get", "pop", "setdefault") and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                self._record(node, func.value, first.value)
            else:
                base = self._chain(func.value)
                if base is not None and base not in _TYPING_BASES:
                    self.dynamic.add((self.module, node.lineno, f"{base}.{func.attr}"))
        self.generic_visit(node)


# `Callable[[], int]`, `Optional[Path]`, `tuple[str, ...]`, `list[str]` are
# type subscripts, not document reads.
_TYPING_BASES = {"Callable", "Optional", "tuple", "list", "dict", "frozenset", "Mapping"}


def _scan():
    sites, dynamic, call_bases = set(), set(), set()
    for directory in SCAN_DIRS:
        for path in sorted(directory.glob("*.py")):
            visitor = _KeyReads(f"{directory.name}/{path.name}")
            visitor.visit(ast.parse(path.read_text()))
            sites |= visitor.sites
            dynamic |= visitor.dynamic
            call_bases |= visitor.call_bases
    return sites, dynamic, call_bases


def document_key_sites():
    return _scan()[0]


# base -> who writes the document. "library" documents are written by the
# shared library itself and are not a bridge surface; "sut" documents come
# back from this SUT's adapter/transport/installer and must be supplied here.
PRODUCERS = {
    "admission": "sut",             # transport.admit_readiness
    "allocation": "sut",            # OTel's own candidate-target-allocation.json
    "allocation['source']": "sut",
    "authorization": "sut",         # adapter.setup_authorization / run_authorization
    "counts": "sut",                # OTel probe receipt, read by OTel's own driver
    "override": "sut",              # adapter.GATE_ENVELOPES, declared above
    "package.readiness": "sut",     # adapter.authorize_from_files -> readiness doc
    # (after the release bridge landed the library reads it through the
    #  `readiness` parameter of `_release_binding`, so the base is `readiness`)
    "pending": "library",           # campaign_setup_flow writes it
    "pending['invariants']": "library",
    "precheck": "sut",              # transport.remote_precheck
    "readiness": "sut",             # target-produced readiness
    "receipt": "mixed",             # library derivation receipt AND install/probe receipts
    "record": "library",            # campaign_authorization builds it
    "remote_input": "sut",          # transport.build_runtime_package
    "result.release_manifest": "sut",
    "result.target_proof": "sut",
    "status": "sut",                # transport.remote_status
    "systemd": "sut",               # status["systemdState"]
}

# Every (base, key) the scan finds today, with its disposition. A new row must
# be classified deliberately; an unclassified one fails the pin test.
#   supplied  -- OTel produces this key under this exact spelling
#   bridged   -- OTel spells it differently and declares an opt-in adapter hook
#   fallback  -- OTel does not produce it; the library documents a fallback
#   cosmetic  -- OTel does not produce it; read via .get() into a printed or
#                audited field only, so it renders as None and blocks nothing
#   library   -- written by the shared library itself, not a bridge surface
DISPOSITION = {
    ("admission", "readinessCanonicalSha256"): "supplied",
    ("allocation", "source"): "supplied",
    ("allocation['source']", "upstreamCommit"): "supplied",
    ("authorization", "setupId"): "fallback",
    ("counts", "false"): "supplied",
    ("counts", "true"): "supplied",
    ("override", "decision"): "supplied",
    ("override", "flags"): "supplied",
    ("override", "payload_key"): "supplied",
    ("readiness", "release"): "bridged",   # the default branch of _release_binding
    ("pending", "deadline"): "library",
    ("pending", "expectedText"): "library",
    ("pending", "invariants"): "library",
    ("pending", "proposedAt"): "library",
    ("pending['invariants']", "compiledPlanCanonicalSha256"): "library",
    ("pending['invariants']", "descriptorCanonicalSha256"): "library",
    ("pending['invariants']", "runs"): "library",
    ("precheck", "detail"): "supplied",
    ("precheck", "ok"): "supplied",
    ("readiness", "capturedAt"): "bridged",
    ("receipt", "campaignId"): "library",
    ("receipt", "derivedAt"): "library",
    ("receipt", "disabledOtlpConnections"): "supplied",
    ("receipt", "enabledOtlpConnections"): "supplied",
    ("receipt", "gatePlanCanonicalSha256"): "library",
    ("receipt", "imageBuildReceiptSha256"): "cosmetic",
    ("receipt", "kind"): "supplied",
    ("receipt", "preflightCapturedAt"): "library",
    ("receipt", "probeScriptSha256"): "supplied",
    ("receipt", "releaseRoot"): "supplied",
    ("receipt", "result"): "supplied",
    ("receipt", "runtimeAuthorized"): "supplied",
    ("receipt", "upstreamCommit"): "supplied",
    ("record", "approvedAt"): "library",
    ("record", "deadline"): "library",
    ("record", "invariants"): "library",
    ("remote_input", "admissionCanonicalSha256"): "supplied",
    ("remote_input", "campaignId"): "supplied",
    ("result.release_manifest", "bundleSha256"): "cosmetic",
    ("result.release_manifest", "bundleSizeBytes"): "cosmetic",
    ("result.target_proof", "capturedAt"): "cosmetic",
    ("status", "abortExists"): "supplied",
    ("status", "journalRows"): "supplied",
    ("status", "leaseHeld"): "supplied",
    ("status", "state"): "supplied",
    ("status", "systemdState"): "supplied",
    ("status", "terminalExists"): "supplied",
    ("systemd", "activeState"): "supplied",
    ("systemd", "result"): "supplied",
    ("systemd", "subState"): "supplied",
}

# The dynamic sites, pinned so a new one is noticed even though what it
# resolves to at run time is not checkable here.
DYNAMIC_SITES = {
    ("gate_driver/campaign_authorization.py", 130, "recorded.get"),
    ("gate_driver/campaign_authorization.py", 130, "observed"),
    ("gate_driver/campaign_authorization.py", 131, "recorded.get"),
    ("gate_driver/campaign_authorization.py", 131, "observed"),
    ("gate_driver/campaign_setup_flow.py", 186, "receipt"),
    ("gate_driver/gate_documents.py", 112, "DEFAULT_GATE_ENVELOPES"),
    ("gate_driver/gate_documents.py", 117, "declared"),
    ("gate_driver/gate_setup_flow.py", 199, "receipt"),
    ("gate_driver/module_loader.py", 49, "sys.modules"),
    ("drivers/gate_run.py", 130, "authorization"),
}


def test_every_document_key_site_is_classified():
    sites = document_key_sites()
    assert len(sites) >= 40, "the key scan found almost nothing; it is broken"
    unclassified = sorted(site for site in sites if site not in DISPOSITION)
    assert not unclassified, (
        "new document-key call site(s) with no declared disposition: %s. Classify "
        "each as supplied/bridged/fallback/cosmetic/library and, if OTel does not "
        "supply the key, declare an adapter bridge -- do NOT widen the shared "
        "library, which TeaStore and Hotel depend on." % unclassified
    )
    stale = sorted(site for site in DISPOSITION if site not in sites)
    assert not stale, "classified sites no longer present in the source: %s" % stale


def test_no_unclassified_dynamic_key_site_appeared():
    _, dynamic, _ = _scan()
    assert sorted(dynamic - DYNAMIC_SITES) == []


def test_no_unclassified_call_base_key_read_appeared():
    # `f()['k']` has no name to key on, so the base-chain scan cannot pin it;
    # the count is pinned instead. Defect 5 lived in a driver, not the library,
    # which is why the drivers are in SCAN_DIRS at all.
    _, _, call_bases = _scan()
    assert len(call_bases) == 2, sorted(call_bases)


def test_every_sut_produced_key_is_supplied_or_bridged(adapter):
    unsupplied = sorted(
        (base, key) for (base, key), disposition in DISPOSITION.items()
        if PRODUCERS.get(base) == "sut" and disposition not in ("supplied", "bridged", "fallback", "cosmetic")
    )
    assert not unsupplied, unsupplied
    # The two bridges the library actually consults, by name.
    assert callable(adapter.preflight_captured_at)
    assert callable(adapter.release_binding)


def test_release_bridge_reads_this_suts_spelling(adapter):
    # OTel spells the release binding `installedBindings`; its readiness
    # document cannot carry a `release` alias because the validator pins the
    # top-level key set exactly.
    binding = {"setupReceiptSha256": "a" * 64, "imageIds": {}}
    assert adapter.release_binding({"installedBindings": binding}) == binding
    for bad in ({}, {"installedBindings": {}}, {"release": binding}, {"installedBindings": "x"}, "nope"):
        with pytest.raises(Exception):
            adapter.release_binding(bad)
