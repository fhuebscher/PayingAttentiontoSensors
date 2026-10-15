"""Compile logical sensor selections into realizable activation groups."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compile_selection(catalog: dict, requested: list[str]) -> dict:
    sensors = {item["id"]: item for item in catalog["logicalSensors"]}
    groups = {item["id"]: item for item in catalog["activationGroups"]}
    unknown = sorted(set(requested) - set(sensors))
    if unknown:
        raise ValueError(f"unknown logical sensors: {unknown}")

    selected_groups = {sensors[item]["activationGroup"] for item in requested}
    frontier = list(selected_groups)
    while frontier:
        group_id = frontier.pop()
        if group_id not in groups:
            raise ValueError(f"undefined activation group: {group_id}")
        for required in groups[group_id].get("requires", []):
            if required not in selected_groups:
                selected_groups.add(required)
                frontier.append(required)

    patterns = sorted({
        pattern
        for group_id in selected_groups
        for pattern in groups[group_id].get("aspectjPatterns", [])
    })
    emitted = sorted(
        sensor_id for sensor_id, sensor in sensors.items()
        if sensor["activationGroup"] in selected_groups
    )
    return {
        "schemaVersion": 1,
        "catalog": catalog["id"],
        "requestedLogicalSensors": sorted(set(requested)),
        "selectedActivationGroups": sorted(selected_groups),
        "mandatoryActivationGroups": sorted(selected_groups - {
            sensors[item]["activationGroup"] for item in requested
        }),
        "expectedLogicalSensors": emitted,
        "aspectjPatterns": patterns,
        "independentlyControllable": emitted == sorted(set(requested)),
    }


def render_aop(compiled: dict) -> str:
    includes = "\n".join(
        f'    <include within="{pattern}" />' for pattern in compiled["aspectjPatterns"]
    )
    pointcut = " || ".join(
        f"execution(* {pattern}(..))" for pattern in compiled["aspectjPatterns"]
    ) or "if(false)"
    return f'''<!DOCTYPE aspectj PUBLIC "-//AspectJ//DTD//EN" "http://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
  <weaver options="-Xlint:ignore -Xset:weaveJavaxPackages=true">
{includes}
  </weaver>
  <aspects>
    <concrete-aspect name="kieker.monitoring.probe.aspectj.operationExecution.CompiledAspect"
      extends="tools.descartes.teastore.kieker.probes.AbstractOperationExecutionWithParameterAspect">
      <pointcut name="monitoredOperation"
        expression="{pointcut.replace('&', '&amp;')}" />
    </concrete-aspect>
  </aspects>
</aspectj>
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("selection", type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--aop", required=True, type=Path)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    requested = json.loads(args.selection.read_text())["logicalSensors"]
    compiled = compile_selection(catalog, requested)
    args.manifest.write_text(json.dumps(compiled, indent=2, sort_keys=True) + "\n")
    args.aop.write_text(render_aop(compiled))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
