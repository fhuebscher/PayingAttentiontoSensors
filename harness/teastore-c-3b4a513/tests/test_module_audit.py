from pathlib import Path

from obsplacement.module_audit import audit


def test_detects_unclassified_file(tmp_path: Path):
    (tmp_path / "extension-ledger.yaml").write_text("extensions: []\n")
    (tmp_path / "surprise.py").write_text("pass\n")
    assert audit(tmp_path)["unclassified_files"] == ["surprise.py"]


def test_counts_classified_lines(tmp_path: Path):
    (tmp_path / "extension-ledger.yaml").write_text(
        "extensions:\n  - path: collector.py\n    class: collector\n"
    )
    (tmp_path / "collector.py").write_text("one\ntwo\n")
    report = audit(tmp_path)
    assert report["verdict"] == "pass"
    assert report["lines_by_class"] == {"collector": 2}
