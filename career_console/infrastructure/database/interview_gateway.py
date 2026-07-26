"""SQLAlchemy adapter for interview preparation and confirmed feedback."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from career_console.domain.common.errors import CareerDomainError
from career_console.domain.interviews import question_category
from career_console.infrastructure.database.models import (
    ApplicationEventModel,
    ApplicationMaterialSnapshotModel,
    ApplicationModel,
    CandidateFactModel,
    CareerTaskModel,
    CompanyModel,
    ImprovementItemModel,
    InterviewFeedbackModel,
    InterviewModel,
    InterviewPreparationPackModel,
    InterviewQuestionModel,
    InterviewRecordModel,
    JobPostModel,
    JobPostVersionModel,
    JobRequirementModel,
    ReminderModel,
    ReviewTaskModel,
    ScheduleModel,
)
from career_console.infrastructure.database.profile_gateway import (
    EntityNotFoundError,
    VersionConflictError,
)
from career_console.infrastructure.database.review_runtime import (
    ensure_review_task,
    set_review_resolution,
)

_ROUND_QUESTIONS = {
    "phone": ["请简要介绍与岗位最相关的经历。", "为什么选择这个岗位和公司？"],
    "technical": ["请解释一个最能体现技术深度的项目决策。", "遇到技术故障时如何定位和验证？"],
    "case": ["面对信息不完整的问题，你会如何拆解并验证假设？", "如何权衡方案的收益、成本和风险？"],
    "final": ["你希望在这个岗位创造什么长期价值？", "你如何处理跨团队分歧和高压决策？"],
}


class SqlAlchemyInterviewGateway:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_interviews(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(InterviewModel).order_by(InterviewModel.scheduled_at.desc())
            ).all()
            return [self._view(session, row) for row in rows]

    def get_interview(self, interview_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            return self._view(session, self._interview(session, interview_id))

    def create_interview(self, **values: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            application = session.get(ApplicationModel, values["application_id"])
            if application is None:
                raise EntityNotFoundError("Application was not found.")
            event = self._resolve_application_event(
                session, application.id, values.get("application_event_id")
            )
            row = InterviewModel(
                id=str(uuid4()),
                application_id=application.id,
                application_event_id=event.id if event else None,
                round_type=values["round_type"],
                scheduled_at=self._aware(values["scheduled_at"]),
                timezone=values.get("timezone") or "Asia/Shanghai",
                status="scheduled",
                version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            self._ensure_task(session, row, application, now)
            session.commit()
            return self._view(session, row)

    def reschedule_interview(self, interview_id: str, **values: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            interview = self._interview(session, interview_id)
            self._expect_version(interview, values["expected_version"])
            if interview.status != "scheduled":
                raise CareerDomainError(
                    "Only a scheduled interview can be rescheduled.",
                    code="interview_not_scheduled",
                )
            interview.scheduled_at = self._aware(values["scheduled_at"])
            interview.timezone = values.get("timezone") or interview.timezone
            interview.version += 1
            interview.updated_at = now
            application = session.get(ApplicationModel, interview.application_id)
            task = self._ensure_task(session, interview, application, now)
            task.due_at = interview.scheduled_at
            task.timezone = interview.timezone
            task.version += 1
            task.updated_at = now
            self._reschedule_reminders(session, task, now)
            session.commit()
            return self._view(session, interview)

    def cancel_interview(self, interview_id: str, **values: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            interview = self._interview(session, interview_id)
            self._expect_version(interview, values["expected_version"])
            if interview.status != "scheduled":
                raise CareerDomainError(
                    "Only a scheduled interview can be cancelled.",
                    code="interview_not_scheduled",
                )
            interview.status = "cancelled"
            interview.version += 1
            interview.updated_at = now
            application = session.get(ApplicationModel, interview.application_id)
            task = self._ensure_task(session, interview, application, now)
            task.status = "cancelled"
            task.notes = values["reason"].strip()
            task.cancelled_at = now
            task.version += 1
            task.updated_at = now
            self._cancel_reminders(session, task.id, now)
            session.commit()
            return self._view(session, interview)

    def generate_preparation(self, interview_id: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            interview = self._interview(session, interview_id)
            if interview.status == "cancelled":
                raise CareerDomainError(
                    "A cancelled interview cannot generate a new preparation pack.",
                    code="interview_cancelled",
                )
            application = session.get(ApplicationModel, interview.application_id)
            job_version = session.get(JobPostVersionModel, application.job_post_version_id)
            snapshots = session.scalars(
                select(ApplicationMaterialSnapshotModel).where(
                    ApplicationMaterialSnapshotModel.application_id == application.id
                )
            ).all()
            if not snapshots:
                raise CareerDomainError(
                    "Interview preparation requires the materials actually submitted.",
                    code="interview_submission_snapshot_required",
                )
            facts = session.scalars(
                select(CandidateFactModel)
                .where(CandidateFactModel.status == "confirmed")
                .order_by(CandidateFactModel.category, CandidateFactModel.created_at)
            ).all()
            requirements = session.scalars(
                select(JobRequirementModel)
                .where(JobRequirementModel.job_post_version_id == job_version.id)
                .order_by(JobRequirementModel.weight.desc(), JobRequirementModel.ordinal)
                .limit(12)
            ).all()
            improvements = session.scalars(
                select(ImprovementItemModel)
                .where(ImprovementItemModel.status == "active")
                .order_by(
                    ImprovementItemModel.occurrence_count.desc(),
                    ImprovementItemModel.updated_at.desc(),
                )
                .limit(10)
            ).all()
            latest_version = session.scalar(
                select(func.max(InterviewPreparationPackModel.version_number)).where(
                    InterviewPreparationPackModel.interview_id == interview.id
                )
            )
            content = self._preparation_content(
                session, interview, application, snapshots, facts, requirements, improvements
            )
            pack = InterviewPreparationPackModel(
                id=str(uuid4()),
                interview_id=interview.id,
                version_number=int(latest_version or 0) + 1,
                job_post_version_id=job_version.id,
                material_snapshot_ids_json=json.dumps([item.id for item in snapshots]),
                confirmed_fact_ids_json=json.dumps([item.id for item in facts]),
                prior_improvement_ids_json=json.dumps([item.id for item in improvements]),
                content_json=json.dumps(content, ensure_ascii=False, separators=(",", ":")),
                created_at=now,
            )
            session.add(pack)
            session.commit()
            return self._pack_view(pack)

    def save_record(self, interview_id: str, **values: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            interview = self._interview(session, interview_id)
            existing = session.scalar(
                select(InterviewRecordModel).where(InterviewRecordModel.interview_id == interview.id)
            )
            if existing is not None:
                return self._record_view(session, existing)
            if interview.status == "cancelled":
                raise CareerDomainError(
                    "A cancelled interview cannot be recorded.", code="interview_cancelled"
                )
            record = InterviewRecordModel(
                id=str(uuid4()),
                interview_id=interview.id,
                occurred_at=self._aware(values["occurred_at"]),
                overall_summary=values["overall_summary"].strip(),
                self_rating=int(values["self_rating"]),
                result=values["result"],
                version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            for ordinal, item in enumerate(values["questions"], start=1):
                rating = item.get("self_rating")
                question = InterviewQuestionModel(
                    id=str(uuid4()),
                    record_id=record.id,
                    question_text=item["question_text"].strip(),
                    answer_summary=item["answer_summary"].strip(),
                    category=question_category(item["question_text"]),
                    self_rating=rating,
                    ordinal=ordinal,
                )
                session.add(question)
                if rating is not None and int(rating) <= 3:
                    self._add_feedback(session, record, question, now)
            if record.self_rating <= 3:
                self._add_summary_feedback(session, record, now)
            interview.status = "completed"
            interview.version += 1
            interview.updated_at = now
            application = session.get(ApplicationModel, interview.application_id)
            task = self._ensure_task(session, interview, application, now)
            if task.status == "pending":
                task.status = "completed"
                task.completed_at = now
                task.version += 1
                task.updated_at = now
                self._cancel_reminders(session, task.id, now)
            session.commit()
            return self._record_view(session, record)

    def list_feedback(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(InterviewFeedbackModel).order_by(InterviewFeedbackModel.created_at.desc())
            ).all()
            return [self._feedback_view(session, row) for row in rows]

    def resolve_feedback(self, feedback_id: str, **values: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            feedback = session.get(InterviewFeedbackModel, feedback_id)
            if feedback is None:
                raise EntityNotFoundError("Interview feedback was not found.")
            if feedback.version != int(values["expected_version"]):
                raise VersionConflictError("Interview feedback changed after it was loaded.")
            if feedback.status != "pending":
                return self._feedback_view(session, feedback)
            feedback.status = values["resolution"]
            feedback.version += 1
            feedback.resolved_at = now
            task = session.scalar(
                select(ReviewTaskModel).where(
                    ReviewTaskModel.entity_type == "interview_feedback",
                    ReviewTaskModel.entity_id == feedback.id,
                )
            )
            if task is not None:
                set_review_resolution(
                    task,
                    now=now,
                    resolution=values["resolution"],
                    reason=values["reason"],
                )
            if values["resolution"] == "confirmed":
                existing = session.scalar(
                    select(ImprovementItemModel).where(
                        ImprovementItemModel.feedback_id == feedback.id
                    )
                )
                if existing is None:
                    title = self._improvement_title(feedback.category)
                    aggregate = session.scalar(
                        select(ImprovementItemModel).where(
                            ImprovementItemModel.category == feedback.category,
                            ImprovementItemModel.title == title,
                            ImprovementItemModel.status == "active",
                        ).order_by(ImprovementItemModel.updated_at.desc())
                    )
                    if aggregate is not None:
                        aggregate.occurrence_count += 1
                        aggregate.description = feedback.description
                        aggregate.updated_at = now
                    else:
                        session.add(ImprovementItemModel(
                            id=str(uuid4()),
                            feedback_id=feedback.id,
                            category=feedback.category,
                            title=title,
                            description=feedback.description,
                            status="active",
                            occurrence_count=1,
                            created_at=now,
                            updated_at=now,
                        ))
            session.commit()
            return self._feedback_view(session, feedback)

    def list_improvements(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ImprovementItemModel).order_by(ImprovementItemModel.updated_at.desc())
            ).all()
            return [self._improvement_view(row) for row in rows]

    def update_improvement(self, improvement_id: str, **values: Any) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.get(ImprovementItemModel, improvement_id)
            if row is None:
                raise EntityNotFoundError("Improvement item was not found.")
            row.status = values["status"]
            row.updated_at = datetime.now(UTC)
            session.commit()
            return self._improvement_view(row)

    def _preparation_content(
        self, session, interview, application, snapshots, facts, requirements, improvements
    ) -> dict[str, Any]:
        job = session.get(JobPostModel, application.job_post_id)
        company = session.get(CompanyModel, job.company_id)
        source_text = "\n".join([item.rendered_text for item in snapshots] + [f.value for f in facts])
        gaps = [
            {
                "requirement_id": item.id,
                "requirement": item.description,
                "bridge": "如实说明当前证据边界，并用相邻经验、学习计划和验证步骤回答。",
            }
            for item in requirements
            if not any(keyword.casefold() in source_text.casefold() for keyword in json.loads(item.keywords_json))
        ][:6]
        return {
            "company": company.canonical_name,
            "job_title": job.title,
            "round_type": interview.round_type,
            "requirements": [
                {"id": item.id, "description": item.description, "level": item.level}
                for item in requirements
            ],
            "submitted_materials": [
                {
                    "id": item.id,
                    "title": item.title,
                    "content_hash": item.content_hash,
                    "evidence_excerpt": item.rendered_text[:2_000],
                }
                for item in snapshots
            ],
            "confirmed_facts": [
                {"id": item.id, "category": item.category, "field_key": item.field_key, "value": item.value}
                for item in facts
            ],
            "star_prompts": [
                {"fact_id": item.id, "prompt": f"围绕这条已确认事实准备 STAR 证据：{item.value[:300]}"}
                for item in facts
                if item.category in {"project", "work", "internship"}
            ][:8],
            "gap_bridges": gaps,
            "questions": _ROUND_QUESTIONS[interview.round_type]
            + [f"请结合真实经历说明：{item.description}" for item in requirements[:4]],
            "candidate_questions": ["该岗位入职前三个月最重要的成功标准是什么？", "团队当前最希望解决的业务或技术问题是什么？"],
            "historical_improvements": [
                {"id": item.id, "category": item.category, "title": item.title, "description": item.description}
                for item in improvements
            ],
            "checklist": ["核对面试时间和方式", "复习实际投递材料", "准备可验证的 STAR 证据", "明确不知道时的诚实回答边界"],
        }

    def _add_feedback(self, session, record, question, now) -> None:
        feedback = InterviewFeedbackModel(
            id=str(uuid4()), record_id=record.id, category=question.category,
            description=f"加强“{question.question_text[:120]}”的结构化回答和证据。",
            evidence_text=question.answer_summary[:1_000], status="pending", version=1,
            created_at=now, resolved_at=None,
        )
        session.add(feedback)
        session.flush()
        self._add_review_task(session, feedback.id, now)

    def _add_summary_feedback(self, session, record, now) -> None:
        feedback = InterviewFeedbackModel(
            id=str(uuid4()), record_id=record.id, category="overall",
            description="根据本轮自评补强整体表达、证据完整性和回答节奏。",
            evidence_text=record.overall_summary[:1_000], status="pending", version=1,
            created_at=now, resolved_at=None,
        )
        session.add(feedback)
        session.flush()
        self._add_review_task(session, feedback.id, now)

    @staticmethod
    def _add_review_task(session, feedback_id: str, now: datetime) -> None:
        feedback = session.get(InterviewFeedbackModel, feedback_id)
        ensure_review_task(
            session,
            task_type="interview_feedback",
            entity_type="interview_feedback",
            entity_id=feedback_id,
            title="确认面试改进建议",
            summary=feedback.description if feedback else "面试反馈待确认",
            source_type="interview_record",
            priority=20,
            now=now,
        )

    def _view(self, session: Session, interview: InterviewModel) -> dict[str, Any]:
        application = session.get(ApplicationModel, interview.application_id)
        pack = session.scalar(select(InterviewPreparationPackModel).where(
            InterviewPreparationPackModel.interview_id == interview.id
        ).order_by(InterviewPreparationPackModel.version_number.desc()))
        record = session.scalar(select(InterviewRecordModel).where(
            InterviewRecordModel.interview_id == interview.id
        ))
        task = session.scalar(
            select(CareerTaskModel).where(
                CareerTaskModel.source_key == self._task_source_key(interview)
            )
        )
        return {
            "id": interview.id, "application_id": interview.application_id,
            "application_event_id": interview.application_event_id,
            "task_id": task.id if task else None,
            "job_title": application.job_title_snapshot, "company": application.company_name_snapshot,
            "round_type": interview.round_type, "scheduled_at": self._utc(interview.scheduled_at),
            "timezone": interview.timezone, "status": interview.status, "version": interview.version,
            "preparation": self._pack_view(pack) if pack else None,
            "record": self._record_view(session, record) if record else None,
            "created_at": self._utc(interview.created_at), "updated_at": self._utc(interview.updated_at),
        }

    def _record_view(self, session: Session, record: InterviewRecordModel) -> dict[str, Any]:
        questions = session.scalars(select(InterviewQuestionModel).where(
            InterviewQuestionModel.record_id == record.id
        ).order_by(InterviewQuestionModel.ordinal)).all()
        feedback = session.scalars(select(InterviewFeedbackModel).where(
            InterviewFeedbackModel.record_id == record.id
        ).order_by(InterviewFeedbackModel.created_at)).all()
        return {
            "id": record.id, "occurred_at": self._utc(record.occurred_at),
            "overall_summary": record.overall_summary, "self_rating": record.self_rating,
            "result": record.result, "version": record.version,
            "questions": [{"id": item.id, "question_text": item.question_text,
                "answer_summary": item.answer_summary, "category": item.category,
                "self_rating": item.self_rating, "ordinal": item.ordinal} for item in questions],
            "feedback": [self._feedback_view(session, item) for item in feedback],
        }

    def _feedback_view(self, session: Session, row: InterviewFeedbackModel) -> dict[str, Any]:
        task = session.scalar(select(ReviewTaskModel).where(
            ReviewTaskModel.entity_type == "interview_feedback", ReviewTaskModel.entity_id == row.id
        ))
        return {"id": row.id, "record_id": row.record_id, "category": row.category,
            "description": row.description, "evidence_text": row.evidence_text,
            "status": row.status, "version": row.version,
            "task_id": task.id if task else None, "created_at": self._utc(row.created_at),
            "resolved_at": self._utc(row.resolved_at)}

    @classmethod
    def _pack_view(cls, row: InterviewPreparationPackModel) -> dict[str, Any]:
        return {"id": row.id, "version_number": row.version_number,
            "job_post_version_id": row.job_post_version_id,
            "material_snapshot_ids": json.loads(row.material_snapshot_ids_json),
            "confirmed_fact_ids": json.loads(row.confirmed_fact_ids_json),
            "prior_improvement_ids": json.loads(row.prior_improvement_ids_json),
            "content": json.loads(row.content_json), "created_at": cls._utc(row.created_at)}

    @classmethod
    def _improvement_view(cls, row: ImprovementItemModel) -> dict[str, Any]:
        return {"id": row.id, "feedback_id": row.feedback_id, "category": row.category,
            "title": row.title, "description": row.description, "status": row.status,
            "occurrence_count": row.occurrence_count, "created_at": cls._utc(row.created_at),
            "updated_at": cls._utc(row.updated_at)}

    @staticmethod
    def _improvement_title(category: str) -> str:
        return {"technical": "补强技术回答", "behavioral": "补强 STAR 证据",
                "case": "加强案例拆解", "motivation": "澄清求职动机",
                "overall": "改善整体面试表现"}.get(category, "补强面试回答")

    def _resolve_application_event(
        self, session: Session, application_id: str, event_id: str | None
    ) -> ApplicationEventModel | None:
        if event_id:
            event = session.get(ApplicationEventModel, event_id)
            if event is None:
                raise EntityNotFoundError("Application event was not found.")
            if event.application_id != application_id or event.event_type != "interview_scheduled":
                raise CareerDomainError(
                    "The selected event is not an interview event for this application.",
                    code="invalid_interview_application_event",
                )
            linked = session.scalar(
                select(InterviewModel.id).where(InterviewModel.application_event_id == event.id)
            )
            if linked:
                raise CareerDomainError(
                    "The application event is already linked to an interview.",
                    code="interview_application_event_already_linked",
                )
            return event
        linked_event_ids = select(InterviewModel.application_event_id).where(
            InterviewModel.application_event_id.is_not(None)
        )
        return session.scalar(
            select(ApplicationEventModel)
            .where(
                ApplicationEventModel.application_id == application_id,
                ApplicationEventModel.event_type == "interview_scheduled",
                ApplicationEventModel.id.not_in(linked_event_ids),
            )
            .order_by(ApplicationEventModel.sequence_number.desc())
            .limit(1)
        )

    def _ensure_task(
        self,
        session: Session,
        interview: InterviewModel,
        application: ApplicationModel,
        now: datetime,
    ) -> CareerTaskModel:
        source_key = self._task_source_key(interview)
        task = session.scalar(
            select(CareerTaskModel).where(CareerTaskModel.source_key == source_key)
        )
        if task is None:
            task = CareerTaskModel(
                id=str(uuid4()),
                application_id=application.id,
                job_post_id=application.job_post_id,
                source_event_id=interview.application_event_id,
                source_key=source_key,
                task_type="interview",
                title=f"参加面试 · {application.company_name_snapshot}",
                notes=f"{interview.round_type} interview",
                status="pending",
                priority=10,
                due_at=interview.scheduled_at,
                timezone=interview.timezone,
                version=1,
                created_at=now,
                updated_at=now,
                completed_at=None,
                cancelled_at=None,
            )
            session.add(task)
            session.flush()
        return task

    @staticmethod
    def _task_source_key(interview: InterviewModel) -> str:
        if interview.application_event_id:
            return f"application-event:{interview.application_event_id}"
        return f"interview:{interview.id}"

    @staticmethod
    def _reschedule_reminders(session: Session, task: CareerTaskModel, now: datetime) -> None:
        reminders = session.scalars(
            select(ReminderModel).where(
                ReminderModel.task_id == task.id,
                ReminderModel.status == "active",
            )
        ).all()
        for reminder in reminders:
            reminder.scheduled_for = task.due_at - timedelta(minutes=reminder.offset_minutes)
            reminder.version += 1
            reminder.updated_at = now
            schedule = session.scalar(
                select(ScheduleModel).where(ScheduleModel.reminder_id == reminder.id)
            )
            if schedule is not None:
                schedule.next_run_at = reminder.scheduled_for
                schedule.timezone = task.timezone
                schedule.version += 1
                schedule.updated_at = now

    @staticmethod
    def _cancel_reminders(session: Session, task_id: str, now: datetime) -> None:
        reminders = session.scalars(
            select(ReminderModel).where(
                ReminderModel.task_id == task_id,
                ReminderModel.status == "active",
            )
        ).all()
        for reminder in reminders:
            reminder.status = "cancelled"
            reminder.version += 1
            reminder.updated_at = now
            schedule = session.scalar(
                select(ScheduleModel).where(ScheduleModel.reminder_id == reminder.id)
            )
            if schedule is not None:
                schedule.status = "cancelled"
                schedule.version += 1
                schedule.updated_at = now

    @staticmethod
    def _expect_version(interview: InterviewModel, expected_version: int) -> None:
        if interview.version != int(expected_version):
            raise VersionConflictError("Interview changed after it was loaded.")

    @staticmethod
    def _interview(session: Session, interview_id: str) -> InterviewModel:
        row = session.get(InterviewModel, interview_id)
        if row is None:
            raise EntityNotFoundError("Interview was not found.")
        return row

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
