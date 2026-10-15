"""LMT+S pilot: the degradation fault adapter and the always-on system collector.

No Docker, no sudo: every command the adapters would run is answered by an
in-process fake that keeps the container state the real commands would change,
so a receipt is only "manifested" when the fake container really is degraded.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/hotel-reservation"


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, MODULE / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


lmt = load("hotel_lmt_pilot_faults_test", "faults/lmt_faults.py")
system = load("hotel_lmt_pilot_system_test", "collectors/system_state.py")
witness = load("hotel_lmt_pilot_witness_test", "witness/candidate_evidence.py")

CID = "c" * 64
PID = 4242
BARRIER = 1000.0
NOQUEUE = "qdisc noqueue 0: root refcnt 2\n"


HOST_NCPU = 12


class FakeHost:
    """The target container as `docker`, `docker compose` and `nsenter tc` see it."""

    def __init__(self, clock: list, *, apply_takes_effect: bool = True,
                 revert_return_code: int = 0):
        self.clock = clock
        self.nanocpus = 0
        self.qdisc = NOQUEUE
        self.apply_takes_effect = apply_takes_effect
        self.revert_return_code = revert_return_code
        self.calls: list = []

    def command(self, argv, check=True, env=None):
        self.calls.append(list(argv))
        self.clock[0] += 0.05  # every command takes a little wall time
        ok = subprocess.CompletedProcess(argv, 0, "", "")
        if argv[:2] == ["docker", "compose"] and argv[-3:-1] == ["ps", "-q"]:
            return subprocess.CompletedProcess(argv, 0, CID + "\n", "")
        if argv == ["docker", "inspect", "--format", "{{.State.Pid}}", CID]:
            return subprocess.CompletedProcess(argv, 0, f"{PID}\n", "")
        if argv == ["docker", "inspect", CID]:
            return subprocess.CompletedProcess(
                argv, 0, json.dumps([{"HostConfig": {"NanoCpus": self.nanocpus}}]), "")
        if argv == ["docker", "info", "--format", "{{.NCPU}}"]:
            return subprocess.CompletedProcess(argv, 0, f"{HOST_NCPU}\n", "")
        if argv[:3] == ["docker", "update", "--cpus"] and argv[4] == CID:
            # As the daemon does (fb14srv4 2026-09-28): a zero NanoCPUs is skipped, not applied,
            # and more CPUs than the host has is refused.
            wanted = int(float(argv[3]) * 1e9)
            if wanted > HOST_NCPU * 10**9:
                return subprocess.CompletedProcess(argv, 1, "", "Range of CPUs is from 0.01 to 12.00")
            if wanted == HOST_NCPU * 10**9:
                if self.revert_return_code:
                    return subprocess.CompletedProcess(argv, self.revert_return_code, "", "denied")
                self.nanocpus = wanted
            elif wanted and self.apply_takes_effect:
                self.nanocpus = wanted
            return ok
        tc = ["sudo", "-n", "nsenter", "-t", str(PID), "-n", "tc", "qdisc"]
        if argv[:len(tc)] == tc:
            rest = argv[len(tc):]
            if rest == ["show", "dev", "eth0"]:
                return subprocess.CompletedProcess(argv, 0, self.qdisc, "")
            if rest[:4] == ["add", "dev", "eth0", "root"]:
                if self.apply_takes_effect:
                    self.qdisc = "qdisc netem 8001: root refcnt 2 limit 1000 delay " + rest[-1] + "\n"
                return ok
            if rest == ["del", "dev", "eth0", "root"]:
                if self.revert_return_code:
                    return subprocess.CompletedProcess(argv, self.revert_return_code, "", "denied")
                self.qdisc = NOQUEUE
                return ok
        raise AssertionError(f"unexpected command: {argv}")


class FakeCancel:
    """The cell's `fault_cancel` event, never set; waiting advances the fake clock."""

    def __init__(self, clock: list, overshoot: float = 0.0):
        self.clock, self.overshoot = clock, overshoot

    def wait(self, seconds):
        self.clock[0] += seconds + self.overshoot
        return False

    def is_set(self):
        return False


def inject(monkeypatch, tmp_path: Path, scenario: str, **host_options) -> tuple[dict, FakeHost]:
    overshoot = host_options.pop("overshoot", 0.0)
    clock = [BARRIER + 40.0]
    host = FakeHost(clock, **host_options)
    monkeypatch.setattr(lmt.pause, "command", host.command)
    monkeypatch.setattr(lmt.pause, "route_available", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(lmt.pause, "wait_recovered", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(lmt.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(lmt.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    receipt = lmt.inject(
        tmp_path, "hotel_candidate_v4_deadbeef_01", scenario, 45, 15,
        "http://127.0.0.1:35005/hotels", tmp_path / "fault-receipt.json",
        FakeCancel(clock, overshoot), env={"PATH": "/usr/bin"},
        scheduled_at_seconds=45, start_at_monotonic=BARRIER + 45,
    )
    assert json.loads((tmp_path / "fault-receipt.json").read_text()) == receipt
    return receipt, host


# --------------------------------------------------------------------------
# (a) degradation receipts: the adapter's happy path is what the witness admits.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("scenario", "apply_command", "revert_command"),
    [
        ("profile-cpu-throttle", ["docker", "update", "--cpus", "0.1", CID],
         ["docker", "update", "--cpus", str(HOST_NCPU), CID]),
        ("rate-net-delay",
         ["sudo", "-n", "nsenter", "-t", str(PID), "-n", "tc", "qdisc", "add", "dev", "eth0",
          "root", "netem", "delay", "100ms"],
         ["sudo", "-n", "nsenter", "-t", str(PID), "-n", "tc", "qdisc", "del", "dev", "eth0", "root"]),
    ],
)
def test_degradation_happy_path_receipt_is_admitted_by_the_witness(
    monkeypatch, tmp_path: Path, scenario: str, apply_command: list, revert_command: list,
):
    receipt, host = inject(monkeypatch, tmp_path, scenario)
    assert receipt["faultKind"] == "degradation"
    assert receipt["targetService"] == {"profile-cpu-throttle": "profile", "rate-net-delay": "rate"}[scenario]
    assert receipt["successful"] is True
    assert receipt["manifested"] is True and receipt["reverted"] is True
    assert receipt["preClean"] is True and receipt["routeAvailableDuring"] is True
    assert [row["action"] for row in receipt["commands"]] == ["apply", "revert"]
    assert apply_command in host.calls and revert_command in host.calls
    # The container ends clean: the degradation was reverted, not left behind.
    assert host.nanocpus in (0, HOST_NCPU * 10**9) and host.qdisc == NOQUEUE
    # Onset waits for the absolute plan offset; the hold is measured inside the fault.
    # (the precondition probes take the fake clock slightly past the 45 s onset).
    assert 45.0 <= receipt["startedMonotonic"] - BARRIER < 45.5
    assert receipt["startedMonotonic"] < receipt["appliedMonotonic"] < receipt["revertingMonotonic"]
    assert receipt["actualHoldSeconds"] == pytest.approx(15.0)
    validated = witness.validate_fault_receipt(receipt, scenario, barrier_monotonic=BARRIER)
    assert validated["state"] == "supported"
    assert validated["faultKind"] == "degradation"
    assert validated["detectionWindowMonotonic"] == [
        receipt["appliedMonotonic"], receipt["revertingMonotonic"],
    ]
    assert validated["phaseBoundaries"]["faultUnpausedMonotonic"] == receipt["revertedAtMonotonic"]
    # A degradation receipt is not a pause receipt.
    with pytest.raises(witness.WitnessError, match="fields differ"):
        witness.validate_fault_receipt(receipt, "search-pause")


def test_degradation_that_never_manifests_is_rejected(monkeypatch, tmp_path: Path):
    # The apply command returns 0 but the container never changes: command
    # success alone must not establish fault truth.
    receipt, _host = inject(monkeypatch, tmp_path, "profile-cpu-throttle", apply_takes_effect=False)
    assert receipt["manifested"] is False
    assert receipt["successful"] is False
    with pytest.raises(witness.WitnessError):
        witness.validate_fault_receipt(receipt, "profile-cpu-throttle", barrier_monotonic=BARRIER)


@pytest.mark.parametrize("scenario", ["profile-cpu-throttle", "rate-net-delay"])
def test_degradation_whose_revert_command_fails_is_rejected(monkeypatch, tmp_path: Path, scenario):
    receipt, _host = inject(monkeypatch, tmp_path, scenario, revert_return_code=1)
    assert receipt["reverted"] is False
    assert receipt["successful"] is False
    # The adapter retries the revert and retains that attempt as evidence.
    assert [row["action"] for row in receipt["commands"]] == ["apply", "revert", "revert-finally"]
    with pytest.raises(witness.WitnessError):
        witness.validate_fault_receipt(receipt, scenario, barrier_monotonic=BARRIER)


def test_degradation_held_18_seconds_is_rejected_although_the_adapter_calls_it_successful(
    monkeypatch, tmp_path: Path,
):
    # The adapter only knows "at least 15 s"; D21 bounds the hold from above.
    receipt, _host = inject(monkeypatch, tmp_path, "profile-cpu-throttle", overshoot=3.0)
    assert receipt["actualHoldSeconds"] == pytest.approx(18.0)
    assert receipt["successful"] is True
    with pytest.raises(witness.WitnessError, match="monotonic truth"):
        witness.validate_fault_receipt(receipt, "profile-cpu-throttle", barrier_monotonic=BARRIER)


def _revert_failed(receipt: dict) -> dict:
    planted = copy.deepcopy(receipt)
    planted["commands"][1]["returnCode"] = 1
    return planted


def _plant(**fields):
    def planted(receipt: dict) -> dict:
        result = copy.deepcopy(receipt)
        result.update({
            key: value(receipt) if callable(value) else value for key, value in fields.items()
        })
        return result
    return planted


@pytest.mark.parametrize(
    ("label", "plant"),
    [
        ("manifested False", _plant(manifested=False)),
        ("revert command non-zero", _revert_failed),
        ("reverted False", _plant(reverted=False)),
        # Every later edge moves with the hold, so only its length is wrong.
        ("hold 18 s", _plant(
            actualHoldSeconds=18.0,
            revertingMonotonic=lambda r: r["appliedMonotonic"] + 18.0,
            revertedAtMonotonic=lambda r: r["appliedMonotonic"] + 18.05,
            readyAtMonotonic=lambda r: r["appliedMonotonic"] + 18.1,
            endedMonotonic=lambda r: r["appliedMonotonic"] + 18.1,
        )),
        ("appliedMonotonic after revertingMonotonic",
         _plant(appliedMonotonic=lambda r: r["revertingMonotonic"] + 0.01)),
        ("not pre-clean", _plant(preClean=False)),
        ("requested hold 10 s", _plant(requestedHoldSeconds=10)),
        ("wrong target", _plant(targetService="profile")),
        ("pause kind", _plant(faultKind="pause")),
    ],
)
def test_planted_degradation_receipt_defects_are_rejected(
    monkeypatch, tmp_path: Path, label: str, plant,
):
    receipt, _host = inject(monkeypatch, tmp_path, "rate-net-delay")
    witness.validate_fault_receipt(receipt, "rate-net-delay", barrier_monotonic=BARRIER)
    with pytest.raises(witness.WitnessError):
        witness.validate_fault_receipt(plant(receipt), "rate-net-delay", barrier_monotonic=BARRIER)


def test_pause_scenarios_pass_through_to_the_compose_pause_adapter(monkeypatch, tmp_path: Path):
    seen = []

    def fake_pause(*args, **kwargs):
        seen.append((args, kwargs))
        return {"faultKind": "pause"}

    monkeypatch.setattr(lmt.pause, "inject", fake_pause)
    assert lmt.inject(
        tmp_path, "project", "search-pause", 45, 15, "http://host/hotels",
        tmp_path / "receipt.json", None, {"A": "1"},
        scheduled_at_seconds=45, start_at_monotonic=1045.0,
    ) == {"faultKind": "pause"}
    assert seen[0][0][2] == "search-pause"
    assert seen[0][1] == {"scheduled_at_seconds": 45, "start_at_monotonic": 1045.0, "record_probes": False}
    with pytest.raises(ValueError, match="scenario"):
        lmt.inject(tmp_path, "project", "geo-crash", 45, 15, "http://host/hotels",
                   tmp_path / "other.json", start_at_monotonic=1045.0)
    with pytest.raises(ValueError, match="monotonic start"):
        lmt.inject(tmp_path, "project", "rate-net-delay", 45, 15, "http://host/hotels",
                   tmp_path / "other.json")


# --------------------------------------------------------------------------
# (b) cgroup cost edges: a window is a non-negative delta over one container set.
# --------------------------------------------------------------------------


def _edge(label: str, monotonic: float, containers: dict, daemons: dict) -> dict:
    return {"label": label, "at": "2026-09-28T20:00:00Z", "monotonic": monotonic,
            "containersUsageUsec": containers, "daemonsUsageUsec": daemons}


def _edges() -> tuple[dict, dict]:
    daemons = {"docker.service": 10_000_000, "containerd.service": 20_000_000}
    start = _edge("window-start", 1000.0, {"search": 1_000_000, "rate": 2_000_000}, daemons)
    end = _edge(
        "window-end", 1120.0, {"search": 3_500_000, "rate": 2_250_000},
        {"docker.service": 10_400_000, "containerd.service": 20_100_000},
    )
    return start, end


def test_cost_document_is_the_per_window_cpu_delta():
    start, end = _edges()
    document = system.cost_document(start, end)
    assert document["kind"] == "hotel-lmt-cost-cgroup-v1"
    assert document["windowSeconds"] == 120.0
    assert document["containersCpuSeconds"] == {"rate": 0.25, "search": 2.5}
    assert document["daemonsCpuSeconds"] == {"containerd.service": 0.1, "docker.service": 0.4}
    assert document["start"] == start and document["end"] == end


@pytest.mark.parametrize("side", ["containersUsageUsec", "daemonsUsageUsec"])
def test_cost_document_rejects_a_decreasing_counter(side: str):
    start, end = _edges()
    key = sorted(end[side])[0]
    end[side][key] = start[side][key] - 1
    with pytest.raises(system.SystemError_, match="decreased"):
        system.cost_document(start, end)


@pytest.mark.parametrize(
    "end_containers",
    [
        {"search": 3_500_000},                                   # one container vanished
        {"search": 3_500_000, "rate": 2_250_000, "geo": 1},      # one appeared
        {"search": 3_500_000, "profile": 2_250_000},             # same size, other set
    ],
)
def test_cost_document_rejects_different_container_sets(end_containers: dict):
    start, end = _edges()
    end["containersUsageUsec"] = end_containers
    with pytest.raises(system.SystemError_, match="different containers"):
        system.cost_document(start, end)


def test_cost_edges_read_container_and_daemon_cgroups_and_refuse_a_missing_one(
    monkeypatch, tmp_path: Path,
):
    slice_ = tmp_path / "system.slice"
    for name, usage in ((f"docker-{CID}.scope", 7), ("docker.service", 11), ("containerd.service", 13)):
        (slice_ / name).mkdir(parents=True)
        (slice_ / name / "cpu.stat").write_text(f"usage_usec {usage}\nuser_usec 1\nsystem_usec 2\n")
    monkeypatch.setattr(system, "CGROUP", tmp_path)
    edge = system.cost_edges({CID: "search"}, "window-start")
    assert edge["label"] == "window-start"
    assert edge["containersUsageUsec"] == {"search": 7}
    assert edge["daemonsUsageUsec"] == {"docker.service": 11, "containerd.service": 13}
    with pytest.raises(system.SystemError_, match="cgroup is missing"):
        system.cost_edges({"d" * 64: "rate"}, "window-end")


def test_throttle_revert_to_zero_cpus_is_not_a_revert(monkeypatch, tmp_path: Path):
    """Planted defect (the 2026-09-28 host smoke): `--cpus 0` leaves the quota in place."""
    monkeypatch.setattr(lmt, "_revert", lambda scenario, cid: ["docker", "update", "--cpus", "0", cid])
    receipt, host = inject(monkeypatch, tmp_path, "profile-cpu-throttle")
    assert host.nanocpus == 100_000_000
    assert receipt["reverted"] is False and receipt["successful"] is False
