"""Deterministic CareerConsole benchmark validation and scoring."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .manager import DatasetError, DevelopmentDatasetManager


@dataclass(frozen=True, slots=True)
class EvaluationCaseResult:
    case_id: str
    dimension: str
    score: float
    threshold: float
    passed: bool
    critical: bool
    detail: str


class ProductEvaluationManager:
    """Score normalized product outputs against a versioned benchmark."""

    SCHEMA_VERSION = "career-console.evaluation.v1"
    RESULT_SCHEMA_VERSION = "career-console.evaluation-results.v1"
    BENCHMARK_FILE = Path("evaluation") / "benchmark.json"
    REFERENCE_RESULTS_FILE = Path("evaluation") / "reference-results.json"

    def __init__(self, dataset: DevelopmentDatasetManager | None = None) -> None:
        self.dataset = dataset or DevelopmentDatasetManager()
        self.source_root = self.dataset.source_root

    def validate(self) -> dict[str, Any]:
        dataset = self.dataset.validate()
        benchmark = self._read_json(self.source_root / self.BENCHMARK_FILE)
        reference = self._read_json(self.source_root / self.REFERENCE_RESULTS_FILE)
        self._validate_benchmark(benchmark)
        self._validate_results(reference, benchmark)
        report = self.run(results_path=self.source_root / self.REFERENCE_RESULTS_FILE)
        if not report["passed"] or report["score"] != 100.0:
            raise DatasetError("Reference evaluation results must score exactly 100.")
        return {
            "dataset": dataset["dataset"],
            "benchmark": benchmark["benchmark"],
            "case_count": len(benchmark["cases"]),
            "dimension_count": len(benchmark["dimensions"]),
            "reference_score": report["score"],
            "valid": True,
        }

    def run(self, *, results_path: Path | None = None) -> dict[str, Any]:
        benchmark = self._read_json(self.source_root / self.BENCHMARK_FILE)
        self._validate_benchmark(benchmark)
        path = results_path or self.source_root / self.REFERENCE_RESULTS_FILE
        results = self._read_json(path)
        self._validate_results(results, benchmark)
        outputs = results["outputs"]
        case_results = [
            self._score_case(case, outputs.get(case["id"]))
            for case in benchmark["cases"]
        ]
        dimensions = []
        for dimension in benchmark["dimensions"]:
            cases = [item for item in case_results if item.dimension == dimension["id"]]
            definitions = [
                case for case in benchmark["cases"]
                if case["dimension"] == dimension["id"]
            ]
            total_weight = sum(float(case["weight"]) for case in definitions)
            weighted_score = sum(
                item.score * float(definition["weight"])
                for item in cases
                for definition in definitions
                if definition["id"] == item.case_id
            )
            score = weighted_score / total_weight if total_weight else 0.0
            dimensions.append({
                "id": dimension["id"],
                "name": dimension["name"],
                "weight": dimension["weight"],
                "score": round(score, 2),
                "passed": all(item.passed for item in cases),
                "case_count": len(cases),
            })
        overall = sum(
            item["score"] * float(item["weight"]) / 100 for item in dimensions
        )
        critical_failures = [
            item.case_id for item in case_results if item.critical and not item.passed
        ]
        minimum = float(benchmark["passCriteria"]["minimumOverallScore"])
        return {
            "schemaVersion": "career-console.evaluation-report.v1",
            "benchmark": benchmark["benchmark"],
            "dataset": benchmark["dataset"],
            "evaluatedAt": datetime.now(UTC).isoformat(),
            "resultsFile": str(path.resolve(strict=False)),
            "score": round(overall, 2),
            "minimumScore": minimum,
            "passed": overall >= minimum and not critical_failures,
            "criticalFailures": critical_failures,
            "dimensions": dimensions,
            "cases": [
                {
                    "id": item.case_id,
                    "dimension": item.dimension,
                    "score": round(item.score, 2),
                    "threshold": item.threshold,
                    "passed": item.passed,
                    "critical": item.critical,
                    "detail": item.detail,
                }
                for item in case_results
            ],
        }

    def write_report(self, report: dict[str, Any], destination: Path) -> Path:
        destination = destination.expanduser().resolve(strict=False)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return destination

    def _validate_benchmark(self, benchmark: dict[str, Any]) -> None:
        if benchmark.get("schemaVersion") != self.SCHEMA_VERSION:
            raise DatasetError("Evaluation benchmark schema version is unsupported.")
        if benchmark.get("dataset") != self.dataset.DATASET_NAME:
            raise DatasetError("Evaluation benchmark dataset does not match.")
        dimensions = benchmark.get("dimensions")
        cases = benchmark.get("cases")
        if not isinstance(dimensions, list) or not dimensions:
            raise DatasetError("Evaluation benchmark requires dimensions.")
        if not isinstance(cases, list) or not cases:
            raise DatasetError("Evaluation benchmark requires cases.")
        dimension_ids = [str(item.get("id", "")) for item in dimensions]
        if (
            len(dimension_ids) != len(set(dimension_ids))
            or any(not item for item in dimension_ids)
        ):
            raise DatasetError("Evaluation dimension IDs must be unique and non-empty.")
        if round(sum(float(item.get("weight", 0)) for item in dimensions), 6) != 100:
            raise DatasetError("Evaluation dimension weights must total 100.")
        case_ids = [str(item.get("id", "")) for item in cases]
        if len(case_ids) != len(set(case_ids)) or any(not item for item in case_ids):
            raise DatasetError("Evaluation case IDs must be unique and non-empty.")
        allowed_evaluators = {"exact", "subset", "set_f1", "range"}
        for case in cases:
            if case.get("dimension") not in dimension_ids:
                raise DatasetError(f"Unknown evaluation dimension: {case.get('dimension')}")
            if case.get("evaluator") not in allowed_evaluators:
                raise DatasetError(f"Unsupported evaluator: {case.get('evaluator')}")
            if not 0 <= float(case.get("threshold", -1)) <= 100:
                raise DatasetError(f"Invalid threshold for case: {case.get('id')}")
            if float(case.get("weight", 0)) <= 0:
                raise DatasetError(f"Invalid weight for case: {case.get('id')}")
            input_files = case.get("inputFiles")
            if not isinstance(input_files, list) or not input_files:
                raise DatasetError(f"Missing inputs for case: {case.get('id')}")
            for input_file in input_files:
                input_path = self.source_root / self.dataset._safe_relative(
                    str(input_file)
                )
                if not input_path.is_file():
                    raise DatasetError(
                        f"Evaluation input is missing: {input_file}"
                    )
            expected = case.get("expected")
            if not isinstance(expected, dict):
                raise DatasetError(f"Missing expected value for case: {case.get('id')}")
            if "file" in expected:
                expected_path = self.source_root / self.dataset._safe_relative(
                    str(expected["file"])
                )
                value = self._read_json(expected_path)
                self._json_pointer(value, str(expected.get("pointer", "")))
            elif "value" not in expected:
                raise DatasetError(f"Expected value is incomplete: {case.get('id')}")
        criteria = benchmark.get("passCriteria")
        if not isinstance(criteria, dict):
            raise DatasetError("Evaluation pass criteria are missing.")
        if not 0 <= float(criteria.get("minimumOverallScore", -1)) <= 100:
            raise DatasetError("Evaluation minimum score is invalid.")

    def _validate_results(
        self, results: dict[str, Any], benchmark: dict[str, Any]
    ) -> None:
        if results.get("schemaVersion") != self.RESULT_SCHEMA_VERSION:
            raise DatasetError("Evaluation results schema version is unsupported.")
        if results.get("dataset") != benchmark["dataset"]:
            raise DatasetError("Evaluation results dataset does not match benchmark.")
        if results.get("benchmark") != benchmark["benchmark"]:
            raise DatasetError("Evaluation results benchmark version does not match.")
        outputs = results.get("outputs")
        if not isinstance(outputs, dict):
            raise DatasetError("Evaluation results require an outputs object.")
        expected_ids = {case["id"] for case in benchmark["cases"]}
        unknown = set(outputs) - expected_ids
        if unknown:
            raise DatasetError(
                f"Evaluation results contain unknown cases: {', '.join(sorted(unknown))}"
            )

    def _score_case(self, case: dict[str, Any], actual: Any) -> EvaluationCaseResult:
        expected = self._expected_value(case["expected"])
        evaluator = case["evaluator"]
        if actual is None:
            score, detail = 0.0, "missing output"
        elif evaluator == "exact":
            score = 100.0 if actual == expected else 0.0
            detail = "exact match" if score else "value differs"
        elif evaluator == "subset":
            score = self._subset_score(expected, actual)
            detail = "recursive expected-field coverage"
        elif evaluator == "set_f1":
            score = self._set_f1(expected, actual)
            detail = "set precision/recall F1"
        else:
            score = self._range_score(expected, actual)
            detail = "numeric range"
        threshold = float(case["threshold"])
        return EvaluationCaseResult(
            case_id=case["id"],
            dimension=case["dimension"],
            score=score,
            threshold=threshold,
            passed=score >= threshold,
            critical=bool(case.get("critical", False)),
            detail=detail,
        )

    def _expected_value(self, expected: dict[str, Any]) -> Any:
        if "value" in expected:
            return expected["value"]
        payload = self._read_json(
            self.source_root / self.dataset._safe_relative(str(expected["file"]))
        )
        return self._json_pointer(payload, str(expected.get("pointer", "")))

    @classmethod
    def _subset_score(cls, expected: Any, actual: Any) -> float:
        matched, total = cls._subset_counts(expected, actual)
        return 100.0 * matched / total if total else 100.0

    @classmethod
    def _subset_counts(cls, expected: Any, actual: Any) -> tuple[int, int]:
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                return 0, max(1, len(expected))
            matched = total = 0
            for key, value in expected.items():
                child_matched, child_total = cls._subset_counts(
                    value, actual.get(key)
                )
                matched += child_matched
                total += child_total
            return matched, total
        if isinstance(expected, list):
            if not isinstance(actual, list):
                return 0, max(1, len(expected))
            return (
                sum(1 for value in expected if value in actual),
                max(1, len(expected)),
            )
        return (1, 1) if actual == expected else (0, 1)

    @staticmethod
    def _set_f1(expected: Any, actual: Any) -> float:
        if not isinstance(expected, list) or not isinstance(actual, list):
            return 0.0
        expected_set = {
            json.dumps(item, ensure_ascii=False, sort_keys=True) for item in expected
        }
        actual_set = {
            json.dumps(item, ensure_ascii=False, sort_keys=True) for item in actual
        }
        if not expected_set and not actual_set:
            return 100.0
        intersection = len(expected_set & actual_set)
        precision = intersection / len(actual_set) if actual_set else 0.0
        recall = intersection / len(expected_set) if expected_set else 0.0
        denominator = precision + recall
        return 200.0 * precision * recall / denominator if denominator else 0.0

    @staticmethod
    def _range_score(expected: Any, actual: Any) -> float:
        if not isinstance(expected, dict) or not isinstance(actual, (int, float)):
            return 0.0
        minimum = float(expected.get("minimum", float("-inf")))
        maximum = float(expected.get("maximum", float("inf")))
        return 100.0 if minimum <= float(actual) <= maximum else 0.0

    @staticmethod
    def _json_pointer(payload: Any, pointer: str) -> Any:
        if pointer in {"", "/"}:
            return payload
        current = payload
        for token in pointer.lstrip("/").split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(current, list):
                current = current[int(token)]
            elif isinstance(current, dict) and token in current:
                current = current[token]
            else:
                raise DatasetError(f"Invalid evaluation JSON pointer: {pointer}")
        return current

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise DatasetError(f"Invalid evaluation JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise DatasetError(f"Evaluation JSON must contain an object: {path}")
        return payload
