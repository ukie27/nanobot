"""Fail-closed process adapter for the external OpenCLI application."""

from __future__ import annotations

import json
import os
import shutil
import signal
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
        ("nowcoder", "whoami"),
        ("nowcoder", "login"),
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
        # A health check must return quickly enough to remain useful in an
        # interactive settings form. Login has its own longer, user-controlled
        # timeout; whoami should never hold the UI for the general 45 seconds.
        return self._object(self._run(profile, "whoami", [], timeout=15))

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

    def nowcoder_status(self) -> dict[str, Any]:
        return self._object(self._run_command("nowcoder", "whoami", [], timeout=15))

    def nowcoder_login(self, *, timeout: int = 300) -> dict[str, Any]:
        return self._object(
            self._run_command(
                "nowcoder",
                "login",
                ["--timeout", str(max(30, min(timeout, 600)))],
                timeout=timeout + 15,
            )
        )

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
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        )
        try:
            process = subprocess.Popen(
                [*self._command_prefix(), *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                creationflags=creationflags,
                start_new_session=os.name != "nt",
            )
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            self._terminate_process_tree(process)
            raise OpenCliError(ConnectorError.TIMEOUT, "OpenCLI 执行超时。") from exc
        except OSError as exc:
            raise OpenCliError(ConnectorError.NOT_INSTALLED, "OpenCLI 无法启动。") from exc
        if process.returncode:
            code = {
                2: ConnectorError.INVALID_ARGUMENT,
                69: ConnectorError.BRIDGE_UNAVAILABLE,
                75: ConnectorError.TIMEOUT,
                77: ConnectorError.AUTH_REQUIRED,
                78: ConnectorError.BRIDGE_UNAVAILABLE,
            }.get(process.returncode, ConnectorError.EXECUTION_FAILED)
            message = "OpenCLI 命令执行失败。"
            if structured:
                try:
                    envelope = json.loads(stderr or stdout)
                    message = str(envelope.get("error", {}).get("message") or message)
                except (json.JSONDecodeError, AttributeError):
                    pass
            raise OpenCliError(str(code), message)
        return stdout.strip()

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
        """Stop command shims and their descendants without leaving pipe holders."""
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/pid", str(process.pid), "/t", "/f"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()

    def _command_prefix(self) -> list[str]:
        path = Path(self.executable)
        suffix = path.suffix.casefold()
        if suffix in {".js", ".mjs"}:
            node = shutil.which("node")
            if not node:
                raise OpenCliError(ConnectorError.NOT_INSTALLED, "OpenCLI 需要 Node.js。")
            return [node, self.executable]
        if suffix in {".cmd", ".bat"}:
            # npm command shims are executable through cmd.exe. Do not probe the
            # sibling .ps1 shim first: managed Windows environments can allow
            # executing the configured .cmd while denying metadata access to
            # files in the user's AppData directory.
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
