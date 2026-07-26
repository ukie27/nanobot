"""Fail-closed process adapter for the external OpenCLI application."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from career_console.application.ports.connector_gateway import OpenCliError
from career_console.domain.connectors import ConnectorError


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


class OpenCliProcessRunner:
    """Invoke only explicitly approved OpenCLI commands with argv and ``shell=False``."""

    _ALLOWED = {
        ("boss", "whoami"),
        ("boss", "login"),
        ("boss", "search"),
        ("boss", "detail"),
        ("nowcoder", "schedule"),
    }

    def __init__(self, executable: str | Path | None = None, *, timeout_seconds: int = 45) -> None:
        self.executable = str(executable or shutil.which("opencli") or "")
        self.timeout_seconds = timeout_seconds

    @property
    def installed(self) -> bool:
        return bool(self.executable)

    def version(self) -> str:
        result = self._execute(["--version"], timeout=10, structured=False)
        return result.strip()

    def boss_status(self, *, profile: str) -> dict[str, Any]:
        return self._object(self._run(profile, "whoami", []))

    def boss_login(self, *, profile: str, timeout: int = 300) -> dict[str, Any]:
        return self._object(
            self._run(
                profile,
                "login",
                ["--timeout", str(max(30, min(timeout, 600)))],
                timeout=timeout + 15,
            )
        )

    def boss_search(
        self, *, profile: str, query: str, city: str, limit: int
    ) -> list[dict[str, Any]]:
        args = []
        if query.strip():
            args.append(query.strip())
        args.extend(["--city", city.strip(), "--limit", str(max(1, min(limit, 50)))])
        payload = self._run(profile, "search", args)
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise OpenCliError(ConnectorError.SCHEMA_INVALID, "OpenCLI search 输出不是对象数组。")
        return payload

    def boss_detail(self, *, profile: str, security_id: str) -> dict[str, Any]:
        if not security_id.strip() or any(char in security_id for char in "\r\n\0"):
            raise OpenCliError(ConnectorError.INVALID_ARGUMENT, "security_id 无效。")
        return self._object(self._run(profile, "detail", [security_id.strip()]))

    def nowcoder_schedule(
        self, *, lookback_days: int, limit: int, query: str = ""
    ) -> list[dict[str, Any]]:
        args = [
            "--lookback",
            str(lookback_days),
            "--limit",
            str(max(1, min(limit, 1000))),
        ]
        if query.strip():
            args.extend(["--query", query.strip()])
        payload = self._run_command("nowcoder", "schedule", args)
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise OpenCliError(
                ConnectorError.SCHEMA_INVALID, "OpenCLI 牛客日程输出不是对象数组。"
            )
        return payload

    def _run(
        self, profile: str, command: str, args: list[str], *, timeout: int | None = None
    ) -> Any:
        if ("boss", command) not in self._ALLOWED:
            raise OpenCliError(
                ConnectorError.COMMAND_DENIED, "该 OpenCLI 命令不在只读 allowlist 中。"
            )
        argv = ["--profile", profile, "boss", command, *args, "-f", "json"]
        return self._execute_json(argv, timeout=timeout or self.timeout_seconds)

    def _run_command(
        self, site: str, command: str, args: list[str], *, timeout: int | None = None
    ) -> Any:
        if (site, command) not in self._ALLOWED:
            raise OpenCliError(
                ConnectorError.COMMAND_DENIED, "该 OpenCLI 命令不在只读 allowlist 中。"
            )
        return self._execute_json(
            [site, command, *args, "-f", "json"],
            timeout=timeout or self.timeout_seconds,
        )

    def _execute_json(self, argv: list[str], *, timeout: int) -> Any:
        output = self._execute(argv, timeout=timeout or self.timeout_seconds, structured=True)
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise OpenCliError(ConnectorError.SCHEMA_INVALID, "OpenCLI 返回了无效 JSON。") from exc

    def _execute(self, args: list[str], *, timeout: int, structured: bool) -> str:
        if not self.executable:
            raise OpenCliError(ConnectorError.NOT_INSTALLED, "未找到 OpenCLI 可执行程序。")
        try:
            result = subprocess.run(
                [*self._command_prefix(), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OpenCliError(ConnectorError.TIMEOUT, "OpenCLI 执行超时。") from exc
        except OSError as exc:
            raise OpenCliError(ConnectorError.NOT_INSTALLED, "OpenCLI 无法启动。") from exc
        if result.returncode:
            code = {
                2: ConnectorError.INVALID_ARGUMENT,
                69: ConnectorError.BRIDGE_UNAVAILABLE,
                75: ConnectorError.TIMEOUT,
                77: ConnectorError.AUTH_REQUIRED,
                78: ConnectorError.BRIDGE_UNAVAILABLE,
            }.get(result.returncode, ConnectorError.EXECUTION_FAILED)
            message = "OpenCLI 命令执行失败。"
            if structured:
                try:
                    envelope = json.loads(result.stderr or result.stdout)
                    message = str(envelope.get("error", {}).get("message") or message)
                except (json.JSONDecodeError, AttributeError):
                    pass
            raise OpenCliError(str(code), message)
        return result.stdout.strip()

    def _command_prefix(self) -> list[str]:
        path = Path(self.executable)
        suffix = path.suffix.casefold()
        if suffix in {".js", ".mjs"}:
            node = shutil.which("node")
            if not node:
                raise OpenCliError(ConnectorError.NOT_INSTALLED, "OpenCLI 需要 Node.js。")
            return [node, self.executable]
        if suffix in {".cmd", ".bat"}:
            powershell_script = path.with_suffix(".ps1")
            powershell = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
            if powershell and powershell_script.is_file():
                return [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(powershell_script),
                ]
            command = shutil.which("cmd.exe") or "cmd.exe"
            return [command, "/d", "/s", "/c", self.executable]
        return [self.executable]

    @staticmethod
    def _object(payload: Any) -> dict[str, Any]:
        if isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], dict):
            return payload[0]
        if isinstance(payload, dict):
            return payload
        raise OpenCliError(ConnectorError.SCHEMA_INVALID, "OpenCLI 输出不是对象。")
