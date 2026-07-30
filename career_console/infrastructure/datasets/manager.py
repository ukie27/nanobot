"""Validate, seed, verify, and safely reset development datasets."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DatasetError(ValueError):
    """Raised when a development dataset violates its safety contract."""


@dataclass(frozen=True, slots=True)
class DatasetFile:
    path: str
    sha256: str
    size: int


class DevelopmentDatasetManager:
    SCHEMA_VERSION = "career-console.dataset.v1"
    DATASET_NAME = "career_console_v1"
    TEST_MARKER = Path(".runtime") / "career-console-test-workspace"
    SEED_RELATIVE_ROOT = Path("data") / "dev-dataset" / DATASET_NAME
    STATE_FILE = "seed-state.json"
    ALLOWED_SCENARIOS = {"full-journey"}
    REQUIRED_DIRECTORIES = {
        "profile",
        "opportunities",
        "jobs",
        "materials",
        "applications",
        "mail",
        "reviews",
        "interviews",
        "connectors",
        "evaluation",
    }
    _SECRET_PATTERNS = (
        re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
        re.compile(r"\b(?:api[_ -]?key|authorization|cookie|token)\s*[:=]\s*\S+",
                   re.IGNORECASE),
        re.compile(r"\b\d{5,}@qq\.com\b", re.IGNORECASE),
    )
    _EMAIL_PATTERN = re.compile(
        r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.IGNORECASE
    )
    _SAFE_EMAIL_DOMAINS = {"example.com", "example.org", "example.test"}

    def __init__(self, source_root: Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[3]
        self.source_root = (
            source_root
            or project_root / "tests" / "datasets" / self.DATASET_NAME
        ).resolve(strict=False)

    def validate(self) -> dict[str, Any]:
        manifest = self._manifest()
        self._validate_manifest(manifest)
        files = self._source_files(manifest)
        for item in files:
            path = self.source_root / item
            if not path.is_file():
                raise DatasetError(f"Dataset file is missing: {item}")
            self._validate_file(path, item)
        return {
            "dataset": self.DATASET_NAME,
            "schema_version": manifest["schemaVersion"],
            "scenario": manifest["scenario"],
            "timezone": manifest["timezone"],
            "base_time": manifest["baseTime"],
            "file_count": len(files),
            "files": [
                {
                    "path": record.path,
                    "sha256": record.sha256,
                    "size": record.size,
                }
                for item in files
                for record in [self._file_record(self.source_root / item, item)]
            ],
        }

    def seed(self, workspace: Path, *, scenario: str) -> dict[str, Any]:
        workspace = self._test_workspace(workspace)
        if scenario not in self.ALLOWED_SCENARIOS:
            raise DatasetError(f"Unknown dataset scenario: {scenario}")
        validation = self.validate()
        if validation["scenario"] != scenario:
            raise DatasetError(
                f"Dataset manifest does not provide scenario: {scenario}"
            )
        target = workspace / self.SEED_RELATIVE_ROOT
        target.mkdir(parents=True, exist_ok=True)
        expected_paths = set()
        for item in validation["files"]:
            relative = Path(str(item["path"]))
            source = self.source_root / relative
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            expected_paths.add(relative.as_posix())
        self._remove_stale_seed_files(target, expected_paths)
        state = {
            "schemaVersion": self.SCHEMA_VERSION,
            "dataset": self.DATASET_NAME,
            "scenario": scenario,
            "timezone": validation["timezone"],
            "baseTime": validation["base_time"],
            "files": validation["files"],
        }
        self._write_json(target / self.STATE_FILE, state)
        return {
            "workspace": str(workspace),
            "target": str(target),
            "scenario": scenario,
            "file_count": len(validation["files"]),
            "state_hash": self._json_hash(state),
        }

    def expect(self, workspace: Path, *, scenario: str) -> dict[str, Any]:
        workspace = self._test_workspace(workspace)
        target = workspace / self.SEED_RELATIVE_ROOT
        state_path = target / self.STATE_FILE
        if not state_path.is_file():
            raise DatasetError("Dataset has not been seeded in this test workspace.")
        state = self._read_json(state_path, "seed state")
        if state.get("schemaVersion") != self.SCHEMA_VERSION:
            raise DatasetError("Seed state schema version is unsupported.")
        if state.get("scenario") != scenario:
            raise DatasetError("Seeded scenario does not match the requested scenario.")
        files = state.get("files")
        if not isinstance(files, list) or not files:
            raise DatasetError("Seed state does not contain a file inventory.")
        for item in files:
            if not isinstance(item, dict):
                raise DatasetError("Seed state file inventory is invalid.")
            relative = self._safe_relative(str(item.get("path", "")))
            path = target / relative
            if not path.is_file():
                raise DatasetError(f"Seeded file is missing: {relative.as_posix()}")
            record = self._file_record(path, relative.as_posix())
            if record.sha256 != item.get("sha256") or record.size != item.get("size"):
                raise DatasetError(
                    f"Seeded file differs from the expected dataset: {relative.as_posix()}"
                )
        return {
            "workspace": str(workspace),
            "scenario": scenario,
            "file_count": len(files),
            "state_hash": self._json_hash(state),
            "valid": True,
        }

    def reset(self, workspace: Path) -> dict[str, Any]:
        workspace = self._test_workspace(workspace)
        target = (workspace / self.SEED_RELATIVE_ROOT).resolve(strict=False)
        expected_target = (workspace / self.SEED_RELATIVE_ROOT).resolve(strict=False)
        if target != expected_target or workspace not in target.parents:
            raise DatasetError("Dataset reset target escaped the test workspace.")
        removed = 0
        if target.is_dir():
            for path in sorted(target.rglob("*"), key=lambda item: len(item.parts),
                               reverse=True):
                if path.is_file() or path.is_symlink():
                    path.unlink()
                    removed += 1
                elif path.is_dir():
                    path.rmdir()
            target.rmdir()
            for parent in (target.parent, target.parent.parent):
                if parent.is_dir() and not any(parent.iterdir()):
                    parent.rmdir()
        return {
            "workspace": str(workspace),
            "target": str(target),
            "removed_file_count": removed,
            "marker_preserved": (workspace / self.TEST_MARKER).is_file(),
        }

    def _manifest(self) -> dict[str, Any]:
        path = self.source_root / "manifest.yaml"
        if not path.is_file():
            raise DatasetError(f"Dataset manifest is missing: {path}")
        return self._read_json(path, "manifest")

    def _validate_manifest(self, manifest: dict[str, Any]) -> None:
        expected = {
            "schemaVersion": self.SCHEMA_VERSION,
            "dataset": self.DATASET_NAME,
            "scenario": "full-journey",
            "timezone": "Asia/Shanghai",
        }
        for key, value in expected.items():
            if manifest.get(key) != value:
                raise DatasetError(f"Manifest field {key} must be {value}.")
        base_time = manifest.get("baseTime")
        if not isinstance(base_time, str) or not base_time.endswith("+08:00"):
            raise DatasetError("Manifest baseTime must be an explicit China time.")
        directories = manifest.get("directories")
        if set(directories or []) != self.REQUIRED_DIRECTORIES:
            raise DatasetError("Manifest directory inventory is incomplete.")
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise DatasetError("Manifest files must be a non-empty list.")
        normalized = [self._safe_relative(str(item)).as_posix() for item in files]
        if len(normalized) != len(set(normalized)):
            raise DatasetError("Manifest contains duplicate file paths.")
        for directory in self.REQUIRED_DIRECTORIES:
            if not any(item.startswith(f"{directory}/") for item in normalized):
                raise DatasetError(f"Manifest has no files for directory: {directory}")

    def _source_files(self, manifest: dict[str, Any]) -> list[str]:
        return sorted(
            self._safe_relative(str(item)).as_posix()
            for item in manifest["files"]
        )

    def _validate_file(self, path: Path, relative: str) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise DatasetError(f"Dataset file is not UTF-8: {relative}") from exc
        lowered = text.casefold()
        for pattern in self._SECRET_PATTERNS:
            if pattern.search(text):
                raise DatasetError(f"Potential secret or real account in: {relative}")
        for match in self._EMAIL_PATTERN.finditer(text):
            if match.group(1).casefold() not in self._SAFE_EMAIL_DOMAINS:
                raise DatasetError(f"Non-example email address in: {relative}")
        if path.suffix == ".json":
            self._read_json(path, relative)
        if path.suffix == ".eml":
            for header in ("from:", "to:", "subject:", "date:"):
                if header not in lowered:
                    raise DatasetError(
                        f"Mail fixture {relative} is missing header {header[:-1]}."
                    )

    def _test_workspace(self, workspace: Path) -> Path:
        resolved = workspace.expanduser().resolve(strict=False)
        marker = resolved / self.TEST_MARKER
        if not resolved.is_dir() or not marker.is_file():
            raise DatasetError(
                "Dataset commands require an existing test workspace marker at "
                f"{self.TEST_MARKER.as_posix()}."
            )
        return resolved

    def _remove_stale_seed_files(
        self, target: Path, expected_paths: set[str]
    ) -> None:
        allowed = {*expected_paths, self.STATE_FILE}
        for path in sorted(target.rglob("*"), key=lambda item: len(item.parts),
                           reverse=True):
            relative = path.relative_to(target).as_posix()
            if path.is_file() and relative not in allowed:
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()

    @staticmethod
    def _safe_relative(value: str) -> Path:
        path = Path(value)
        if (
            not value
            or path.is_absolute()
            or ".." in path.parts
            or path.as_posix().startswith("/")
        ):
            raise DatasetError(f"Unsafe dataset path: {value}")
        return path

    @staticmethod
    def _file_record(path: Path, relative: str) -> DatasetFile:
        content = path.read_bytes()
        return DatasetFile(
            path=relative,
            sha256=hashlib.sha256(content).hexdigest(),
            size=len(content),
        )

    @staticmethod
    def _read_json(path: Path, label: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise DatasetError(f"Invalid JSON-compatible {label}: {path}") from exc
        if not isinstance(value, dict):
            raise DatasetError(f"{label} must contain an object.")
        return value

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    @staticmethod
    def _json_hash(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
