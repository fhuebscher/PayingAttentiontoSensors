import json
from pathlib import Path

import pytest

from obsplacement.selection import compile_selection, render_aop


CATALOG = json.loads((Path(__file__).parents[1] / "modules/teastore/activation/catalog.json").read_text())


def test_compiler_closes_over_mandatory_propagation():
    result = compile_selection(CATALOG, ["operation:auth"])
    assert result["selectedActivationGroups"] == ["aspectj:auth", "manual:registry-client"]
    assert result["mandatoryActivationGroups"] == ["manual:registry-client"]
    assert result["independentlyControllable"] is False
    assert "operation:auth" in result["expectedLogicalSensors"]
    assert "propagation:registry-client" in result["expectedLogicalSensors"]
    rendered = render_aop(result)
    assert 'include within="tools.descartes.teastore.auth..*"' in rendered
    assert "execution(* tools.descartes.teastore.auth..*(..))" in rendered
    assert "..*.*(..)" not in rendered


def test_compiler_rejects_unknown_sensor():
    with pytest.raises(ValueError, match="unknown logical sensors"):
        compile_selection(CATALOG, ["operation:not-real"])


def test_fault_goal_generates_declared_qualification_selection():
    goal = json.loads((Path(__file__).parents[1] / "modules/teastore/goals/fault-qualification.json").read_text())
    result = compile_selection(CATALOG, goal["logicalSensors"])
    assert result["requestedLogicalSensors"] == ["operation:auth", "operation:persistence"]
    assert result["selectedActivationGroups"] == ["aspectj:auth", "aspectj:persistence", "manual:registry-client"]
