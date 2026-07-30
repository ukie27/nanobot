"""Controlled OpenCLI BOSS connector use cases."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from career_console.application.ports.connector_gateway import (
    ConnectorGateway,
    OpenCliError,
    OpenCliRunner,
)
from career_console.application.ports.opportunity_gateway import OpportunityGateway
from career_console.application.ports.job_recommendation import JobDescriptionDiscovery
from career_console.application.services.jobs import JobApplicationService
from career_console.domain.connectors import (
    ConnectorError,
    boss_external_id,
    nowcoder_external_id,
    validate_nowcoder_lookback,
    validate_profile_alias,
    validate_schedule_times,
)


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
        # Daily discovery belongs exclusively to Nowcoder; BOSS remains manual-only.
        values["schedule_enabled"] = False
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
        checked_at = datetime.now(ZoneInfo("Asia/Shanghai"))
        try:
            version = self.runner.version()
            identity = self.runner.boss_status(profile=config["profile_alias"])
            config = self.gateway.update_boss(
                health_status="healthy",
                session_status="authenticated",
                session_identity=self._safe_identity(identity),
                session_checked_at=checked_at,
                last_error_code=None,
            )
            return {
                "status": "healthy",
                "opencli_version": version,
                "identity": identity,
                "config": config,
            }
        except OpenCliError as exc:
            status = (
                "requires_login"
                if exc.code == ConnectorError.AUTH_REQUIRED
                else "unavailable"
            )
            config = self.gateway.update_boss(
                health_status="unavailable" if status == "unavailable" else "healthy",
                session_status=status,
                session_identity={},
                session_checked_at=checked_at,
                last_error_code=exc.code,
            )
            return {"status": status, "error_code": exc.code, "message": str(exc), "config": config}

    def login(self, *, timeout: int = 300) -> dict[str, Any]:
        config = self.gateway.get_or_create_boss()
        try:
            result = self.runner.boss_login(profile=config["profile_alias"], timeout=timeout)
            identity = self.runner.boss_status(profile=config["profile_alias"])
            self.gateway.update_boss(
                health_status="healthy",
                session_status="authenticated",
                session_identity=self._safe_identity(identity),
                session_checked_at=datetime.now(ZoneInfo("Asia/Shanghai")),
                last_error_code=None,
            )
            return result
        except OpenCliError as exc:
            self.gateway.update_boss(
                health_status="unavailable"
                if exc.code != ConnectorError.AUTH_REQUIRED
                else "healthy",
                session_status="requires_login"
                if exc.code == ConnectorError.AUTH_REQUIRED
                else "unavailable",
                session_identity={},
                session_checked_at=datetime.now(ZoneInfo("Asia/Shanghai")),
                last_error_code=exc.code,
            )
            raise

    def scan(self, *, trigger_type: str = "manual") -> dict[str, Any]:
        config = self.gateway.get_or_create_boss()
        if not config["enabled"]:
            raise ValueError("请先启用 BOSS Connector。")
        if config["session_status"] != "authenticated":
            raise OpenCliError(ConnectorError.AUTH_REQUIRED, "BOSS 会话未登录或已经过期。")
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
        return None

    @staticmethod
    def _safe_identity(identity: dict[str, Any]) -> dict[str, Any]:
        allowed = {"site", "logged_in", "user_type", "nickname", "username", "display_name"}
        return {
            key: value
            for key, value in identity.items()
            if key in allowed and isinstance(value, (str, bool, int))
        }

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


class NowcoderConnectorApplicationService:
    """Read-only campus schedule ingestion with a strict China-calendar window."""

    def __init__(
        self,
        *,
        gateway: ConnectorGateway,
        runner: OpenCliRunner,
        opportunities: OpportunityGateway,
        jobs: JobApplicationService,
        jd_discovery: JobDescriptionDiscovery,
        recommendations: Any,
    ) -> None:
        self.gateway = gateway
        self.runner = runner
        self.opportunities = opportunities
        self.jobs = jobs
        self.jd_discovery = jd_discovery
        self.recommendations = recommendations

    def get(self) -> dict[str, Any]:
        result = self.gateway.get_or_create_nowcoder()
        connector_id = result["id"]
        result["runs"] = self.gateway.list_runs(connector_id=connector_id)
        result["quarantine"] = self.gateway.list_quarantine(connector_id=connector_id)
        result["automatic_scope"] = "today"
        result["manual_lookback_options"] = [0, 7, 14, 30]
        return result

    def configure(self, **values: Any) -> dict[str, Any]:
        values["schedule_times"] = validate_schedule_times(values["schedule_times"])
        values["search_query"] = values.get("search_query", "").strip()
        values["city"] = values.get("city", "全国").strip() or "全国"
        values["timezone"] = "Asia/Shanghai"
        if not 1 <= int(values["result_limit"]) <= 1000:
            raise ValueError("牛客每次同步数量必须在 1 到 1000 之间。")
        return self.gateway.update_nowcoder(**values)

    def health(self) -> dict[str, Any]:
        config = self.gateway.get_or_create_nowcoder()
        checked_at = datetime.now(ZoneInfo("Asia/Shanghai"))
        try:
            version = self.runner.version()
            identity = self.runner.nowcoder_status()
            config = self.gateway.update_nowcoder(
                health_status="healthy",
                session_status="authenticated",
                session_identity=ConnectorApplicationService._safe_identity(identity),
                session_checked_at=checked_at,
                last_error_code=None,
            )
            return {
                "status": "healthy",
                "opencli_version": version,
                "identity": identity,
                "config": config,
            }
        except OpenCliError as exc:
            session_status = (
                "requires_login"
                if exc.code == ConnectorError.AUTH_REQUIRED
                else "unavailable"
            )
            config = self.gateway.update_nowcoder(
                health_status="healthy"
                if session_status == "requires_login"
                else "unavailable",
                session_status=session_status,
                session_identity={},
                session_checked_at=checked_at,
                last_error_code=exc.code,
            )
            return {
                "status": session_status,
                "error_code": exc.code,
                "message": str(exc),
                "config": config,
            }

    def login(self, *, timeout: int = 300) -> dict[str, Any]:
        try:
            result = self.runner.nowcoder_login(timeout=timeout)
            identity = self.runner.nowcoder_status()
            self.gateway.update_nowcoder(
                health_status="healthy",
                session_status="authenticated",
                session_identity=ConnectorApplicationService._safe_identity(identity),
                session_checked_at=datetime.now(ZoneInfo("Asia/Shanghai")),
                last_error_code=None,
            )
            return result
        except OpenCliError as exc:
            self.gateway.update_nowcoder(
                health_status="healthy"
                if exc.code == ConnectorError.AUTH_REQUIRED
                else "unavailable",
                session_status="requires_login"
                if exc.code == ConnectorError.AUTH_REQUIRED
                else "unavailable",
                session_identity={},
                session_checked_at=datetime.now(ZoneInfo("Asia/Shanghai")),
                last_error_code=exc.code,
            )
            raise

    def scan(
        self, *, lookback_days: int = 0, trigger_type: str = "manual",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
        scheduled = trigger_type == "schedule"
        lookback_days = validate_nowcoder_lookback(lookback_days, scheduled=scheduled)
        config = self.gateway.get_or_create_nowcoder()
        if not config["enabled"]:
            raise ValueError("请先启用牛客校招日程 Connector。")
        if config["session_status"] != "authenticated":
            raise OpenCliError(ConnectorError.AUTH_REQUIRED, "牛客会话未登录或已经过期。")
        recorded_trigger = (
            trigger_type
            if scheduled
            else ("manual_today" if lookback_days == 0 else f"manual_{lookback_days}d")
        )
        run = self.gateway.start_run(
            trigger_type=recorded_trigger,
            connector_id=config["id"],
            now=now,
        )
        counts = {
            "discovered_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "duplicate_count": 0,
            "quarantined_count": 0,
            "opportunities_discovered": 0,
            "jd_discovered": 0,
            "jd_imported": 0,
            "recommendations_created": 0,
            "recommendations_rejected": 0,
            "jd_discovery_failed": 0,
            "recommendation_failed": 0,
        }
        try:
            rows = self.runner.nowcoder_schedule(
                lookback_days=lookback_days,
                limit=config["result_limit"],
                query=config["search_query"],
            )
            counts["discovered_count"] = len(rows)
            for row in rows:
                self._process_row(config, run["id"], row, lookback_days, counts, now)
            finished = self.gateway.finish_run(run["id"], now=now, **counts)
            return {**finished, **{
                key: value for key, value in counts.items()
                if key not in finished
            }}
        except OpenCliError as exc:
            self.gateway.fail_run(run["id"], error_code=exc.code, now=now)
            raise
        except Exception:
            self.gateway.fail_run(
                run["id"], error_code=ConnectorError.EXECUTION_FAILED, now=now
            )
            raise

    def run_due(self, *, now: datetime | None = None) -> dict[str, Any] | None:
        now = now or datetime.now(UTC)
        config = self.gateway.get_or_create_nowcoder()
        if not self.gateway.due(connector_id=config["id"], now=now):
            return None
        return self.scan(lookback_days=0, trigger_type="schedule", now=now)

    def _process_row(
        self,
        config: dict[str, Any],
        run_id: str,
        row: dict[str, Any],
        lookback_days: int,
        counts: dict[str, int],
        now: datetime,
    ) -> None:
        try:
            external_id = self._required(row, "id")
            source_url = self._required(row, "source_url")
            nowcoder_external_id(external_id, source_url)
            self._required(row, "company")
            self._required(row, "batch")
            self._required(row, "application_url")
            self._validate_collected_at(row, lookback_days, now)
            canonical = json.dumps(
                row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            event, created = self.gateway.source_event(
                connector_id=config["id"],
                sync_run_id=run_id,
                external_id=external_id,
                source_url=source_url,
                content_hash=content_hash,
                payload=row,
                schema_version="opencli.nowcoder.schedule.v1",
            )
            if not created:
                counts["duplicate_count"] += 1
            else:
                opportunity, opportunity_created, opportunity_updated = self.opportunities.ingest(
                    connector_id=config["id"],
                    source_event_id=event["id"],
                    external_id=external_id,
                    source_url=source_url,
                    content_hash=content_hash,
                    payload=row,
                )
                self.gateway.complete_opportunity_event(
                    event["id"], opportunity_id=opportunity["id"]
                )
                if opportunity_created:
                    counts["created_count"] += 1
                elif opportunity_updated:
                    counts["updated_count"] += 1
                else:
                    counts["duplicate_count"] += 1
            opportunity_id = event.get("opportunity_id")
            if created:
                opportunity_id = opportunity["id"]
            if not opportunity_id:
                return
            counts["opportunities_discovered"] += 1
            opportunity_payload = {**row, "id": opportunity_id}
            discovery = self.jd_discovery.discover(opportunity=opportunity_payload)
            if discovery.status != "succeeded":
                counts["jd_discovery_failed"] += 1
                self.gateway.record_event_error(
                    event["id"],
                    error_code=discovery.error_code or "jd_discovery_failed",
                )
                return
            counts["jd_discovered"] += len(discovery.jobs)
            manual_directions = [
                item.strip()
                for item in config.get("search_query", "").replace("，", ",").split(",")
                if item.strip()
            ]
            for discovered in discovery.jobs:
                try:
                    imported = self.jobs.import_connector(
                        name=discovered.name,
                        text=discovered.text,
                        source_url=discovered.url,
                        source_type="nowcoder_official_jd",
                        opportunity_id=opportunity_id,
                    )
                    counts["jd_imported"] += int(not imported.get("duplicate", False))
                    recommendation = self.recommendations.analyze(
                        imported["id"],
                        opportunity_id=opportunity_id,
                        manual_directions=manual_directions,
                    )
                    if recommendation is None:
                        counts["recommendations_rejected"] += 1
                    else:
                        counts["recommendations_created"] += int(
                            recommendation["status"] == "active"
                        )
                except Exception as exc:
                    code = str(getattr(exc, "code", "recommendation_failed"))
                    if code.startswith("jd_") or code.startswith("job_"):
                        counts["jd_discovery_failed"] += 1
                    else:
                        counts["recommendation_failed"] += 1
                    self.gateway.record_event_error(event["id"], error_code=code)
        except (KeyError, TypeError, ValueError, OpenCliError) as exc:
            if isinstance(exc, OpenCliError) and exc.code != ConnectorError.SCHEMA_INVALID:
                raise
            payload = row if isinstance(row, dict) else {"invalid": True}
            canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
            external_id = str(payload.get("id") or "")
            if not external_id:
                external_id = f"invalid:{hashlib.sha256(canonical.encode()).hexdigest()[:24]}"
            event, created = self.gateway.source_event(
                connector_id=config["id"],
                sync_run_id=run_id,
                external_id=external_id,
                source_url=str(payload.get("source_url") or ""),
                content_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                payload=payload,
                schema_version="opencli.nowcoder.schedule.v1",
            )
            if created:
                self.gateway.quarantine_event(
                    event["id"], error_code=ConnectorError.SCHEMA_INVALID
                )
                counts["quarantined_count"] += 1
            else:
                counts["duplicate_count"] += 1

    @staticmethod
    def _required(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"缺少字段 {key}。")
        return value.strip()

    @staticmethod
    def _validate_collected_at(
        row: dict[str, Any], lookback_days: int, now: datetime | None = None
    ) -> None:
        raw = NowcoderConnectorApplicationService._required(row, "collected_at")
        try:
            collected = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("collected_at 不是有效时间。") from exc
        china = ZoneInfo("Asia/Shanghai")
        today = (now or datetime.now(china)).astimezone(china).date()
        earliest = today - timedelta(days=(lookback_days or 1) - 1)
        collected_date = collected.astimezone(china).date()
        if not earliest <= collected_date <= today:
            raise ValueError("牛客日程超出本次允许的中国时间范围。")

    @staticmethod
    def _schedule_text(row: dict[str, Any]) -> str:
        fields = [
            ("公司", row.get("company")),
            ("招聘批次", row.get("batch")),
            ("城市", row.get("cities")),
            ("岗位方向", row.get("careers")),
            ("行业", row.get("industries")),
            ("公司信息", row.get("evaluation")),
            ("牛客收录时间", row.get("collected_at")),
            ("网申开始", row.get("application_starts_at")),
            ("网申截止", row.get("application_ends_at")),
            ("招聘公告", row.get("announcement_url")),
            ("投递入口", row.get("application_url")),
        ]
        return "\n".join(f"{label}：{value}" for label, value in fields if value)
