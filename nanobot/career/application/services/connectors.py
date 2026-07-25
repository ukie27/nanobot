"""Controlled OpenCLI BOSS connector use cases."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from nanobot.career.application.ports.connector_gateway import ConnectorGateway, OpenCliRunner
from nanobot.career.application.services.jobs import JobApplicationService
from nanobot.career.domain.connectors import (
    ConnectorError,
    boss_external_id,
    validate_profile_alias,
    validate_schedule_times,
)
from nanobot.career.infrastructure.connectors import OpenCliError


class ConnectorApplicationService:
    def __init__(
        self,
        *,
        gateway: ConnectorGateway,
        runner: OpenCliRunner,
        jobs: JobApplicationService,
    ) -> None:
        self.gateway = gateway
        self.runner = runner
        self.jobs = jobs

    def get_boss(self) -> dict[str, Any]:
        result = self.gateway.get_or_create_boss()
        result["runs"] = self.gateway.list_runs()
        result["quarantine"] = self.gateway.list_quarantine()
        return result

    def configure(self, **values: Any) -> dict[str, Any]:
        values["profile_alias"] = validate_profile_alias(values["profile_alias"])
        values["schedule_times"] = validate_schedule_times(values["schedule_times"])
        try:
            ZoneInfo(values["timezone"])
        except ZoneInfoNotFoundError as exc:
            raise ValueError("必须使用有效的 IANA 时区。") from exc
        values["search_query"] = values["search_query"].strip()
        values["city"] = values["city"].strip()
        if not values["city"]:
            raise ValueError("城市不能为空。")
        return self.gateway.update_boss(**values)

    def health(self) -> dict[str, Any]:
        config = self.gateway.get_or_create_boss()
        try:
            version = self.runner.version()
            identity = self.runner.boss_status(profile=config["profile_alias"])
            config = self.gateway.update_boss(health_status="healthy", last_error_code=None)
            return {
                "status": "healthy",
                "opencli_version": version,
                "identity": identity,
                "config": config,
            }
        except OpenCliError as exc:
            status = "requires_login" if exc.code == ConnectorError.AUTH_REQUIRED else "unavailable"
            self.gateway.update_boss(health_status=status, last_error_code=exc.code)
            return {"status": status, "error_code": exc.code, "message": str(exc), "config": config}

    def login(self, *, timeout: int = 300) -> dict[str, Any]:
        config = self.gateway.get_or_create_boss()
        result = self.runner.boss_login(profile=config["profile_alias"], timeout=timeout)
        self.gateway.update_boss(health_status="healthy", last_error_code=None)
        return result

    def scan(self, *, trigger_type: str = "manual") -> dict[str, Any]:
        config = self.gateway.get_or_create_boss()
        if not config["enabled"]:
            raise ValueError("请先启用 BOSS Connector。")
        run = self.gateway.start_run(trigger_type=trigger_type)
        counts = {
            "discovered_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "duplicate_count": 0,
            "quarantined_count": 0,
        }
        try:
            rows = self.runner.boss_search(
                profile=config["profile_alias"],
                query=config["search_query"],
                city=config["city"],
                limit=config["result_limit"],
            )
            counts["discovered_count"] = len(rows)
            for row in rows:
                self._process_search_row(config, run["id"], row, counts)
            return self.gateway.finish_run(run["id"], **counts)
        except OpenCliError as exc:
            self.gateway.fail_run(run["id"], error_code=exc.code)
            raise
        except Exception:
            self.gateway.fail_run(run["id"], error_code=ConnectorError.EXECUTION_FAILED)
            raise

    def run_due(self) -> dict[str, Any] | None:
        return self.scan(trigger_type="schedule") if self.gateway.due() else None

    def _process_search_row(
        self,
        config: dict[str, Any],
        run_id: str,
        row: dict[str, Any],
        counts: dict[str, int],
    ) -> None:
        try:
            security_id = self._required(row, "security_id")
            source_url = self._required(row, "url")
            external_id = boss_external_id(source_url)
            detail = self.runner.boss_detail(
                profile=config["profile_alias"], security_id=security_id
            )
            self._validate_detail(detail)
            canonical = json.dumps(
                detail, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            event, created = self.gateway.source_event(
                sync_run_id=run_id,
                external_id=external_id,
                source_url=source_url,
                content_hash=content_hash,
                payload=detail,
                schema_version="opencli.boss.detail.v1",
            )
            if not created:
                counts["duplicate_count"] += 1
                return
            imported = self.jobs.import_connector(
                name=f"BOSS · {detail['company']} · {detail['name']}",
                text=self._detail_text(detail),
                source_url=source_url,
                source_type="opencli_boss",
            )
            self.gateway.complete_event(event["id"], job_post_id=imported["id"])
            if imported.get("created"):
                counts["created_count"] += 1
            elif imported.get("duplicate"):
                counts["duplicate_count"] += 1
            else:
                counts["updated_count"] += 1
        except (KeyError, TypeError, ValueError, OpenCliError) as exc:
            if isinstance(exc, OpenCliError) and exc.code != ConnectorError.SCHEMA_INVALID:
                raise
            payload = row if isinstance(row, dict) else {"invalid": True}
            canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
            event, created = self.gateway.source_event(
                sync_run_id=run_id,
                external_id=f"invalid:{hashlib.sha256(canonical.encode()).hexdigest()[:24]}",
                source_url=str(payload.get("url") or ""),
                content_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                payload=payload,
                schema_version="opencli.boss.search.v1",
            )
            if created:
                self.gateway.quarantine_event(event["id"], error_code=ConnectorError.SCHEMA_INVALID)
                counts["quarantined_count"] += 1
            else:
                counts["duplicate_count"] += 1

    @staticmethod
    def _required(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"缺少字段 {key}。")
        return value.strip()

    @classmethod
    def _validate_detail(cls, detail: dict[str, Any]) -> None:
        for key in ("name", "company", "description", "url"):
            cls._required(detail, key)
        boss_external_id(cls._required(detail, "url"))

    @staticmethod
    def _detail_text(detail: dict[str, Any]) -> str:
        fields = [
            ("职位", detail.get("name")),
            ("公司", detail.get("company")),
            (
                "地点",
                " · ".join(
                    filter(
                        None, [detail.get("city"), detail.get("district"), detail.get("address")]
                    )
                ),
            ),
            ("薪资", detail.get("salary")),
            ("经验", detail.get("experience")),
            ("学历", detail.get("degree")),
            ("技能", detail.get("skills")),
            ("福利", detail.get("welfare")),
            ("行业", detail.get("industry")),
            ("规模", detail.get("scale")),
            ("融资阶段", detail.get("stage")),
            ("职位描述", detail.get("description")),
        ]
        return "\n".join(f"{label}：{value}" for label, value in fields if value)
