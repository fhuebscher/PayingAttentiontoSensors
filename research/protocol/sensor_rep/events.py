"""One sensor representation (protocol draft 3 §2): events `(channel, service, token, t, value, meta)`.

Channels: `log`, `span`, `metric`, `ledger`. Per-SUT code lives only in `parsers/<sut>.py`; everything downstream
(`vectors.py`, `vocab.py`, `catch.py`) sees events and streams, never a SUT file.

Token conventions (engineering defaults, recorded):
- log: the template id of `research/s4-conjunction/symptoms.template_id` (framework, level, logger/caller, masked
  message), so a token is the same string the frozen bags used; OTel uses the parameter-aware variant in
  `parsers/otel.py` (VALIDITY.md §7 defect fixed there, not in symptoms.py).
- span: `symptoms.op_token(operation)`, value = duration in seconds, one event per span; a failed span ALSO emits one
  event on the companion token `<op>:error` (value = duration), so a failure is an ordinary token that can appear,
  disappear or move.
- metric: the resource name (`cpu` = docker stats CPU percent; `sys_cpu`, `sys_memory`, `sys_io`, `sys_psi_*` = the
  cgroup sampler as derived by `research/lmt-pilot/lmt_detect.py`; OTel: OTLP metric name with `~rate`/`~mean`).
- ledger: `<route>:ok` (value = latency ms of a successful request) and `<route>:failed` (value = latency ms of a failed
  one), service = the entry service. A failed request is therefore an appear/move of `<route>:failed` (PLAN part 2).

Metadata on every event (draft 3 §2), one shared dict per stream:
  role (project map rule, `research/project-map/project_map.json`; `?` where the map has no row), channel, source
  (runtime / application / harness), level (info / warn / error / other / undefined; logs only, else None),
  resolution (sampling period in s for metrics, `per-record` otherwise), posture, onPath (service on the driven route
  per the project map's call graph; None = unknown), projected (the map's projection for (service, channel, posture);
  `?` where absent), collector (which collector produced it), clock (`wall` epoch seconds or `mono` = the harness's
  monotonic clock; windows carry bounds in both).
Level class rule: the reused parsers collapse trace/debug/info into level None, so `info` here means info-or-below
(debug and trace are not separable without re-parsing; ledger row). `fatal` maps to `other`; a record with no level
field (JVM throwable header) is `undefined`.
"""
import bisect
import json
import statistics
from collections import namedtuple
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CHANNELS = ("log", "span", "metric", "ledger")
LEVEL_CLASSES = ("info", "warn", "error", "other", "undefined")
SOURCES = ("runtime", "application", "harness")
PROJECT_MAP = REPO / "research" / "project-map" / "project_map.json"

Event = namedtuple("Event", "channel service token t value meta")

_META = {}


def meta(**kw):
    """Interned metadata dict (one object per distinct stream metadata)."""
    key = tuple(sorted(kw.items()))
    m = _META.get(key)
    if m is None:
        m = _META[key] = dict(kw)
    return m


def level_class(framework, level):
    if level in ("warn", "error"):
        return level
    if level == "fatal":
        return "other"
    if framework == "jvm-throwable":
        return "undefined"
    return "info"


def sensor_id(channel, service, token):
    return "%s:%s:%s" % (channel, service, token)


class ProjectMap:
    """Read-only lookup into the project map (draft 3 §1b). Missing file or row -> `?` (unknown is not zero)."""

    def __init__(self, path=PROJECT_MAP):
        self.ok = Path(path).exists()
        self.cells, self.roles, self.on_route = {}, {}, {}
        if not self.ok:
            return
        d = json.loads(Path(path).read_text())
        for sut, v in d.get("suts", {}).items():
            self.roles[sut] = {s: r.get("role", "?") for s, r in (v.get("roles") or {}).items()}
            self.on_route[sut] = set((v.get("callGraph") or {}).get("onRoute") or [])
            for c in v.get("cells") or []:
                self.cells[(sut, c["service"], c["channel"], c["posture"])] = c

    def role(self, sut, service):
        return self.roles.get(sut, {}).get(service, "?")

    def on_path(self, sut, service):
        r = self.on_route.get(sut)
        return None if not r else service in r

    def projected(self, sut, service, channel, posture):
        c = self.cells.get((sut, service, channel, posture))
        return "?" if c is None else c.get("projection", "?")

    @staticmethod
    def map_channel(channel, source, level):
        if channel == "metric":
            return "metric:runtime" if source == "runtime" else "metric:app"
        if channel == "log":
            return "log:" + (level or "undefined")
        return "trace" if channel == "span" else "ledger"


PMAP = None


def project_map():
    global PMAP
    if PMAP is None:
        PMAP = ProjectMap()
    return PMAP


def stream_meta(sut, posture, channel, service, source, collector, clock, resolution, level=None):
    pm = project_map()
    return meta(role=pm.role(sut, service), channel=channel, source=source, level=level, resolution=resolution,
                posture=posture, onPath=pm.on_path(sut, service),
                projected=pm.projected(sut, service, ProjectMap.map_channel(channel, source, level), posture),
                collector=collector, clock=clock)


class Stream:
    """All events of one (channel, service, token) in one cell, sorted by time."""
    __slots__ = ("channel", "service", "token", "t", "v", "meta")

    def __init__(self, channel, service, token, meta_):
        self.channel, self.service, self.token, self.meta = channel, service, token, meta_
        self.t, self.v = [], []

    def finish(self):
        if any(b < a for a, b in zip(self.t, self.t[1:])):
            order = sorted(range(len(self.t)), key=lambda i: self.t[i])
            self.t = [self.t[i] for i in order]
            self.v = [self.v[i] for i in order]

    def select(self, lo, hi, lo_open=False, hi_open=False):
        """Values with lo <= t <= hi (edges open as flagged); lo None = unbounded below. Untimed events never match."""
        a = 0 if lo is None else (bisect.bisect_right(self.t, lo) if lo_open else bisect.bisect_left(self.t, lo))
        b = bisect.bisect_left(self.t, hi) if hi_open else bisect.bisect_right(self.t, hi)
        return self.v[a:b] if b > a else []


def group(events):
    """Events -> {(channel, service, token): Stream}. Events with t None are dropped from streams (they can never fall
    in a window; counted in the parser stats instead)."""
    out = {}
    for e in events:
        if e.t is None:
            continue
        k = (e.channel, e.service, e.token)
        s = out.get(k)
        if s is None:
            s = out[k] = Stream(e.channel, e.service, e.token, e.meta)
        s.t.append(e.t)
        s.v.append(e.value)
    for s in out.values():
        s.finish()
    return out


def robust(values):
    """(median, raw MAD) of a non-empty list; the scaled spread is 1.4826 * MAD (symptoms.robust_threshold)."""
    m = statistics.median(values)
    return m, statistics.median(abs(v - m) for v in values)
