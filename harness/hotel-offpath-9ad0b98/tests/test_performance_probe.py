import importlib.util
from pathlib import Path


MODULE = Path(__file__).parents[1] / "modules/teastore/collectors/performance_probe.py"
SPEC = importlib.util.spec_from_file_location("performance_probe", MODULE)
performance_probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(performance_probe)


def test_memory_units():
    assert performance_probe.bytes_value("1KiB / 2GiB") == 1024
    assert performance_probe.bytes_value("1.5MiB / 2GiB") == 1.5 * 1024**2
