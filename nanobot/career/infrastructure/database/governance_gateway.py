"""Cross-module workspace queries and recoverable local data governance."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from nanobot.career.infrastructure.database.backup import backup_database, database_revision
from nanobot.career.infrastructure.database.models import (
    AgentRunModel,
    ApplicationEventModel,
    ApplicationMaterialSnapshotModel,
    ApplicationModel,
    Base,
    BlobModel,
    CareerTaskModel,
    ConnectorConfigModel,
    ImprovementItemModel,
    InterviewFeedbackModel,
    InterviewModel,
    JobPostModel,
    MaterialDraftModel,
    ReviewTaskModel,
)


class SqlAlchemyGovernanceGateway:
    def __init__(self, session_factory: sessionmaker, *, settings, secrets) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._secrets = secrets

    def overview(self) -> dict[str, Any]:
        with self._session_factory() as session:
            applications = session.scalars(select(ApplicationModel)).all()
            funnel = Counter(item.current_status for item in applications)
            recent = session.scalars(
                select(ApplicationEventModel)
                .order_by(ApplicationEventModel.created_at.desc())
                .limit(12)
            ).all()
            review_count = session.scalar(
                select(func.count()).select_from(ReviewTaskModel).where(
                    ReviewTaskModel.status == "open"
                )
            ) or 0
            active_improvements = session.scalar(
                select(func.count()).select_from(ImprovementItemModel).where(
                    ImprovementItemModel.status == "active"
                )
            ) or 0
            upcoming_interviews = session.scalar(
                select(func.count()).select_from(InterviewModel).where(
                    InterviewModel.status == "scheduled",
                    InterviewModel.scheduled_at >= datetime.now(UTC),
                )
            ) or 0
            return {
                "generated_at": datetime.now(UTC),
                "funnel": dict(sorted(funnel.items())),
                "total_applications": len(applications),
                "pending_review_count": review_count,
                "active_improvement_count": active_improvements,
                "upcoming_interview_count": upcoming_interviews,
                "recent_changes": [
                    {
                        "id": item.id,
                        "application_id": item.application_id,
                        "event_type": item.event_type,
                        "to_status": item.to_status,
                        "occurred_at": self._utc(item.occurred_at),
                        "note": item.note[:300],
                    }
                    for item in recent
                ],
                "daily_brief": self._brief(applications, recent, days=1),
                "weekly_brief": self._brief(applications, recent, days=7),
            }

    def search(self, *, query: str) -> list[dict[str, Any]]:
        term = query.strip().casefold()
        if len(term) < 2:
            return []
        results: list[dict[str, Any]] = []
        with self._session_factory() as session:
            for item in session.scalars(select(ApplicationModel)).all():
                text = f"{item.company_name_snapshot} {item.job_title_snapshot}".casefold()
                if term in text:
                    results.append(self._search_item("application", item.id, item.job_title_snapshot, item.company_name_snapshot, f"/applications/{item.id}"))
            for item in session.scalars(select(JobPostModel)).all():
                if term in item.title.casefold():
                    results.append(self._search_item("job", item.id, item.title, "岗位", f"/job-posts/{item.id}"))
            for item in session.scalars(select(MaterialDraftModel)).all():
                text = f"{item.company_name_snapshot} {item.job_title_snapshot}".casefold()
                if term in text:
                    results.append(self._search_item("material", item.id, item.job_title_snapshot, item.company_name_snapshot, f"/materials/{item.id}"))
            for item in session.scalars(select(CareerTaskModel)).all():
                if term in f"{item.title} {item.notes}".casefold():
                    results.append(self._search_item("task", item.id, item.title, item.status, "/tasks"))
            for item in session.scalars(select(InterviewModel)).all():
                application = session.get(ApplicationModel, item.application_id)
                text = f"{application.company_name_snapshot} {application.job_title_snapshot}".casefold()
                if term in text:
                    results.append(self._search_item("interview", item.id, application.job_title_snapshot, application.company_name_snapshot, f"/interviews/{item.id}"))
        return results[:100]

    def create_backup_bundle(self) -> dict[str, Any]:
        self._settings.ensure_directories()
        database_copy = backup_database(self._settings, label="full-bundle")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        destination = self._settings.backups_dir / f"career-full-{stamp}.zip"
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "database_revision": database_revision(database_copy),
            "secrets_included": False,
            "files": {},
        }
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            self._write_bundle_file(archive, database_copy, "career.sqlite3", manifest)
            for root, prefix in ((self._settings.blobs_dir, "blobs"), (self._settings.exports_dir, "exports")):
                for path in root.rglob("*"):
                    if path.is_file():
                        self._write_bundle_file(archive, path, f"{prefix}/{path.relative_to(root).as_posix()}", manifest)
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        database_copy.unlink(missing_ok=True)
        return {"path": str(destination), "size_bytes": destination.stat().st_size, "manifest": manifest}

    def export_user_data(self) -> dict[str, Any]:
        self._settings.ensure_directories()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        destination = self._settings.exports_dir / f"career-data-{stamp}.json"
        payload: dict[str, Any] = {"exported_at": datetime.now(UTC).isoformat(), "tables": {}}
        with self._session_factory() as session:
            connection = session.connection()
            for table in Base.metadata.sorted_tables:
                rows = connection.execute(select(table)).mappings().all()
                payload["tables"][table.name] = [
                    {key: self._json_value(value) for key, value in row.items()} for row in rows
                ]
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"path": str(destination), "size_bytes": destination.stat().st_size, "table_count": len(payload["tables"]), "secrets_included": False}

    def garbage_collect(self) -> dict[str, Any]:
        with self._session_factory() as session:
            referenced = {Path(item).as_posix() for item in session.scalars(select(BlobModel.relative_path)).all()}
        removed_files = 0
        removed_bytes = 0
        for path in self._settings.blobs_dir.rglob("*"):
            if path.is_file() and path.relative_to(self._settings.blobs_dir).as_posix() not in referenced:
                removed_bytes += path.stat().st_size
                path.unlink()
                removed_files += 1
        trace_cutoff = datetime.now(UTC) - timedelta(
            days=self._settings.agent_trace_retention_days
        )
        with self._session_factory() as session:
            deleted_traces = session.execute(
                delete(AgentRunModel).where(
                    AgentRunModel.finished_at.is_not(None),
                    AgentRunModel.finished_at < trace_cutoff,
                )
            ).rowcount
            session.commit()
        return {
            "removed_files": removed_files,
            "removed_bytes": removed_bytes,
            "removed_agent_traces": int(deleted_traces or 0),
        }

    def delete_connector_data(self, connector_type: str) -> dict[str, Any]:
        with self._session_factory() as session:
            rows = session.scalars(select(ConnectorConfigModel).where(
                ConnectorConfigModel.connector_type == connector_type
            )).all()
            if connector_type == "imap_readonly":
                self._secrets.delete("imap-account:primary")
            count = len(rows)
            for row in rows:
                session.delete(row)
            session.commit()
        return {"deleted_connectors": count, "connector_type": connector_type}

    def integration_health(self) -> dict[str, Any]:
        """Report cross-module consistency without mutating user data."""
        with self._session_factory() as session:
            applications = session.scalars(select(ApplicationModel)).all()
            events = session.scalars(select(ApplicationEventModel)).all()
            snapshots = session.scalars(select(ApplicationMaterialSnapshotModel)).all()
            interviews = session.scalars(select(InterviewModel)).all()
            tasks = session.scalars(select(CareerTaskModel)).all()
            feedback = session.scalars(select(InterviewFeedbackModel)).all()
            reviews = session.scalars(select(ReviewTaskModel)).all()
            improvements = session.scalars(select(ImprovementItemModel)).all()

        events_by_application = {item.application_id for item in events}
        snapshots_by_application = {item.application_id for item in snapshots}
        event_by_id = {item.id: item for item in events}
        task_keys = {item.source_key for item in tasks if item.source_key}
        open_feedback_reviews = {
            item.entity_id
            for item in reviews
            if item.entity_type == "interview_feedback" and item.status == "open"
        }
        improvement_categories = {item.category for item in improvements}
        issues: list[dict[str, Any]] = []

        def add(code: str, count: int, severity: str, message: str) -> None:
            if count:
                issues.append({
                    "code": code, "count": count, "severity": severity, "message": message,
                })

        add(
            "application_without_timeline",
            sum(item.id not in events_by_application for item in applications),
            "error",
            "申请缺少不可变时间线事件。",
        )
        add(
            "submitted_without_material_snapshot",
            sum(
                item.current_status not in {"discovered", "preparing_materials", "ready_to_apply"}
                and item.id not in snapshots_by_application
                for item in applications
            ),
            "warning",
            "已进入投递后阶段的申请没有实际投递材料快照。",
        )
        add(
            "interview_without_task",
            sum(
                (f"application-event:{item.application_event_id}" if item.application_event_id else f"interview:{item.id}")
                not in task_keys
                for item in interviews
            ),
            "error",
            "面试没有对应的日程任务。",
        )
        add(
            "interview_event_mismatch",
            sum(
                item.application_event_id is not None
                and (
                    item.application_event_id not in event_by_id
                    or event_by_id[item.application_event_id].application_id != item.application_id
                    or event_by_id[item.application_event_id].event_type != "interview_scheduled"
                )
                for item in interviews
            ),
            "error",
            "面试关联了不匹配的申请事件。",
        )
        add(
            "pending_feedback_without_review",
            sum(item.status == "pending" and item.id not in open_feedback_reviews for item in feedback),
            "error",
            "待确认面试反馈没有进入统一审查队列。",
        )
        add(
            "confirmed_feedback_without_improvement",
            sum(
                item.status == "confirmed" and item.category not in improvement_categories
                for item in feedback
            ),
            "error",
            "已确认面试反馈没有沉淀为长期改进项。",
        )
        return {
            "status": "ok" if not issues else "attention",
            "checked_counts": {
                "applications": len(applications),
                "events": len(events),
                "interviews": len(interviews),
                "tasks": len(tasks),
                "feedback": len(feedback),
            },
            "issues": issues,
            "issue_count": sum(item["count"] for item in issues),
        }

    def delete_all_personal_data(self) -> dict[str, Any]:
        backup = self.create_backup_bundle()
        self._secrets.delete("imap-account:primary")
        with self._session_factory() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(delete(table))
            session.commit()
        for root in (self._settings.blobs_dir, self._settings.exports_dir):
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
        return {"deleted": True, "backup_path": backup["path"]}

    @staticmethod
    def _brief(applications, recent, *, days: int) -> dict[str, Any]:
        cutoff = datetime.now(UTC).timestamp() - days * 86400
        changes = [item for item in recent if SqlAlchemyGovernanceGateway._utc(item.created_at).timestamp() >= cutoff]
        return {"period_days": days, "application_count": len(applications), "change_count": len(changes), "summary": f"当前跟踪 {len(applications)} 个申请，最近 {days} 天记录 {len(changes)} 次状态变化。"}

    @staticmethod
    def _search_item(kind, entity_id, title, subtitle, url) -> dict[str, str]:
        return {"type": kind, "id": entity_id, "title": title, "subtitle": subtitle, "url": url}

    @staticmethod
    def _write_bundle_file(archive, path: Path, archive_name: str, manifest: dict[str, Any]) -> None:
        content = path.read_bytes()
        archive.writestr(archive_name, content)
        manifest["files"][archive_name] = {"size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, bytes):
            return value.hex()
        return value

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
