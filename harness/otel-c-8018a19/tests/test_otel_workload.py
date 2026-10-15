import importlib.util
from pathlib import Path

MODULE = Path(__file__).parents[1] / "modules/otel-demo/workload.py"
SPEC = importlib.util.spec_from_file_location("otel_workload", MODULE)
workload = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workload)


def test_percentile_uses_nearest_rank():
    assert workload.percentile([1, 2, 3, 4], .5) == 2
    assert workload.percentile([1, 2, 3, 4], .95) == 4
    assert workload.percentile([], .95) is None
