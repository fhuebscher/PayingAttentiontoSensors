"""teastore-offpath-v1: the off-path pause of ``recommender`` beside the on-path ``auth`` freeze (BUDGET_TEASTORE_OFFPATH.md).

Section 1 (this commit): the per-cell fault controller pauses the allow-listed service of the scenario, not a hard-coded
``auth``.  Every test runs the real ``performance_campaign.inject_fault`` against a faked Docker that keeps one state per
container, so a pause of the wrong container shows in the fake's own state, not in a string the code wrote.

The frozen and earlier sweep epochs reach the same code with ``auth-freeze``; their receipts are pinned by
tests/test_teastore_traffic_sweep.py (``test_frozen_fault_receipt_is_unchanged_by_the_sweep_code``) and
tests/test_teastore_sweep_b.py, which keep passing unchanged.
"""
from __future__ import annotations

import json
import types

import pytest

import test_teastore_traffic_sweep as sw


MODULE = sw.MODULE
IDS = {
    "auth": "a" * 64, "recommender": "b" * 64, "persistence": "c" * 64, "webui": "d" * 64,
    "image": "e" * 64, "registry": "f" * 64,
}
H4_H10 = {"version": "h4-h10-v1", "noProbeDuringFault": True, "freezeStamps": True,
          "freezeFailure": "record-not-block", "freezeEventToleranceSeconds": 0.25}


class PerContainerDocker:
    """A fake host with one pause state per container, a Docker event log, and a record of every argv."""

    def __init__(self, clock):
        self.clock = clock
        self.paused = {identifier: False for identifier in IDS.values()}
        self.events: list = []
        self.calls: list = []

    def _pause(self, service: str, paused: bool) -> None:
        identifier = IDS[service]
        self.paused[identifier] = paused
        self.events.append({
            "Type": "container", "Action": "pause" if paused else "unpause",
            "Actor": {"ID": identifier, "Attributes": {"name": "teastore_%s_1" % service}},
            "time": int(self.clock.wall), "timeNano": int(round((self.clock.wall + 0.1) * 1e9))})

    def __call__(self, args, *, output=None, check=True):
        args = list(args)
        self.calls.append((self.clock.monotonic(), args))
        stdout, cost = "", 0.0
        if args[:2] == ["docker", "compose"] and "ps" in args:
            stdout, cost = IDS[args[-1]] + "\n", 0.3
        elif args[:2] == ["docker", "compose"] and args[-2] in ("pause", "unpause"):
            self._pause(args[-1], args[-2] == "pause")
            cost = 0.25
        elif args[:2] == ["docker", "inspect"]:
            paused = self.paused[args[-1]]
            stdout = json.dumps([{"State": {"Running": True, "Paused": paused,
                                            "Status": "paused" if paused else "running"},
                                  "HostConfig": {"NanoCpus": 0}}])
            cost = 0.05
        elif args[:3] == ["timeout", "30", "docker"] and args[3] == "events":
            container = next(args[i + 1].split("=", 1)[1] for i, value in enumerate(args)
                             if value == "--filter" and args[i + 1].startswith("container="))
            wanted = {args[i + 1].split("=", 1)[1] for i, value in enumerate(args) if value == "--filter"
                      and args[i + 1].startswith("event=")}
            stdout = "".join(json.dumps(event) + "\n" for event in self.events
                             if event["Action"] in wanted and event["Actor"]["ID"] == container)
            cost = 0.05
        elif args[0] == "curl":
            stdout, cost = "OK " * 5, 0.1
        self.clock.advance(cost)
        return types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def _kit(producer, monkeypatch):
    clock = sw.FakeClock()
    fake = PerContainerDocker(clock)
    monkeypatch.setattr(producer, "time", clock)
    monkeypatch.setattr(producer, "command", fake)
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "teastore_candidate_0123456789abcdef")
    return clock, fake


def _timing(fault: str, target: str, harness=H4_H10) -> dict:
    """A compiled sweep cell's timing of a pause fault: the sweep's auth-pause cell with the fault and its target."""
    run_id = sw.sweep.run_id_for("auth-freeze-effect", 1.0, 1, "full")
    timing = sw.sweep.cell_timing(run_id, "auth-freeze-effect", 1.0)
    timing.update({"fault": fault, "faultTarget": target, "faultHarness": dict(harness) if harness else None})
    return timing


def _inject(producer, clock, service, fault, timing, tmp_path):
    barrier = clock.monotonic() + 15.0
    image = {"containerId": IDS[service], "declaredImage": "descartesresearch/teastore-" + service,
             "containerImageId": "sha256:" + "d" * 64, "imageInspectId": "sha256:" + "d" * 64, "repoDigests": []}
    receipt = producer.inject_fault(
        fault, timing["faultOnsetSeconds"], timing["faultHoldSeconds"], tmp_path, "full",
        measurement_barrier_epoch=clock.time() + 15.0, measurement_barrier_monotonic=barrier,
        measurement_barrier_id="barrier-" + "e" * 32, target_image=image, sweep_timing=timing)
    return receipt


@pytest.fixture
def producer():
    return sw.load("teastore_offpath_performance_campaign", MODULE / "execution/performance_campaign.py")


# ------------------------------------------------------------------ 1. the pause target is an allow-list, not "auth"
@pytest.mark.parametrize("fault,service", [("auth-freeze", "auth"), ("recommender-pause", "recommender")])
def test_a_pause_fault_pauses_its_allow_listed_service_and_nothing_else(producer, tmp_path, monkeypatch, fault, service):
    clock, fake = _kit(producer, monkeypatch)
    receipt = _inject(producer, clock, service, fault, _timing(fault, service), tmp_path)
    assert receipt["successful"] is True, receipt["error"]
    assert receipt["scenario"] == fault and receipt["service"] == service
    assert receipt["targetContainerId"] == IDS[service]
    assert receipt["commandVector"][-2:] == ["pause", service]
    assert receipt["recoveryAction"]["commandVector"][-2:] == ["unpause", service]
    # The fake's own event log: exactly one pause then one unpause, both of the target, no other container touched.
    assert [(event["Action"], event["Actor"]["ID"]) for event in fake.events] == [
        ("pause", IDS[service]), ("unpause", IDS[service])]
    assert not any(fake.paused.values())
    # The H4 events query named the target container and the record found its pause and unpause.
    freeze = receipt["sweep"]["freezeStamps"]
    assert freeze["status"] == "recorded", freeze["failures"]
    assert freeze["targetContainerId"] == IDS[service]
    assert [row["action"] for row in freeze["events"]["rows"]] == ["pause", "unpause"]


def test_the_checker_sees_a_pause_aimed_at_the_wrong_container(producer, tmp_path, monkeypatch):
    """Planted defect for the test above: the allow-list entry of the recommender pause is changed to auth."""
    monkeypatch.setitem(producer.PAUSE_FAULT_SERVICES, "recommender-pause", "auth")
    clock, fake = _kit(producer, monkeypatch)
    # The plan still says recommender, so the controller refuses before it touches any container ...
    with pytest.raises(ValueError, match="not the allow-listed"):
        _inject(producer, clock, "recommender", "recommender-pause", _timing("recommender-pause", "recommender"),
                tmp_path)
    assert not any(args[-2:] in (["pause", "auth"], ["pause", "recommender"]) for _, args in fake.calls)
    # ... and a plan that agrees with the planted entry does pause auth, which the per-container state shows.
    clock, fake = _kit(producer, monkeypatch)
    receipt = _inject(producer, clock, "auth", "recommender-pause", _timing("recommender-pause", "auth"), tmp_path)
    assert receipt["commandVector"][-2:] == ["pause", "auth"] != ["pause", "recommender"]
    assert [event["Actor"]["ID"] for event in fake.events] == [IDS["auth"], IDS["auth"]]


@pytest.mark.parametrize("fault,wrong", [("recommender-pause", "auth"), ("recommender-pause", "persistence"),
                                         ("recommender-pause", "webui; rm"), ("auth-freeze", "recommender"),
                                         ("auth-freeze", None)])
def test_a_plan_whose_fault_target_is_not_the_allow_listed_service_is_refused(producer, tmp_path, monkeypatch,
                                                                              fault, wrong):
    clock, fake = _kit(producer, monkeypatch)
    timing = _timing(fault, "recommender")
    timing["faultTarget"] = wrong
    with pytest.raises(ValueError, match="allow-listed"):
        _inject(producer, clock, "recommender", fault, timing, tmp_path)
    assert fake.calls == [] and fake.events == []


@pytest.mark.parametrize("fault", ["recommender-pause", "persistence-cpu-throttle"])
def test_the_sweep_only_faults_are_refused_outside_the_sweep(producer, tmp_path, fault):
    with pytest.raises(ValueError, match="only in the traffic sweep"):
        producer.inject_fault(fault, 60, 60, tmp_path, "full")


@pytest.mark.parametrize("fault", ["web-pause", "pause", "recommender", "auth", "image-pause", ""])
def test_a_pause_scenario_outside_the_allow_list_is_unknown(producer, tmp_path, monkeypatch, fault):
    clock, fake = _kit(producer, monkeypatch)
    with pytest.raises(ValueError, match="unknown sweep fault"):
        _inject(producer, clock, "auth", fault, _timing("auth-freeze", "auth"), tmp_path)
    assert fake.calls == []


def test_the_allow_list_is_exactly_auth_and_recommender(producer):
    assert producer.PAUSE_FAULT_SERVICES == {"auth-freeze": "auth", "recommender-pause": "recommender"}
    assert producer.fault_service("persistence-crash") == producer.fault_service("persistence-cpu-throttle") == "persistence"
    assert producer.SWEEP_FAULTS == {"auth-freeze", "persistence-cpu-throttle", "recommender-pause"}
    # The frozen epoch's CLI fault set is unchanged: the off-path pause cannot be requested outside the sweep.
    assert producer.ALLOWED_FAULTS == {"none", "auth-freeze", "persistence-crash"}


def test_the_target_image_proof_follows_the_scenarios_service(producer):
    """The cell function binds the fault's image proof to the same service the controller pauses."""
    source = (MODULE / "execution/performance_campaign.py").read_text()
    assert 'runtime_images["services"][fault_service(args.fault)][key]' in source
    assert '"auth" if args.fault == "auth-freeze" else "persistence"' not in source


# ------------------------------------------------ 2. the validator replays a recommender pause like an auth pause
@pytest.fixture(scope="module")
def validator():
    return sw.load("teastore_offpath_validator", MODULE / "validation/candidate_pilot.py")


def _recorded(producer, tmp_path, monkeypatch, service: str, fault: str):
    clock, fake = _kit(producer, monkeypatch)
    timing = _timing(fault, service)
    receipt = _inject(producer, clock, service, fault, timing, tmp_path)
    assert receipt["successful"] is True, receipt["error"]
    return receipt, timing


def test_the_validator_knows_the_recommender_pause_and_its_service(validator):
    assert validator.FAULT_SERVICES["recommender-pause"] == "recommender"
    assert validator.PAUSE_SCENARIOS == {"auth-freeze", "recommender-pause"}
    # Every pause scenario of the validator is a pause scenario of the controller, with the same service.
    producer = sw.load("teastore_offpath_pc_for_validator", MODULE / "execution/performance_campaign.py")
    assert {scenario: validator.FAULT_SERVICES[scenario] for scenario in validator.PAUSE_SCENARIOS} == dict(
        producer.PAUSE_FAULT_SERVICES)


@pytest.mark.parametrize("fault,service", [("auth-freeze", "auth"), ("recommender-pause", "recommender")])
def test_the_h4_replay_accepts_a_recorded_pause(validator, producer, tmp_path, monkeypatch, fault, service):
    receipt, timing = _recorded(producer, tmp_path, monkeypatch, service, fault)
    problems = validator._freeze_stamp_problems(receipt, receipt["sweep"], timing["faultHarness"], timing, fault)
    assert problems == []
    assert validator._fault_harness_problem(receipt, receipt["sweep"], timing["faultHarness"], timing, fault) is None


@pytest.mark.parametrize("plant", ["event-of-another-container", "no-unpause-event", "readback-not-paused",
                                   "events-missing-as-for-a-throttle"])
def test_the_h4_replay_refuses_planted_defects_on_a_recommender_pause(validator, producer, tmp_path, monkeypatch, plant):
    receipt, timing = _recorded(producer, tmp_path, monkeypatch, "recommender", "recommender-pause")
    record = receipt["sweep"]
    freeze = record["freezeStamps"]
    if plant == "event-of-another-container":
        freeze["events"]["rows"][0]["containerId"] = IDS["auth"]
    elif plant == "no-unpause-event":
        freeze["events"]["rows"] = freeze["events"]["rows"][:1]
    elif plant == "readback-not-paused":
        freeze["readbacks"][1]["paused"] = False
    elif plant == "events-missing-as-for-a-throttle":
        freeze["events"], freeze["clock"] = None, None
    problems = validator._freeze_stamp_problems(receipt, record, timing["faultHarness"], timing, "recommender-pause")
    assert problems, plant


# =====================================================================================================================
# 3. the epoch teastore-offpath-v1: 30 cells, B's shape, three regimes, not activated
# =====================================================================================================================
import ast
import copy
import hashlib
import math
import subprocess
from pathlib import Path

import test_teastore_quiet_calibration as qc
import test_teastore_sweep_b as tb
import test_teastore_sweep_c as tcc

ROOT = sw.ROOT
OFFPATH = "teastore-offpath-v1"
OFFPATH_SELECTOR = {"schemaVersion": 1, "studyEpoch": OFFPATH}
C_HARNESS_COMMIT = "3b4a513ff3c4b00b65131dbc82ba1b472d1c0548"      # campaign C's activated harness (HEAD before this epoch)
REGIMES = ("no-fault-cost", "recommender-pause-effect", "auth-freeze-effect")
RATES = (10.0, 1.0)
o = sw.load("teastore_offpath_compiler_test", MODULE / "execution/candidate_offpath_ts.py")
b = tb.b
c = tcc.c
quiet = qc.quiet
sweep = sw.sweep
O_TARGET_FILES = ("execution/candidate_offpath_ts.py", "execution/study_epoch.py", "execution/performance_campaign.py",
                  "validation/candidate_pilot.py")
# What this epoch may change relative to campaign C's activated harness; every other file under modules/teastore and
# pipelines/campaigns must be byte-identical.  The selector joins the set with the activation commit (2026-10-14).
SELECTOR_RELATIVE = "modules/teastore/execution/study-epoch.json"
OFFPATH_ALLOWED = tcc.OFFPATH_MOVED | tcc.OFFPATH_ADDED | {SELECTOR_RELATIVE}


@pytest.fixture(scope="module")
def otree(tmp_path_factory):
    """Modules loaded from a tree copy whose selector names the off-path epoch."""
    return tb._tree(sw._copy_tree(tmp_path_factory.mktemp("teastore-offpath-tree"), OFFPATH_SELECTOR))


def _plan() -> dict:
    return o.compile_plan(o.load_descriptor())


def _cells() -> list:
    return o.flatten_cells(_plan())


def _cell(regime: str, rate: float, block: int = 1) -> dict:
    return next(cell for cell in _cells() if cell["runKey"]["regime"] == regime
                and cell["timing"]["journeysPerSecond"] == rate and cell["runKey"]["block"] == block)


def _run_ids(plan: dict) -> set:
    return {cell["runId"] for block in plan["blocks"] for cell in block["cells"]}


def _hours(seconds: float) -> int:
    return int(math.ceil(seconds / 3600.0))


# ------------------------------------------------------------------------------------------------ 3.1 the plan
def test_the_plan_is_30_cells_5_blocks_3_regimes_2_rates_deterministic_and_pinned():
    descriptor = o.load_descriptor()
    assert o.canonical_sha256(descriptor) == o.EXPECTED_DESCRIPTOR_SHA256
    # The checked-in descriptor is the generator's output, byte for byte (regenerate, never hand-edit).
    assert o.DEFAULT_DESCRIPTOR.read_bytes() == o.descriptor_bytes()
    first, second = o.compile_plan(descriptor), o.compile_plan(copy.deepcopy(descriptor))
    assert first == second and o.canonical_sha256(first) == o.EXPECTED_PLAN_SHA256
    assert o.validate_plan(descriptor, first) is first
    assert first["runCount"] == o.TOTAL_RUNS == 30 and first["studyEpoch"] == OFFPATH
    assert (o.REGIMES, o.RATES, o.BLOCKS, o.EPISODES, o.CELLS_PER_BLOCK) == (REGIMES, RATES, 5, 5, 6)
    assert descriptor["schedule"]["seed"] == o.SCHEDULE_SEED == 20261014
    assert len({o.SCHEDULE_SEED, c.SCHEDULE_SEED, b.SCHEDULE_SEED, sweep.SCHEDULE_SEED, quiet.SCHEDULE_SEED}) == 5
    assert descriptor["schedule"]["version"] == "offpath-schedule-v1" and descriptor["schedule"]["leadCell"] is None
    cells = o.flatten_cells(first)
    assert len(cells) == 30 and len({cell["runId"] for cell in cells}) == 30
    pairs = sorted((regime, rate) for regime in REGIMES for rate in RATES)
    for block in first["blocks"]:
        assert sorted((x["runKey"]["regime"], x["timing"]["journeysPerSecond"]) for x in block["cells"]) == pairs
        assert [x["ordinalPosition"] for x in block["cells"]] == list(range(1, 7))
    assert [block["block"] for block in first["blocks"]] == [1, 2, 3, 4, 5]
    assert len({tuple(block["order"]) for block in first["blocks"]}) == 5       # shuffled per block


def test_the_regime_ids_and_targets_are_the_ones_the_reader_registry_admits():
    """Reader v3.3 (parameters_v3_3.json) admits exactly these ids and targets for teastore-offpath-v1."""
    assert o.REGIMES == ("no-fault-cost", "recommender-pause-effect", "auth-freeze-effect")
    assert o.FAULTS == {"no-fault-cost": None, "recommender-pause-effect": "recommender-pause",
                        "auth-freeze-effect": "auth-freeze"}
    assert o.FAULT_TARGETS == {"auth-freeze": "auth", "recommender-pause": "recommender"}
    # Every earlier TeaStore epoch names its no-fault regime the same way.
    assert all("no-fault-cost" in module.REGIMES for module in (sweep, quiet, b, c))
    descriptor = o.load_descriptor()
    assert [(row["id"], row["fault"], row["artifactRootClass"], row.get("pathRelation"))
            for row in descriptor["design"]["regimes"]] == [
        ("no-fault-cost", None, "cost", None),
        ("recommender-pause-effect", "recommender-pause", "effect/recommender-pause", "off-path"),
        ("auth-freeze-effect", "auth-freeze", "effect/auth-freeze", "on-path-control")]
    for cell in _cells():
        regime = cell["runKey"]["regime"]
        assert cell["timing"]["faultTarget"] == {"no-fault-cost": None, "recommender-pause-effect": "recommender",
                                                 "auth-freeze-effect": "auth"}[regime]


def test_the_compilers_pause_targets_are_the_fault_controllers_allow_list(producer):
    assert dict(o.FAULT_TARGETS) == dict(producer.PAUSE_FAULT_SERVICES)


def test_the_target_check_catches_a_cell_that_pauses_the_wrong_service():
    """Planted defect: a recommender-pause cell whose target is auth (the on-path service) is a geometry error."""
    plan = copy.deepcopy(_plan())
    cell = next(x for x in o.flatten_cells(plan) if x["runKey"]["regime"] == "recommender-pause-effect")
    o._check_geometry(plan)
    cell["timing"]["faultTarget"] = "auth"
    with pytest.raises(o.ProtocolError, match="target"):
        o._check_geometry(plan)


def test_no_run_id_equals_that_of_another_epoch():
    mine = _run_ids(_plan())
    assert all(run_id.startswith(OFFPATH + "/") and run_id.endswith("/full/a01") for run_id in mine)
    others = {"sweep": _run_ids(sweep.compile_plan(sweep.load_descriptor())),
              "quiet": _run_ids(quiet.compile_plan(quiet.load_descriptor())),
              "B": _run_ids(b.compile_plan(b.load_descriptor())), "C": _run_ids(c.compile_plan(c.load_descriptor()))}
    for name, run_ids in others.items():
        assert not mine & run_ids, name
    with pytest.raises(o.ProtocolError):
        o._run_id_parts(sorted(others["C"])[0])
    with pytest.raises(c.ProtocolError):
        c._run_id_parts(sorted(mine)[0])
    with pytest.raises(o.ProtocolError):
        o._run_id_parts(o.run_id_for("persistence-cpu-throttle-effect", 1.0, 1, "full"))


def test_the_run_id_collision_check_catches_a_planted_collision(monkeypatch):
    """Planted defect: the off-path regimes compiled under C's epoch name collide with C for the shared regimes."""
    monkeypatch.setattr(o, "EPOCH", c.EPOCH)
    planted = {o.run_id_for(row["regime"], row["rate"], block, "full")
               for block in range(1, 4) for row in o.block_order(block)}
    assert planted & _run_ids(c.compile_plan(c.load_descriptor()))


def test_the_order_is_recomputed_from_the_recorded_encoding():
    schedule = o.load_descriptor()["schedule"]
    for receipt in schedule["blocks"]:
        pairs = [(regime, float(rate)) for regime in REGIMES for rate in RATES]
        for index in range(len(pairs) - 1, 0, -1):          # the recorded Fisher-Yates, written out again
            text = "\0".join([str(schedule["seed"]), OFFPATH, "block-%02d" % receipt["block"], "draw-%d" % index,
                              schedule["version"]])
            other = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (index + 1)
            pairs[index], pairs[other] = pairs[other], pairs[index]
        expected = [o.run_id_for(regime, rate, receipt["block"], "full") for regime, rate in pairs]
        assert receipt["runIds"] == expected and receipt["orderSha256"] == o.canonical_sha256(expected)


# -------------------------------------------------------------------------------------- 3.2 B's shape, exactly
def test_every_cell_is_bs_shape_cell_but_for_the_onset_and_the_recommenders_fault_name():
    strata = {}
    for cell in _cells():
        timing, regime, rate = cell["timing"], cell["runKey"]["regime"], cell["timing"]["journeysPerSecond"]
        shape = "auth-freeze-effect" if regime == "recommender-pause-effect" else regime
        twin = b.compiled_cell(b.run_id_for(shape, rate, 1, "full"))
        assert set(timing) == set(twin["timing"])
        differing = {key for key in timing if timing[key] != twin["timing"][key]}
        allowed = set(o.ONSET_TIMING_KEYS) | (set(o.FAULT_TIMING_KEYS) if regime == "recommender-pause-effect" else set())
        assert differing <= allowed and set(o.OWN_TIMING_KEYS) == set(o.ONSET_TIMING_KEYS) | set(o.FAULT_TIMING_KEYS)
        if regime == "recommender-pause-effect":
            assert {"fault", "faultTarget"} <= differing
            assert (timing["fault"], timing["faultTarget"]) == ("recommender-pause", "recommender")
            assert (twin["timing"]["fault"], twin["timing"]["faultTarget"]) == ("auth-freeze", "auth")
        offset = timing["faultOnsetPhaseOffsetSeconds"]
        assert timing["faultOnsetSeconds"] == round(60 + offset, 6)
        assert 0.0 <= offset < 1.0 / rate
        strata.setdefault((regime, rate), []).append(int(offset * rate * 5))
        # application.log (every service, including the registry) is retained in EVERY cell of this epoch.
        assert timing["applicationLogTimestamps"] is True
        if regime == "no-fault-cost":
            assert timing["faultHarness"] is None and timing["minimumActualStartsByPhase"] is None
        else:
            assert timing["faultHarness"] == b.FAULT_HARNESS == o.FAULT_HARNESS
            assert timing["minimumActualStartsByPhase"] == sweep.phase_floors(rate, 180, timing["faultOnsetSeconds"], 60)
            assert timing["drainAllowanceSeconds"] == 17.0
            assert timing["faultHoldSeconds"] == 60 and timing["cpuThrottleCpus"] is None
        assert timing["concurrency"] == 240 and timing["warmupSeconds"] == 30 and timing["measurementSeconds"] == 180
    # Each (regime, rate) pair's 5 blocks take the 5 fifths of its inter-arrival, one each (B's stratification).
    assert len(strata) == 6 and all(sorted(values) == [0, 1, 2, 3, 4] for values in strata.values())


def test_the_retained_log_flag_check_catches_a_cell_without_application_log(monkeypatch):
    """Planted defect: B's shape with the log flag off would drop the registry lines; the compiler refuses it."""
    real = o.b.cell_timing
    monkeypatch.setattr(o.b, "cell_timing", lambda *args: {**real(*args), "applicationLogTimestamps": False})
    with pytest.raises(o.ProtocolError, match="application.log"):
        o.cell_timing(o.run_id_for("recommender-pause-effect", 1.0, 1, "full"), "recommender-pause-effect", 1.0)


def test_the_descriptor_differs_from_bs_only_where_the_epoch_differs():
    base, mine = b.load_descriptor(), o.load_descriptor()
    changed = {key for key in set(base) | set(mine) if base.get(key) != mine.get(key)}
    assert changed == {"id", "declaration", "workload", "design", "timing", "schedule", "groundTruth", "faultParameters",
                       "collection", "outcomes", "analysis", "continuation", "derivedFrom"}
    for key in ("schemaVersion", "status", "module", "targetHost", "source", "runIdentity", "systemSamples",
                "postureProof", "queueProof", "missingness", "evidence", "protocolGates"):
        assert mine[key] == base[key], key
    assert mine["timing"]["faultHarness"] == base["timing"]["faultHarness"]
    assert mine["workload"]["journeysPerSecondLevels"] == [10.0, 1.0]
    assert set(mine["faultParameters"]) == {"auth-freeze", "recommender-pause"}
    assert mine["faultParameters"]["recommender-pause"]["command"] == "docker compose pause recommender"
    assert [row["scenario"] for row in mine["groundTruth"]["fault"]["scenarioContracts"]] == [
        "auth-freeze", "recommender-pause"]
    assert "registryLog" in mine["collection"] and "Removed" in mine["collection"]["registryLog"]
    assert mine["derivedFrom"]["studyEpoch"] == b.EPOCH
    assert mine["derivedFrom"]["descriptorCanonicalSha256"] == tcc.B_DESCRIPTOR_SHA256
    assert mine["derivedFrom"]["planCanonicalSha256"] == tcc.B_PLAN_SHA256


def test_a_hand_edited_descriptor_is_refused(tmp_path):
    document = copy.deepcopy(o.load_descriptor())
    document["design"]["rates"] = [10.0, 1.0, 0.2]
    path = tmp_path / "descriptor.json"
    path.write_text(json.dumps(document))
    with pytest.raises(o.ProtocolError, match="differs"):
        o.load_descriptor(path)


def test_o_exposes_every_name_of_bs_compiler():
    assert {name for name in vars(b) if not name.startswith("__")} - set(vars(o)) == set()


# --------------------------------------------------------------------------------------------- 3.3 sizing
def test_the_window_ends_by_10_00z_when_launched_at_03_30z():
    """Launch 03:30Z; setup is inside the plan's prepare reserve; deadline 10:00Z (BUDGET_TEASTORE_OFFPATH.md)."""
    deadline_seconds = 6.5 * 3600
    assert o.TOTAL_RUNS == 30
    assert (o.RUN_WINDOW_HOURS, o.MAXIMUM_WALL_SECONDS) == (5, 18_000)
    # The plan's own wall bound (budget rule 525 s per cell, 1800 s prepare reserve, 300 s cleanup) fits.
    assert o.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS + o.PREPARE_RESERVE_SECONDS <= o.MAXIMUM_WALL_SECONDS
    # Measured: campaign C's gaps (same host, harness and shape), per (regime, rate); recommender pause = auth pause.
    measured = o.MEASURED_CELL_PERIOD_SECONDS["meanByRegimeAndRate"]
    per_block = (measured["no-fault-cost/r10"] + measured["no-fault-cost/r1"]
                 + 2 * (measured["auth-freeze-effect/r10"] + measured["auth-freeze-effect/r1"]))
    expected = 5 * per_block + 1800
    worst = 30 * o.MEASURED_CELL_PERIOD_SECONDS["maximum"] + 1800
    assert expected < worst < o.MAXIMUM_WALL_SECONDS <= deadline_seconds
    # Five blocks is a choice, not a constraint: six (36 cells) would still fit the plan's own bound in 6 h.
    assert _hours(36 * o.CELL_PERIOD_ESTIMATE_SECONDS + o.CLEANUP_RESERVE_SECONDS + o.PREPARE_RESERVE_SECONDS) == 6


def test_the_sizing_check_catches_a_cell_count_that_overruns():
    """Planted defect: 12 blocks (72 cells) would need a window far past the deadline."""
    total = len(o.REGIMES) * len(o.RATES) * 12
    window = _hours(total * o.CELL_PERIOD_ESTIMATE_SECONDS + o.CLEANUP_RESERVE_SECONDS + o.PREPARE_RESERVE_SECONDS)
    assert window * 3600 > 6.5 * 3600


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="no system python3 (3.9 on the hosts)")
def test_plan_digest_is_identical_under_python39(tmp_path):
    result = subprocess.run(
        ["/usr/bin/python3", "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I",
         str(MODULE / "execution/candidate_offpath_ts.py")],
        capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["planCanonicalSha256"] == o.EXPECTED_PLAN_SHA256
    assert report["descriptorCanonicalSha256"] == o.EXPECTED_DESCRIPTOR_SHA256
    assert report["runCount"] == 30 and report["runWindowHours"] == 5
    assert report["firstRunId"].startswith(OFFPATH + "/")


# --------------------------------------------------------------- 3.4 the other epochs unchanged, not activated
def test_the_off_path_epoch_is_activated_and_the_earlier_epochs_keep_their_pins():
    """The committed selector (not a copy) names the off-path epoch, and the tree runs it."""
    assert json.loads((ROOT / SELECTOR_RELATIVE).read_text()) == OFFPATH_SELECTOR
    epoch = sw.load("teastore_offpath_committed_epoch", MODULE / "execution/study_epoch.py")
    active = epoch.active(ROOT)
    assert (active["studyEpoch"], active["runCount"], active["runWindowHours"]) == (OFFPATH, 30, 5)
    assert active["compilerRelative"] == "modules/teastore/execution/candidate_offpath_ts.py"
    assert epoch.sweep_compiler(ROOT).EXPECTED_PLAN_SHA256 == o.EXPECTED_PLAN_SHA256
    assert c.EXPECTED_DESCRIPTOR_SHA256 == "ee01552936cfcef21b0826480a1c844e30aa67b418a99555e9f163a270c49711"
    assert c.EXPECTED_PLAN_SHA256 == "e55b4f59e3ff8895b3f7d44d89114436fae89b6096fc7d6204d9e0579872eb29"
    assert (b.EXPECTED_DESCRIPTOR_SHA256, b.EXPECTED_PLAN_SHA256) == (tcc.B_DESCRIPTOR_SHA256, tcc.B_PLAN_SHA256)
    assert sweep.canonical_sha256(sweep.compile_plan(sweep.load_descriptor())) == tcc.SWEEP_PLAN_SHA256
    assert quiet.canonical_sha256(quiet.compile_plan(quiet.load_descriptor())) == tcc.QUIET_PLAN_SHA256
    assert c.canonical_sha256(c.compile_plan(c.load_descriptor())) == c.EXPECTED_PLAN_SHA256
    assert tcc._changed_since(C_HARNESS_COMMIT) <= OFFPATH_ALLOWED, tcc._changed_since(C_HARNESS_COMMIT) - OFFPATH_ALLOWED
    for relative in ("modules/teastore/execution/candidate_sweep.py", sweep.DESCRIPTOR_RELATIVE,
                     "modules/teastore/execution/candidate_quiet.py", quiet.DESCRIPTOR_RELATIVE,
                     "modules/teastore/execution/candidate_sweep_b.py", b.DESCRIPTOR_RELATIVE,
                     "modules/teastore/execution/candidate_sweep_c.py", c.DESCRIPTOR_RELATIVE,
                     "modules/teastore/execution/candidate_pilot.py", "pipelines/campaigns/teastore-candidate-pilot-sys-v1.json",
                     "modules/teastore/execution/candidate_runtime_adapter.py"):
        assert (ROOT / relative).read_bytes() == tcc._blob(C_HARNESS_COMMIT, relative), relative


def test_the_changed_file_check_catches_a_planted_edit_of_cs_compiler():
    """Planted defect for the test above: an edit of C's compiler is outside the allowed set."""
    planted = tcc._changed_since(C_HARNESS_COMMIT) | {"modules/teastore/execution/candidate_sweep_c.py"}
    assert not planted <= OFFPATH_ALLOWED
    planted = tcc._changed_since(C_HARNESS_COMMIT) | {"modules/teastore/execution/candidate_sweep_b.py"}
    assert not planted <= OFFPATH_ALLOWED


@pytest.mark.parametrize("selector,expected", [(None, sw.SWEEP), (tb.SWEEP_SELECTOR, sw.SWEEP),
                                                (tb.QUIET_SELECTOR, qc.QUIET), (tb.B_SELECTOR, tb.B),
                                                (tcc.C_SELECTOR, tcc.C), (OFFPATH_SELECTOR, OFFPATH)])
def test_the_sweep_mode_compiler_follows_the_selector(tmp_path, selector, expected):
    root = sw._copy_tree(tmp_path, selector)
    epoch = sw.load("teastore_offpath_resolution_epoch", root / "modules/teastore/execution/study_epoch.py")
    assert epoch.sweep_compiler(root).EPOCH == expected


def test_the_selector_activates_the_off_path_epoch_in_every_runtime_file(otree):
    epoch = otree["epoch"].active(otree["root"])
    assert (epoch["studyEpoch"], epoch["sweep"], epoch["runCount"], epoch["runWindowHours"]) == (OFFPATH, True, 30, 5)
    assert epoch["regimes"] == REGIMES and epoch["scenarios"] == o.FAULTS and epoch["blocksPerRegime"] == 5
    assert epoch["maximumOrdinal"] == 6 and epoch["scheduleVersion"] == "offpath-schedule-v1"
    assert epoch["compilerRelative"] == "modules/teastore/execution/candidate_offpath_ts.py"
    assert epoch["descriptorRelative"] == "pipelines/campaigns/teastore-offpath-v1.json"
    assert epoch["outerLeaseScope"] == "entire-30-cell-one-shot" and epoch["maximumWallSeconds"] == 18_000
    assert epoch["additionalControllerPaths"] == dict(o.ADDITIONAL_CONTROLLER_PATHS)
    assert otree["validator"].EPOCH == epoch and otree["validator"].SWEEP is True
    assert otree["validator"].SCENARIOS == {"recommender-pause-effect": "recommender-pause",
                                            "auth-freeze-effect": "auth-freeze"}
    assert otree["readiness"].EPOCH == epoch
    assert set(otree["witness"].EFFECT_REGIMES) == {"recommender-pause-effect", "auth-freeze-effect"}
    assert set(otree["native_token"].EFFECT_REGIMES) == {"recommender-pause-effect", "auth-freeze-effect"}
    assert set(otree["adapter"].CONTROLLER_PATHS) >= set(o.ADDITIONAL_CONTROLLER_PATHS)
    assert otree["producer"].CANDIDATE_EPOCH == epoch


@pytest.mark.parametrize("selector", [
    {"schemaVersion": 1, "studyEpoch": "teastore-offpath-v2"},
    {"schemaVersion": True, "studyEpoch": OFFPATH},
    {"schemaVersion": 1, "studyEpoch": OFFPATH, "extra": 1},
    {"schemaVersion": 1, "studyEpoch": OFFPATH + " "},
    b'{"schemaVersion": 1, "studyEpoch": "teastore-offpath-v1", "studyEpoch": "teastore-offpath-v1"}',
])
def test_a_malformed_off_path_selector_refuses_to_load(tmp_path, selector):
    root = sw._copy_tree(tmp_path, selector)
    epoch = sw.load("teastore_offpath_bad_selector_epoch", root / "modules/teastore/execution/study_epoch.py")
    with pytest.raises(epoch.SelectorError):
        epoch.active(root)


def test_a_selector_whose_compiler_names_another_epoch_refuses_to_load(tmp_path):
    root = sw._copy_tree(tmp_path, OFFPATH_SELECTOR)
    compiler = root / "modules/teastore/execution/candidate_offpath_ts.py"
    compiler.write_text(compiler.read_text().replace('EPOCH = "teastore-offpath-v1"', 'EPOCH = "teastore-offpath-v9"', 1))
    epoch = sw.load("teastore_offpath_wrong_compiler_epoch", root / "modules/teastore/execution/study_epoch.py")
    with pytest.raises(epoch.SelectorError):
        epoch.active(root)


# ----------------------------------------------- 3.5 materialize -> inspect -> contracts -> package, 30 cells
@pytest.fixture
def ochain(otree, tmp_path, monkeypatch):
    materialized, bindings, package, contracts = qc._contracts(otree, tmp_path, OFFPATH, monkeypatch)
    return {"materialized": materialized, "bindings": bindings, "package": package, "contracts": contracts}


def test_inspect_and_contracts_carry_the_compiled_timing_and_the_pause_target(otree, ochain):
    bindings, contracts = ochain["bindings"], ochain["contracts"]
    compiled = _cells()
    assert bindings.plan_sha256 == o.EXPECTED_PLAN_SHA256 and bindings.descriptor_sha256 == o.EXPECTED_DESCRIPTOR_SHA256
    assert list(bindings.run_ids) == [cell["runId"] for cell in compiled]
    assert bindings.campaign["scheduleVersion"] == "offpath-schedule-v1" and bindings.campaign["runCount"] == 30
    assert len({row["path"] for row in bindings.campaign["runs"]}) == 30
    assert set(bindings.controller_sha256) == set(otree["adapter"].CONTROLLER_PATHS)
    assert bindings.controller_sha256["offpath-descriptor"] == hashlib.sha256(
        (ROOT / "pipelines/campaigns/teastore-offpath-v1.json").read_bytes()).hexdigest()
    for contract, cell in zip(contracts, compiled):
        timing = cell["timing"]
        assert contract["runId"] == cell["runId"] and contract["window"]["timing"] == timing
        assert contract["target"]["outerLeaseScope"] == "entire-30-cell-one-shot"
        assert {"application.log"} <= set(contract["requiredArtifacts"])
        assert ("intervention.json" in contract["requiredArtifacts"]) is timing["faultApplied"]
        assert contract["faultGroundTruth"]["scenario"] == timing["fault"]
        assert contract["window"]["artifactRootClass"] == (
            "cost" if timing["fault"] is None else "effect/" + timing["fault"])


def test_the_runtime_package_round_trips_through_the_transport(otree, ochain):
    transport = otree["transport"]
    runtime_package = types.SimpleNamespace(
        bindings=ochain["bindings"], gate_run=ochain["package"].gate_run,
        gate_plan_sha256="4" * 64, readiness_sha256="5" * 64, gate_run_sha256="6" * 64,
        readiness={**ochain["package"].readiness, "release": {**ochain["package"].readiness["release"]}},
    )
    document = transport.build_runtime_package(runtime_package)
    document["releaseBindingSha256"] = document["cells"][0]["runtimeInputs"]["releaseBindingSha256"]
    for cell in document["cells"]:
        cell["runtimeInputs"]["readinessArchiveSha256"] = document["readinessArchiveSha256"]
    validated = transport.validate_runtime_package(document)
    assert validated["runCount"] == 30 and len(validated["cells"]) == 30
    planted = copy.deepcopy(document)
    planted["cells"] = planted["cells"][:29]
    with pytest.raises(transport.TransportError, match="exactly 30 cells"):
        transport.validate_runtime_package(planted)


def test_the_producer_accepts_every_compiled_contract_and_refuses_a_foreign_fault_target(otree, ochain, monkeypatch):
    producer = sw._producer_in_tree(otree, monkeypatch)
    for contract in ochain["contracts"]:
        contract = sw._with_real_controller_digests(otree, contract)
        producer._validate_candidate_contract(contract)
        args = producer._candidate_args(contract, Path("out"))
        assert args.timing == contract["window"]["timing"]
        assert args.fault == (contract["window"]["timing"]["fault"] or "none")
    # Planted: a recommender-pause contract whose timing names auth as the target is not the compiled cell.
    index = next(i for i, cell in enumerate(_cells()) if cell["timing"]["fault"] == "recommender-pause")
    contract = sw._with_real_controller_digests(otree, ochain["contracts"][index])
    contract["window"]["timing"]["faultTarget"] = "auth"
    with pytest.raises(RuntimeError):
        producer._validate_candidate_contract(contract)


# ------------------------------------- 3.6 the real validator on sealed recommender-pause cells (fake host data)
def _offpath_intervention(original):
    def build(timing: dict, regime: str) -> dict:
        receipt = original(timing, regime)
        if timing["fault"] == "recommender-pause":
            receipt["service"] = "recommender"
            receipt["commandVector"] = ["docker", "compose", "pause", "recommender"]
            receipt["recoveryAction"]["commandVector"] = ["docker", "compose", "unpause", "recommender"]
            receipt["commandResult"]["command"] = receipt["commandVector"]
            receipt["recoveryAction"]["commandResult"]["command"] = receipt["recoveryAction"]["commandVector"]
            receipt["operational"]["commandResults"] = [receipt["commandResult"],
                                                        receipt["recoveryAction"]["commandResult"]]
        return receipt
    return build


def _offpath_extras(original):
    def build(intervention: dict, timing: dict) -> dict:
        if intervention["scenario"] != "recommender-pause":
            return original(intervention, timing)
        # The H4 record builder of B's kit knows the auth pause; the recommender pause has the same record shape.
        extras = original({**intervention, "scenario": "auth-freeze"}, timing)
        extras["freezeStamps"]["scenario"] = "recommender-pause"
        return extras
    return build


@pytest.fixture
def as_offpath(monkeypatch):
    monkeypatch.setattr(sw, "SWEEP", OFFPATH)
    monkeypatch.setattr(sw, "_intervention", _offpath_intervention(sw._intervention))
    monkeypatch.setattr(tb, "_extras", _offpath_extras(tb._extras))


@pytest.mark.parametrize("regime,rate", [(regime, rate) for regime in REGIMES for rate in RATES])
def test_a_sealed_off_path_cell_is_accepted_at_every_regime_and_rate(otree, tmp_path, as_offpath, regime, rate):
    cell = _cell(regime, rate, block=3)
    root = tb._seal_b(otree, tmp_path / "run", cell)
    report = otree["validator"].validate_run(root, expected={**cell["runKey"], "runId": cell["runId"]})
    assert report["verdict"] == "pass", sw._failed_gates(report)
    if cell["timing"]["faultApplied"]:
        assert tb._h4_of(report) == {"status": "recorded", "reasons": [], "failureCount": 0}
        intervention = json.loads((root / "intervention.json").read_text())
        assert intervention["scenario"] == cell["timing"]["fault"]
        assert intervention["service"] == cell["timing"]["faultTarget"]
        assert intervention["commandVector"][-2:] == ["pause", cell["timing"]["faultTarget"]]


@pytest.mark.parametrize("plant", ["pause-command-names-auth", "unpause-command-names-auth", "service-field-auth",
                                   "probe-inside-window", "event-other-container"])
def test_planted_defects_on_a_recommender_pause_cell_block_or_are_recorded(otree, tmp_path, as_offpath, plant):
    cell = _cell("recommender-pause-effect", 1.0, block=2)
    root = tb._seal_b(otree, tmp_path / "run", cell)
    assert tb._verdict(otree, root, cell) == []

    def mutate(intervention):
        record = intervention["sweep"]
        if plant == "pause-command-names-auth":
            intervention["commandVector"] = ["docker", "compose", "pause", "auth"]
            intervention["commandResult"]["command"] = intervention["commandVector"]
            intervention["operational"]["commandResults"][0] = intervention["commandResult"]
        elif plant == "unpause-command-names-auth":
            vector = ["docker", "compose", "unpause", "auth"]
            intervention["recoveryAction"]["commandVector"] = vector
            intervention["recoveryAction"]["commandResult"]["command"] = vector
            intervention["operational"]["commandResults"][1] = intervention["recoveryAction"]["commandResult"]
        elif plant == "service-field-auth":
            intervention["service"] = "auth"
        elif plant == "probe-inside-window":
            record["probes"][0]["startMonotonicOffsetSeconds"] = (
                record["probePolicy"]["scoredWindowEndMonotonicOffsetSeconds"] - 1.0)
        elif plant == "event-other-container":
            record["freezeStamps"]["events"]["rows"][0]["containerId"] = IDS["auth"]
    sw._mutate(otree, root, "intervention.json", mutate)
    if plant in ("pause-command-names-auth", "unpause-command-names-auth", "service-field-auth"):
        # Which container was paused is fault truth: the cell blocks on the ground-truth check, not on the stamps.
        report = otree["validator"].validate_run(root, expected={**cell["runKey"], "runId": cell["runId"]})
        assert report["verdict"] != "pass" and "independent-fault-ground-truth" in sw._failed_gates(report)
        return
    tb._check_plant(otree, root, cell, plant, {"probe-inside-window"})


def test_a_cell_without_application_log_is_not_valid(otree, tmp_path, as_offpath):
    """The registry lane lives in application.log: a recommender-pause cell that lost it is refused."""
    cell = _cell("recommender-pause-effect", 10.0, block=1)
    root = tb._seal_b(otree, tmp_path / "run", cell)
    assert tb._verdict(otree, root, cell) == []
    (root / "application.log").unlink()
    assert tb._verdict(otree, root, cell) != []


def test_the_off_path_campaign_replays_its_own_allocation(otree, tmp_path, monkeypatch, as_offpath):
    adapter = otree["adapter"]
    monkeypatch.setattr(adapter, "_git_repository_state", sw._git_state(adapter))
    root = tmp_path / "campaign"
    materialized = otree["orchestrator"].materialize_campaign(root)
    assert len(materialized["cells"]) == 30
    for row, cell in zip(materialized["campaign"]["runs"], materialized["cells"]):
        assert row["runId"] == cell["runId"]
        tb._seal_b(otree, root / row["path"], cell)
    report = otree["validator"].validate_campaign(root)
    assert report["verdict"] == "pass", [(r["runKey"], sw._failed_gates(r)) for r in report["runReports"]]
    assert len(report["runReports"]) == 30
    campaign = json.loads((root / "campaign.json").read_text())
    campaign["runs"][0], campaign["runs"][1] = campaign["runs"][1], campaign["runs"][0]
    sw._json(root / "campaign.json", campaign)
    assert "scheduled-cell-population" in sw._failed_gates(otree["validator"].validate_campaign(root))


# ----------------------------------------------------------------------------------------- 3.7 the 3.9 floor
@pytest.mark.parametrize("relative", O_TARGET_FILES)
def test_off_path_target_files_parse_at_the_python39_floor(relative):
    tree_ = ast.parse((MODULE / relative).read_text(), feature_version=(3, 9))
    assert any(isinstance(node, ast.ImportFrom) and node.module == "__future__"
               and any(alias.name == "annotations" for alias in node.names) for node in tree_.body), relative


@pytest.mark.parametrize("relative", O_TARGET_FILES)
def test_no_name_is_loaded_that_is_bound_nowhere_in_the_files_the_off_path_epoch_touches(relative):
    assert tb._unbound_in_functions(MODULE / relative) == []


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="no system python3 (3.9 on the hosts)")
def test_the_off_path_runtime_imports_under_system_python_isolated(tmp_path):
    root = sw._copy_tree(tmp_path / "tree", OFFPATH_SELECTOR)
    script = (
        "import importlib.util, json, sys\n"
        "root = sys.argv[1]\n"
        "spec = importlib.util.spec_from_file_location('epoch', root + '/modules/teastore/execution/study_epoch.py')\n"
        "module = importlib.util.module_from_spec(spec); sys.modules['epoch'] = module; spec.loader.exec_module(module)\n"
        "for relative in sys.argv[2:]:\n"
        "    s = importlib.util.spec_from_file_location('m_' + str(abs(hash(relative))), root + '/' + relative)\n"
        "    m = importlib.util.module_from_spec(s); sys.modules[s.name] = m; s.loader.exec_module(m)\n"
        "active = module.active(__import__('pathlib').Path(root))\n"
        "print(json.dumps([active['studyEpoch'], active['runCount']]))\n"
    )
    files = ["modules/teastore/execution/candidate_runtime_adapter.py", "modules/teastore/execution/performance_campaign.py",
             "modules/teastore/validation/candidate_pilot.py", "modules/teastore/execution/candidate_offpath_ts.py"]
    result = subprocess.run(["/usr/bin/python3", "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script,
                             str(root), *files], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout.strip().splitlines()[-1]) == [OFFPATH, 30]
