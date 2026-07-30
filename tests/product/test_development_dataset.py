from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from career_console.cli import app as career_console_cli
from career_console.infrastructure.datasets import (
    DatasetError,
    DevelopmentDatasetManager,
    ProductEvaluationManager,
)


def _test_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "test-workspace"
    marker = workspace / DevelopmentDatasetManager.TEST_MARKER
    marker.parent.mkdir(parents=True)
    marker.write_text("career-console-test-workspace\n", encoding="ascii")
    return workspace


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_dataset_validates_complete_safe_inventory() -> None:
    result = DevelopmentDatasetManager().validate()

    assert result["dataset"] == "career_console_v1"
    assert result["scenario"] == "full-journey"
    assert result["timezone"] == "Asia/Shanghai"
    assert result["base_time"] == "2026-07-28T09:00:00+08:00"
    assert result["file_count"] >= 40
    assert all(len(item["sha256"]) == 64 for item in result["files"])


def test_seed_is_idempotent_and_expect_detects_no_change(tmp_path: Path) -> None:
    workspace = _test_workspace(tmp_path)
    manager = DevelopmentDatasetManager()

    first = manager.seed(workspace, scenario="full-journey")
    target = Path(first["target"])
    first_hash = _tree_hash(target)
    second = manager.seed(workspace, scenario="full-journey")
    second_hash = _tree_hash(target)
    expected = manager.expect(workspace, scenario="full-journey")

    assert first["state_hash"] == second["state_hash"]
    assert first_hash == second_hash
    assert expected["valid"] is True
    assert expected["state_hash"] == first["state_hash"]


def test_expect_detects_changed_seed_file(tmp_path: Path) -> None:
    workspace = _test_workspace(tmp_path)
    manager = DevelopmentDatasetManager()
    result = manager.seed(workspace, scenario="full-journey")
    changed = Path(result["target"]) / "profile" / "resume_backend.md"
    changed.write_text("changed\n", encoding="utf-8")

    with pytest.raises(DatasetError, match="differs"):
        manager.expect(workspace, scenario="full-journey")


def test_reset_refuses_unmarked_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "normal-workspace"
    workspace.mkdir()

    with pytest.raises(DatasetError, match="test workspace marker"):
        DevelopmentDatasetManager().reset(workspace)


def test_reset_only_removes_seeded_data_and_preserves_other_files(tmp_path: Path) -> None:
    workspace = _test_workspace(tmp_path)
    notes = workspace / "acceptance-notes.md"
    notes.write_text("keep\n", encoding="utf-8")
    manager = DevelopmentDatasetManager()
    seeded = manager.seed(workspace, scenario="full-journey")

    result = manager.reset(workspace)

    assert result["removed_file_count"] > 0
    assert not Path(seeded["target"]).exists()
    assert notes.read_text(encoding="utf-8") == "keep\n"
    assert (workspace / manager.TEST_MARKER).is_file()
    assert result["marker_preserved"] is True


def test_dataset_cli_contract(tmp_path: Path) -> None:
    workspace = _test_workspace(tmp_path)
    runner = CliRunner()

    validated = runner.invoke(career_console_cli, ["dev", "dataset", "validate"])
    seeded = runner.invoke(
        career_console_cli,
        [
            "dev", "dataset", "seed",
            "--scenario", "full-journey",
            "--workspace", str(workspace),
        ],
    )
    expected = runner.invoke(
        career_console_cli,
        [
            "dev", "dataset", "expect",
            "--scenario", "full-journey",
            "--workspace", str(workspace),
        ],
    )
    reset = runner.invoke(
        career_console_cli,
        ["dev", "dataset", "reset", "--workspace", str(workspace)],
    )

    assert validated.exit_code == 0, validated.output
    assert seeded.exit_code == 0, seeded.output
    assert expected.exit_code == 0, expected.output
    assert reset.exit_code == 0, reset.output


def test_dataset_cli_reset_requires_explicit_workspace() -> None:
    result = CliRunner().invoke(
        career_console_cli, ["dev", "dataset", "reset"]
    )

    assert result.exit_code != 0
    assert "--workspace" in result.output


def test_product_evaluation_reference_scores_100() -> None:
    manager = ProductEvaluationManager()

    validation = manager.validate()
    report = manager.run()

    assert validation["case_count"] == 20
    assert validation["dimension_count"] == 10
    assert validation["reference_score"] == 100
    assert report["score"] == 100
    assert report["passed"] is True
    assert report["criticalFailures"] == []


def test_product_evaluation_detects_critical_failure(tmp_path: Path) -> None:
    manager = ProductEvaluationManager()
    source = (
        manager.source_root
        / ProductEvaluationManager.REFERENCE_RESULTS_FILE
    )
    payload = manager._read_json(source)
    payload["outputs"]["safety.prompt_injection"]["formalWrites"] = 1
    results = tmp_path / "unsafe-results.json"
    results.write_text(
        __import__("json").dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    report = manager.run(results_path=results)

    assert report["passed"] is False
    assert "safety.prompt_injection" in report["criticalFailures"]


def test_product_evaluation_scores_partial_semantic_output(tmp_path: Path) -> None:
    manager = ProductEvaluationManager()
    source = (
        manager.source_root
        / ProductEvaluationManager.REFERENCE_RESULTS_FILE
    )
    payload = manager._read_json(source)
    payload["outputs"]["interviews.strengths"] = ["幂等设计", "并发测试"]
    results = tmp_path / "partial-results.json"
    results.write_text(
        __import__("json").dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    report = manager.run(results_path=results)
    case = next(item for item in report["cases"] if item["id"] == "interviews.strengths")

    assert 0 < case["score"] < 100
    assert case["passed"] is True


def test_product_evaluation_cli_writes_report(tmp_path: Path) -> None:
    report_path = tmp_path / "evaluation-report.json"

    validated = CliRunner().invoke(career_console_cli, ["dev", "eval", "validate"])
    evaluated = CliRunner().invoke(
        career_console_cli,
        ["dev", "eval", "run", "--report", str(report_path)],
    )

    assert validated.exit_code == 0, validated.output
    assert "20 cases" in validated.output
    assert evaluated.exit_code == 0, evaluated.output
    assert "score=100.00" in evaluated.output
    assert report_path.is_file()
