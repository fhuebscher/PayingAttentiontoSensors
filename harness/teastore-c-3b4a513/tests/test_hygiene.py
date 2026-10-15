from obsplacement.execution.hygiene import classify, json_lines


def row(name, project, state="running"):
    return {"ID": name, "Names": name, "State": state, "Labels": f"com.docker.compose.project={project}"}


def test_json_lines_ignores_non_json_banner():
    assert json_lines("banner\n{\"ID\": \"a\"}\n") == [{"ID": "a"}]


def test_classification_blocks_foreign_running_container():
    rows, blockers = classify([row("otel", "opentelemetry-demo"), row("x", "someone-else")], {"opentelemetry-demo"}, "obsplacement-teastore")
    assert [r["ownership"] for r in rows] == ["owned-legacy", "foreign"]
    assert blockers == ["running foreign container x"]
