import importlib.util
from pathlib import Path


MODULE = Path(__file__).parents[1] / "modules/teastore/validation/native_kieker.py"
SPEC = importlib.util.spec_from_file_location("native_kieker", MODULE)
native_kieker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(native_kieker)


def event(**overrides):
    value = {
        "source": "kieker_native", "service": "webui", "trace_id": "42",
        "eoi": 0, "ess": 0, "message_sha1": "m", "signature_sha1": "s",
    }
    value.update(overrides)
    return value


def test_accepts_native_multiservice_events():
    report = native_kieker.validate([event(), event(service="auth", eoi=1, ess=1)])
    assert report["verdict"] == "pass"


def test_rejects_scraper_ids_and_single_service():
    report = native_kieker.validate([event(trace_id="scraped_deadbeef")])
    assert report["verdict"] == "blocked"
    assert any("scraper-generated" in item for item in report["blockers"])
