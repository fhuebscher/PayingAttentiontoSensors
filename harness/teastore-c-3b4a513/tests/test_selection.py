import json
import re
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


ALL_SENSORS = [row["id"] for row in CATALOG["logicalSensors"]]
STOCK_AOP = (Path(__file__).parents[1]
             / "upstream/teastore/utilities/tools.descartes.teastore.dockerbase/aop.xml")


def test_render_carries_group_exclusions_and_guards():
    rendered = render_aop(compile_selection(CATALOG, ["operation:persistence"]))
    assert '<exclude within="tools.descartes.teastore.persistence.repository..*" />' in rendered
    assert "!within(tools.descartes.teastore.persistence.repository..*)" in rendered
    assert ("!execution(* tools.descartes.teastore.persistence.domain."
            "PersistenceUser.getEmail(..))") in rendered
    assert "!within(is(AnonymousType))" in rendered
    assert "&amp;&amp; !execution(private * *..lambda*(..))" in rendered
    # F-ADH-071: the framework witness stays unwoven in every rendering.
    assert '<exclude within="tools.descartes.teastore.registryclient.observability..*" />' in rendered
    # && binds tighter than ||, so the alternatives must be parenthesised.
    assert 'expression="(execution(' in rendered


def test_full_selection_is_superset_of_selected_join_point_set():
    """F-ADH-072: the lattice must nest at the join point, not just the label."""
    goal = json.loads((Path(__file__).parents[1]
                       / "modules/teastore/goals/fault-qualification.json").read_text())
    selected = compile_selection(CATALOG, goal["logicalSensors"])
    full = compile_selection(CATALOG, ALL_SENSORS)
    for key in ("aspectjPatterns", "excludeTypes", "excludeExecutions"):
        assert set(selected[key]) <= set(full[key]), key
    assert set(selected["selectedActivationGroups"]) < set(full["selectedActivationGroups"])
    # No exclusion may apply to full inside selected's own scope without also
    # applying to selected -- that asymmetry is exactly what campaign #6 had.
    scope = ("tools.descartes.teastore.auth.", "tools.descartes.teastore.persistence.")
    for key in ("excludeTypes", "excludeExecutions"):
        asymmetric = [value for value in set(full[key]) - set(selected[key])
                      if value.startswith(scope)]
        assert asymmetric == [], (key, asymmetric)


def test_empty_selection_weaves_nothing():
    compiled = compile_selection(CATALOG, [])
    assert compiled["selectedActivationGroups"] == []
    rendered = render_aop(compiled)
    assert '<exclude within="*..*" />' in rendered
    assert "if(false)" in rendered
    assert "<include" not in rendered


def test_stock_exclusions_are_carried_verbatim():
    """Every stock exclusion reachable from a group's include is in the catalog."""
    if not STOCK_AOP.exists():
        pytest.skip("upstream/teastore submodule is not initialised")
    stock = STOCK_AOP.read_text()
    full = compile_selection(CATALOG, ALL_SENSORS)
    prefixes = tuple(row["aspectjPatterns"][0][:-2] for row in CATALOG["activationGroups"]
                     if row.get("aspectjPatterns"))
    for symbol in re.findall(r'<exclude within="([^"]+)"', stock):
        if symbol.startswith(prefixes):
            assert symbol in full["excludeTypes"], symbol
    for symbol in re.findall(r"!execution\(\* ([\w.$]+)\(\.\.\)\)", stock):
        if symbol.startswith(prefixes):
            assert symbol in full["excludeExecutions"], symbol
