"""SQLAlchemy task, reminder, scheduler, outbox, and dashboard adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from career_console.domain.common.errors import CareerDomainError
from career_console.domain.tasks import (
    ReminderStatus,
    TaskStatus,
    conflict,
    next_schedule_run,
    normalize_due,
    reminder_time,
)
from career_console.infrastructure.database.models import (
    ApplicationEventModel,
    ApplicationModel,
    CareerTaskModel,
    CompanyModel,
    InterviewModel,
    JobPostModel,
    NotificationModel,
    OutboxEventModel,
    ReminderModel,
    ReviewTaskModel,
    ScheduleModel,
)
from career_console.infrastructure.database.profile_gateway import (
    EntityNotFoundError,
    VersionConflictError,
)

_EVENT_TASK_TYPES = {
    "assessment_scheduled": "assessment",
    "written_test_scheduled": "written_test",
    "interview_scheduled": "interview",
}
_TASK_LABELS = {
    "assessment": "完成测评",
    "written_test": "参加笔试",
    "interview": "参加面试",
    "job_deadline": "岗位截止",
}


class SqlAlchemyTaskGateway:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_task(
        self,
        *,
        title: str,
        task_type: str,
        due_at: datetime,
        timezone: str,
        notes: str = "",
        priority: int = 0,
        application_id: str | None = None,
        job_post_id: str | None = None,
        source_key: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            if source_key:
                existing = session.scalar(select(CareerTaskModel).where(
                    CareerTaskModel.source_key == source_key
                ))
                if existing is not None:
                    return self._task_view(session, existing)
            normalized_title = title.strip()
            if not normalized_title:
                raise CareerDomainError("Task title cannot be empty.", code="empty_task_title")
            if application_id is not None:
                application = session.get(ApplicationModel, application_id)
                if application is None:
                    raise EntityNotFoundError("Application was not found.")
                if job_post_id is None:
                    job_post_id = application.job_post_id
            if job_post_id is not None and session.get(JobPostModel, job_post_id) is None:
                raise EntityNotFoundError("Job post was not found.")
            task = CareerTaskModel(
                id=str(uuid4()),
                application_id=application_id,
                job_post_id=job_post_id,
                source_event_id=None,
                source_key=source_key,
                task_type=task_type,
                title=normalized_title[:300],
                notes=notes.strip(),
                status=TaskStatus.PENDING.value,
                priority=priority,
                due_at=normalize_due(due_at, timezone),
                timezone=timezone,
                version=1,
                created_at=now,
                updated_at=now,
                completed_at=None,
                cancelled_at=None,
            )
            session.add(task)
            self._add_outbox(
                session, "task", task.id, "task.created", {"task_id": task.id}, f"task:{task.id}:v1"
            )
            session.commit()
            return self._task_view(session, task)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            self._sync_derived_tasks(session, datetime.now(UTC))
            session.commit()
            tasks = session.scalars(
                select(CareerTaskModel).order_by(
                    CareerTaskModel.status, CareerTaskModel.due_at, CareerTaskModel.priority.desc()
                )
            ).all()
            return self._task_views(session, tasks)

    def update_task(
        self,
        task_id: str,
        *,
        expected_version: int,
        action: str,
        due_at: datetime | None = None,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            task = self._task(session, task_id)
            self._expect_version(task, expected_version)
            if task.status != TaskStatus.PENDING.value:
                raise CareerDomainError(
                    "Only pending tasks can be changed.", code="task_not_pending"
                )
            if action == "complete":
                task.status = TaskStatus.COMPLETED.value
                task.completed_at = now
                self._cancel_active_reminders(session, task.id, now)
            elif action == "cancel":
                task.status = TaskStatus.CANCELLED.value
                task.cancelled_at = now
                self._cancel_active_reminders(session, task.id, now)
            elif action == "postpone":
                if due_at is None:
                    raise CareerDomainError(
                        "Postpone requires a new due time.", code="postpone_due_required"
                    )
                task.timezone = timezone or task.timezone
                task.due_at = normalize_due(due_at, task.timezone)
                reminders = session.scalars(
                    select(ReminderModel).where(
                        ReminderModel.task_id == task.id,
                        ReminderModel.status == ReminderStatus.ACTIVE.value,
                    )
                ).all()
                for reminder in reminders:
                    reminder.scheduled_for = reminder_time(task.due_at, reminder.offset_minutes)
                    reminder.version += 1
                    reminder.updated_at = now
                    schedule = session.scalar(
                        select(ScheduleModel).where(ScheduleModel.reminder_id == reminder.id)
                    )
                    schedule.next_run_at = reminder.scheduled_for
                    schedule.version += 1
                    schedule.updated_at = now
            else:
                raise CareerDomainError("Unknown task action.", code="invalid_task_action")
            task.version += 1
            task.updated_at = now
            self._add_outbox(
                session,
                "task",
                task.id,
                f"task.{action}",
                {"task_id": task.id},
                f"task:{task.id}:v{task.version}",
            )
            session.commit()
            return self._task_view(session, task)

    def create_reminder(self, task_id: str, *, offset_minutes: int) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            task = self._task(session, task_id)
            if task.status != TaskStatus.PENDING.value:
                raise CareerDomainError(
                    "Reminders require a pending task.", code="reminder_task_not_pending"
                )
            existing = session.scalar(
                select(ReminderModel).where(
                    ReminderModel.task_id == task.id,
                    ReminderModel.offset_minutes == offset_minutes,
                    ReminderModel.status == ReminderStatus.ACTIVE.value,
                )
            )
            if existing is not None:
                return self._reminder_view(existing)
            generation = (
                session.scalar(
                    select(func.max(ReminderModel.generation)).where(
                        ReminderModel.task_id == task.id,
                        ReminderModel.offset_minutes == offset_minutes,
                    )
                )
                or 0
            ) + 1
            scheduled_for = reminder_time(task.due_at, offset_minutes)
            reminder = ReminderModel(
                id=str(uuid4()),
                task_id=task.id,
                offset_minutes=offset_minutes,
                generation=generation,
                scheduled_for=scheduled_for,
                status=ReminderStatus.ACTIVE.value,
                version=1,
                created_at=now,
                updated_at=now,
                triggered_at=None,
            )
            session.add(reminder)
            session.flush()
            session.add(
                ScheduleModel(
                    id=str(uuid4()),
                    reminder_id=reminder.id,
                    schedule_type="once",
                    handler_type="reminder.trigger",
                    payload_json=json.dumps({"reminder_id": reminder.id}, separators=(",", ":")),
                    timezone=task.timezone,
                    next_run_at=scheduled_for,
                    interval_seconds=None,
                    cron_expression=None,
                    status="active",
                    version=1,
                    last_run_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
            return self._reminder_view(reminder)

    def create_schedule(
        self,
        *,
        schedule_type: str,
        handler_type: str,
        payload: dict[str, Any],
        next_run_at: datetime,
        timezone: str,
        interval_seconds: int | None = None,
        cron_expression: str | None = None,
    ) -> str:
        now = datetime.now(UTC)
        normalized = normalize_due(next_run_at, timezone)
        if schedule_type != "once":
            next_schedule_run(
                schedule_type,
                normalized,
                interval_seconds=interval_seconds,
                cron_expression=cron_expression,
                timezone=timezone,
            )
        with self._session_factory() as session:
            schedule = ScheduleModel(
                id=str(uuid4()),
                reminder_id=None,
                schedule_type=schedule_type,
                handler_type=handler_type,
                payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                timezone=timezone,
                next_run_at=normalized,
                interval_seconds=interval_seconds,
                cron_expression=cron_expression,
                status="active",
                version=1,
                last_run_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(schedule)
            session.commit()
            return schedule.id

    def run_due(self, *, now: datetime | None = None) -> dict[str, int]:
        now = self._aware(now or datetime.now(UTC))
        with self._session_factory() as session:
            self._sync_derived_tasks(session, now)
            recovered = (
                session.execute(
                    update(OutboxEventModel)
                    .where(
                        OutboxEventModel.status == "processing",
                        OutboxEventModel.lease_expires_at.is_not(None),
                        OutboxEventModel.lease_expires_at < now,
                    )
                    .values(
                        status="pending",
                        lease_owner=None,
                        lease_expires_at=None,
                        next_attempt_at=now,
                    )
                ).rowcount
                or 0
            )
            schedules = session.scalars(
                select(ScheduleModel).where(
                    ScheduleModel.status == "active", ScheduleModel.next_run_at <= now
                )
            ).all()
            triggered = 0
            for schedule in schedules:
                if schedule.reminder_id is not None:
                    reminder = session.get(ReminderModel, schedule.reminder_id)
                    task = session.get(CareerTaskModel, reminder.task_id)
                    if reminder.status != ReminderStatus.ACTIVE.value:
                        schedule.status = "completed"
                    elif task.status != TaskStatus.PENDING.value:
                        reminder.status = ReminderStatus.CANCELLED.value
                        reminder.updated_at = now
                        schedule.status = "cancelled"
                    else:
                        reminder.status = ReminderStatus.TRIGGERED.value
                        reminder.triggered_at = now
                        reminder.updated_at = now
                        reminder.version += 1
                        self._add_outbox(
                            session,
                            "reminder",
                            reminder.id,
                            "reminder.triggered",
                            {"reminder_id": reminder.id, "task_id": task.id},
                            f"reminder:{reminder.id}:trigger",
                        )
                        schedule.status = "completed"
                        triggered += 1
                else:
                    self._add_outbox(
                        session,
                        "schedule",
                        schedule.id,
                        schedule.handler_type,
                        json.loads(schedule.payload_json),
                        f"schedule:{schedule.id}:v{schedule.version}",
                    )
                    next_run = next_schedule_run(
                        schedule.schedule_type,
                        self._aware(schedule.next_run_at),
                        interval_seconds=schedule.interval_seconds,
                        cron_expression=schedule.cron_expression,
                        timezone=schedule.timezone,
                    )
                    if next_run is None:
                        schedule.status = "completed"
                    else:
                        while next_run <= now:
                            next_run = next_schedule_run(
                                schedule.schedule_type,
                                next_run,
                                interval_seconds=schedule.interval_seconds,
                                cron_expression=schedule.cron_expression,
                                timezone=schedule.timezone,
                            )
                        schedule.next_run_at = next_run
                        schedule.version += 1
                schedule.last_run_at = now
                schedule.updated_at = now
            session.flush()
            dispatched = self._dispatch_outbox(session, now)
            session.commit()
            return {
                "schedules_processed": len(schedules),
                "reminders_triggered": triggered,
                "outbox_dispatched": dispatched,
                "leases_recovered": int(recovered),
            }

    def dashboard(
        self, *, now: datetime | None = None, timezone: str = "Asia/Shanghai"
    ) -> dict[str, Any]:
        now = self._aware(now or datetime.now(UTC))
        zone = ZoneInfo(timezone)
        with self._session_factory() as session:
            self._sync_derived_tasks(session, now)
            session.commit()
            tasks = session.scalars(
                select(CareerTaskModel).where(CareerTaskModel.status == TaskStatus.PENDING.value)
            ).all()
            views = self._task_views(session, tasks)
            local_today = now.astimezone(zone).date()
            today = [
                item for item in views if item["due_at"].astimezone(zone).date() == local_today
            ]
            overdue = [item for item in views if item["due_at"] < now]
            upcoming = [item for item in views if now <= item["due_at"] <= now + timedelta(days=7)]
            interviews = [
                item
                for item in upcoming
                if item["task_type"] in {"assessment", "written_test", "interview"}
            ]
            review_count = (
                session.scalar(
                    select(func.count(ReviewTaskModel.id)).where(ReviewTaskModel.status == "open")
                )
                or 0
            )
            unread = (
                session.scalar(
                    select(func.count(NotificationModel.id)).where(
                        NotificationModel.status == "unread"
                    )
                )
                or 0
            )
            return {
                "generated_at": now,
                "timezone": timezone,
                "today": today,
                "overdue": overdue,
                "upcoming": upcoming,
                "interviews": interviews,
                "pending_review_count": review_count,
                "unread_notification_count": unread,
                "conflict_count": sum(len(item["conflict_ids"]) for item in views) // 2,
            }

    def list_notifications(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(NotificationModel).order_by(NotificationModel.created_at.desc())
            ).all()
            return [self._notification_view(item) for item in rows]

    def read_notification(self, notification_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            item = session.get(NotificationModel, notification_id)
            if item is None:
                raise EntityNotFoundError("Notification was not found.")
            if item.status != "read":
                item.status = "read"
                item.read_at = datetime.now(UTC)
                session.commit()
            return self._notification_view(item)

    def recent_change_refs(self, *, limit: int = 20) -> list[dict[str, str]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(OutboxEventModel)
                .order_by(OutboxEventModel.created_at.desc())
                .limit(max(1, min(limit, 100)))
            ).all()
            return [
                {
                    "id": item.id,
                    "event_type": item.event_type,
                    "aggregate_type": item.aggregate_type,
                    "aggregate_id": item.aggregate_id,
                }
                for item in rows
            ]

    def _sync_derived_tasks(self, session: Session, now: datetime) -> None:
        events = session.scalars(
            select(ApplicationEventModel).where(
                ApplicationEventModel.event_type.in_([*_EVENT_TASK_TYPES, "event_corrected"])
            )
        ).all()
        corrections = {
            item.supersedes_event_id: item
            for item in events
            if item.event_type == "event_corrected" and item.supersedes_event_id
        }
        for event in events:
            if event.event_type not in _EVENT_TASK_TYPES:
                continue
            effective = corrections.get(event.id, event)
            application = session.get(ApplicationModel, event.application_id)
            interview = session.scalar(
                select(InterviewModel).where(InterviewModel.application_event_id == event.id)
            )
            effective_due = interview.scheduled_at if interview is not None else effective.occurred_at
            task_type = _EVENT_TASK_TYPES[event.event_type]
            source_key = f"application-event:{event.id}"
            task = session.scalar(
                select(CareerTaskModel).where(CareerTaskModel.source_key == source_key)
            )
            if task is None:
                task = CareerTaskModel(
                    id=str(uuid4()),
                    application_id=application.id,
                    job_post_id=application.job_post_id,
                    source_event_id=event.id,
                    source_key=source_key,
                    task_type=task_type,
                    title=f"{_TASK_LABELS[task_type]} · {application.company_name_snapshot}",
                    notes=effective.note,
                    status=(
                        interview.status
                        if interview is not None and interview.status in {"completed", "cancelled"}
                        else TaskStatus.PENDING.value
                    ),
                    priority=10,
                    due_at=self._aware(effective_due),
                    timezone="Asia/Shanghai",
                    version=1,
                    created_at=now,
                    updated_at=now,
                    completed_at=now if interview is not None and interview.status == "completed" else None,
                    cancelled_at=now if interview is not None and interview.status == "cancelled" else None,
                )
                session.add(task)
            elif task.status == TaskStatus.PENDING.value and (
                task.due_at != effective_due or task.notes != effective.note
            ):
                task.due_at = self._aware(effective_due)
                task.notes = effective.note
                task.version += 1
                task.updated_at = now
                for reminder in session.scalars(
                    select(ReminderModel).where(
                        ReminderModel.task_id == task.id,
                        ReminderModel.status == ReminderStatus.ACTIVE.value,
                    )
                ).all():
                    reminder.scheduled_for = reminder_time(task.due_at, reminder.offset_minutes)
                    reminder.version += 1
                    reminder.updated_at = now
                    schedule = session.scalar(
                        select(ScheduleModel).where(ScheduleModel.reminder_id == reminder.id)
                    )
                    if schedule is not None:
                        schedule.next_run_at = reminder.scheduled_for
                        schedule.version += 1
                        schedule.updated_at = now
            if (
                interview is not None
                and task.status == TaskStatus.PENDING.value
                and interview.status in {"completed", "cancelled"}
            ):
                task.status = interview.status
                task.completed_at = now if interview.status == "completed" else None
                task.cancelled_at = now if interview.status == "cancelled" else None
                task.version += 1
                task.updated_at = now
                self._cancel_active_reminders(session, task.id, now)
        posts = session.scalars(
            select(JobPostModel).where(
                JobPostModel.deadline_at.is_not(None), JobPostModel.status == "active"
            )
        ).all()
        for post in posts:
            source_key = f"job-deadline:{post.id}"
            if session.scalar(
                select(CareerTaskModel.id).where(CareerTaskModel.source_key == source_key)
            ):
                continue
            company = session.get(CompanyModel, post.company_id)
            session.add(
                CareerTaskModel(
                    id=str(uuid4()),
                    application_id=None,
                    job_post_id=post.id,
                    source_event_id=None,
                    source_key=source_key,
                    task_type="job_deadline",
                    title=f"岗位截止 · {company.canonical_name} · {post.title}",
                    notes="",
                    status=TaskStatus.PENDING.value,
                    priority=5,
                    due_at=self._aware(post.deadline_at),
                    timezone="Asia/Shanghai",
                    version=1,
                    created_at=now,
                    updated_at=now,
                    completed_at=None,
                    cancelled_at=None,
                )
            )

    def _dispatch_outbox(self, session: Session, now: datetime) -> int:
        events = session.scalars(
            select(OutboxEventModel).where(
                OutboxEventModel.status.in_(["pending", "failed"]),
                OutboxEventModel.next_attempt_at <= now,
            )
        ).all()
        dispatched = 0
        for event in events:
            event.status = "processing"
            event.attempt_count += 1
            event.lease_owner = "local-outbox"
            event.lease_expires_at = now + timedelta(seconds=60)
            if event.event_type == "reminder.triggered":
                payload = json.loads(event.payload_json)
                reminder = session.get(ReminderModel, payload["reminder_id"])
                task = session.get(CareerTaskModel, reminder.task_id)
                existing = session.scalar(
                    select(NotificationModel).where(NotificationModel.reminder_id == reminder.id)
                )
                if existing is None:
                    session.add(
                        NotificationModel(
                            id=str(uuid4()),
                            reminder_id=reminder.id,
                            notification_type="in_app",
                            title=task.title,
                            body=f"任务将在 {reminder.offset_minutes} 分钟后到期。",
                            status="unread",
                            created_at=now,
                            read_at=None,
                        )
                    )
            event.status = "dispatched"
            event.dispatched_at = now
            event.lease_owner = None
            event.lease_expires_at = None
            dispatched += 1
        return dispatched

    @staticmethod
    def _add_outbox(
        session: Session,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        dedupe_key: str,
    ) -> OutboxEventModel:
        existing = session.scalar(
            select(OutboxEventModel).where(OutboxEventModel.dedupe_key == dedupe_key)
        )
        if existing is not None:
            return existing
        now = datetime.now(UTC)
        item = OutboxEventModel(
            id=str(uuid4()),
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            dedupe_key=dedupe_key,
            status="pending",
            attempt_count=0,
            next_attempt_at=now,
            lease_owner=None,
            lease_expires_at=None,
            last_error_code=None,
            created_at=now,
            dispatched_at=None,
        )
        session.add(item)
        return item

    @staticmethod
    def _cancel_active_reminders(session: Session, task_id: str, now: datetime) -> None:
        reminders = session.scalars(
            select(ReminderModel).where(
                ReminderModel.task_id == task_id,
                ReminderModel.status == ReminderStatus.ACTIVE.value,
            )
        ).all()
        for reminder in reminders:
            reminder.status = ReminderStatus.CANCELLED.value
            reminder.updated_at = now
            schedule = session.scalar(
                select(ScheduleModel).where(ScheduleModel.reminder_id == reminder.id)
            )
            schedule.status = "cancelled"
            schedule.updated_at = now

    def _task_views(self, session: Session, tasks: list[CareerTaskModel]) -> list[dict[str, Any]]:
        views = [self._task_view(session, item) for item in tasks]
        pending = [item for item in tasks if item.status == TaskStatus.PENDING.value]
        conflicts: dict[str, list[str]] = {item.id: [] for item in tasks}
        scheduled_types = {"assessment", "written_test", "interview"}
        for index, left in enumerate(pending):
            for right in pending[index + 1 :]:
                if (
                    left.task_type in scheduled_types
                    and right.task_type in scheduled_types
                    and conflict(left.due_at, right.due_at)
                ):
                    conflicts[left.id].append(right.id)
                    conflicts[right.id].append(left.id)
        for view in views:
            view["conflict_ids"] = conflicts[view["id"]]
        return views

    def _task_view(self, session: Session, task: CareerTaskModel) -> dict[str, Any]:
        application = (
            session.get(ApplicationModel, task.application_id) if task.application_id else None
        )
        post = session.get(JobPostModel, task.job_post_id) if task.job_post_id else None
        company = session.get(CompanyModel, post.company_id) if post else None
        reminders = session.scalars(
            select(ReminderModel)
            .where(ReminderModel.task_id == task.id)
            .order_by(ReminderModel.offset_minutes.desc(), ReminderModel.generation.desc())
        ).all()
        return {
            "id": task.id,
            "application_id": task.application_id,
            "job_post_id": task.job_post_id,
            "source_event_id": task.source_event_id,
            "task_type": task.task_type,
            "title": task.title,
            "notes": task.notes,
            "status": task.status,
            "priority": task.priority,
            "due_at": self._utc(task.due_at),
            "timezone": task.timezone,
            "version": task.version,
            "created_at": self._utc(task.created_at),
            "updated_at": self._utc(task.updated_at),
            "completed_at": self._utc(task.completed_at),
            "cancelled_at": self._utc(task.cancelled_at),
            "company": application.company_name_snapshot
            if application
            else (company.canonical_name if company else None),
            "job_title": application.job_title_snapshot
            if application
            else (post.title if post else None),
            "reminders": [self._reminder_view(item) for item in reminders],
            "conflict_ids": [],
        }

    def _reminder_view(self, item: ReminderModel) -> dict[str, Any]:
        return {
            "id": item.id,
            "task_id": item.task_id,
            "offset_minutes": item.offset_minutes,
            "generation": item.generation,
            "scheduled_for": self._utc(item.scheduled_for),
            "status": item.status,
            "version": item.version,
            "created_at": self._utc(item.created_at),
            "updated_at": self._utc(item.updated_at),
            "triggered_at": self._utc(item.triggered_at),
        }

    def _notification_view(self, item: NotificationModel) -> dict[str, Any]:
        return {
            "id": item.id,
            "reminder_id": item.reminder_id,
            "notification_type": item.notification_type,
            "title": item.title,
            "body": item.body,
            "status": item.status,
            "created_at": self._utc(item.created_at),
            "read_at": self._utc(item.read_at),
        }

    @staticmethod
    def _task(session: Session, task_id: str) -> CareerTaskModel:
        task = session.get(CareerTaskModel, task_id)
        if task is None:
            raise EntityNotFoundError("Task was not found.")
        return task

    @staticmethod
    def _expect_version(task: CareerTaskModel, expected_version: int) -> None:
        if task.version != expected_version:
            raise VersionConflictError("Task changed after it was loaded.")

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
