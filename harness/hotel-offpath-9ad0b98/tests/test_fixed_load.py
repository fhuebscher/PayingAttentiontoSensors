import importlib.util
from pathlib import Path


MODULE = Path(__file__).parents[1] / "modules/teastore/workload/fixed_load.py"
SPEC = importlib.util.spec_from_file_location("fixed_load", MODULE)
fixed_load = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(fixed_load)


def test_percentile_interpolates_and_handles_empty():
    assert fixed_load.percentile([], 0.95) == 0
    assert fixed_load.percentile([1, 2, 3], 0.5) == 2
    assert fixed_load.percentile([0, 10], 0.95) == 9.5
