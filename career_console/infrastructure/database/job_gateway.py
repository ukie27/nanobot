"""SQLAlchemy adapter for the versioned job pool and explainable matching."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from career_console.application.ports.job_extractor import ExtractedJob
from career_console.domain.jobs import (
    CandidateEvidence,
    EvidenceDecision,
    JobRequirement,
    RequirementCategory,
    RequirementLevel,
    evaluate_match,
)
from career_console.infrastructure.database.models import (
    CandidateFactModel,
    CandidateProfileModel,
    CompanyAliasModel,
    CompanyModel,
    JobMatchAnalysisModel,
    JobMatchEvidenceModel,
    JobPostModel,
    JobPostSourceModel,
    JobPostVersionModel,
    JobRequirementModel,
    MailIntelligenceAnalysisModel,
    OpportunityJobLinkModel,
    RecruitmentOpportunityModel,
)
from career_console.infrastructure.database.profile_gateway import (
    EntityNotFoundError,
    ensure_profile_model,
)


class SqlAlchemyJobGateway:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def import_job(
        self,
        *,
        name: str,
        text: str,
        source_url: str | None,
        source_type: str,
        extracted: ExtractedJob,
        extractor_name: str,
        extractor_schema_version: str,
        opportunity_id: str | None = None,
        mail_analysis_id: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        content_hash = hashlib.sha256(self._canonical_content(text).encode("utf-8")).hexdigest()
        with self._session_factory() as session:
            profile = self._ensure_profile(session, now)
            company = self._company(session, extracted.company, now)
            normalized_title = self._normalize(extracted.title)
            normalized_location = self._normalize(extracted.location or "")
            source_key = self._source_key(
                source_url, company.normalized_name, normalized_title, normalized_location
            )
            source = session.scalar(
                select(JobPostSourceModel).where(JobPostSourceModel.source_key == source_key)
            )
            post = session.get(JobPostModel, source.job_post_id) if source is not None else None
            if post is None:
                post = session.scalar(
                    select(JobPostModel).where(
                        JobPostModel.company_id == company.id,
                        JobPostModel.normalized_title == normalized_title,
                        JobPostModel.normalized_location == normalized_location,
                    )
                )
            created = post is None
            if post is None:
                post = JobPostModel(
                    id=str(uuid4()),
                    company_id=company.id,
                    title=extracted.title,
                    normalized_title=normalized_title,
                    location=extracted.location,
                    normalized_location=normalized_location,
                    employment_type=extracted.employment_type,
                    work_mode=extracted.work_mode,
                    target_audience=extracted.target_audience,
                    deadline_at=extracted.deadline_at,
                    status="active",
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(post)
                session.flush()
            if source is None:
                source = JobPostSourceModel(
                    id=str(uuid4()),
                    job_post_id=post.id,
                    source_type=source_type,
                    source_url=source_url,
                    source_key=source_key,
                    display_name=name[:300],
                    discovered_at=now,
                    last_seen_at=now,
                )
                session.add(source)
            else:
                source.last_seen_at = now
            existing_version = session.scalar(
                select(JobPostVersionModel).where(
                    JobPostVersionModel.job_post_id == post.id,
                    JobPostVersionModel.content_hash == content_hash,
                )
            )
            if existing_version is not None:
                self._link_opportunity(session, opportunity_id, post.id, now)
                self._link_mail_analysis(session, mail_analysis_id, post.id, now)
                session.commit()
                return self._job_view(session, post, duplicate=True)
            next_number = (
                session.scalar(
                    select(func.max(JobPostVersionModel.version_number)).where(
                        JobPostVersionModel.job_post_id == post.id
                    )
                )
                or 0
            ) + 1
            version = JobPostVersionModel(
                id=str(uuid4()),
                job_post_id=post.id,
                version_number=next_number,
                content_hash=content_hash,
                raw_text=text,
                extractor_name=extractor_name,
                extractor_schema_version=extractor_schema_version,
                created_at=now,
            )
            session.add(version)
            session.flush()
            for ordinal, item in enumerate(extracted.requirements):
                session.add(
                    JobRequirementModel(
                        id=str(uuid4()),
                        job_post_version_id=version.id,
                        category=item.category.value,
                        level=item.level.value,
                        description=item.description,
                        evidence_text=item.evidence_text,
                        keywords_json=json.dumps(item.keywords, ensure_ascii=False),
                        weight=item.weight,
                        ordinal=ordinal,
                    )
                )
            post.title = extracted.title
            post.normalized_title = normalized_title
            post.location = extracted.location
            post.normalized_location = normalized_location
            post.employment_type = extracted.employment_type
            post.work_mode = extracted.work_mode
            post.target_audience = extracted.target_audience
            post.deadline_at = extracted.deadline_at
            post.version = next_number
            post.updated_at = now
            session.flush()
            self._create_analysis(session, post, version, profile, now)
            self._link_opportunity(session, opportunity_id, post.id, now)
            self._link_mail_analysis(session, mail_analysis_id, post.id, now)
            session.commit()
            return self._job_view(session, post, duplicate=False, created=created)

    def list_jobs(self, *, status: str | None = None) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            statement = select(JobPostModel).order_by(JobPostModel.updated_at.desc())
            if status:
                statement = statement.where(JobPostModel.status == status)
            return [self._job_summary(session, item) for item in session.scalars(statement).all()]

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            post = session.get(JobPostModel, job_id)
            if post is None:
                raise EntityNotFoundError("Job post was not found.")
            return self._job_view(session, post)

    def analyze_job(self, job_id: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            post = session.get(JobPostModel, job_id)
            if post is None:
                raise EntityNotFoundError("Job post was not found.")
            version = self._latest_version(session, post.id)
            profile = self._ensure_profile(session, now)
            facts = session.scalars(
                select(CandidateFactModel).where(
                    CandidateFactModel.profile_id == profile.id,
                    CandidateFactModel.status == "confirmed",
                ).order_by(CandidateFactModel.id)
            ).all()
            fact_set_hash = hashlib.sha256(
                "\n".join(f"{fact.id}:{fact.version}:{fact.value}" for fact in facts).encode("utf-8")
            ).hexdigest()
            existing = session.scalar(select(JobMatchAnalysisModel).where(
                JobMatchAnalysisModel.job_post_id == post.id,
                JobMatchAnalysisModel.job_post_version_id == version.id,
                JobMatchAnalysisModel.profile_id == profile.id,
                JobMatchAnalysisModel.fact_set_hash == fact_set_hash,
                JobMatchAnalysisModel.analysis_origin == "deterministic",
            ).order_by(JobMatchAnalysisModel.created_at.desc()))
            if existing is not None:
                return {**self._analysis_view(session, existing), "reused": True}
            try:
                analysis = self._create_analysis(session, post, version, profile, now)
                session.commit()
            except IntegrityError:
                session.rollback()
                analysis = session.scalar(select(JobMatchAnalysisModel).where(
                    JobMatchAnalysisModel.job_post_id == post.id,
                    JobMatchAnalysisModel.job_post_version_id == version.id,
                    JobMatchAnalysisModel.profile_id == profile.id,
                    JobMatchAnalysisModel.fact_set_hash == fact_set_hash,
                    JobMatchAnalysisModel.analysis_origin == "deterministic",
                ))
                if analysis is None:
                    raise
                return {**self._analysis_view(session, analysis), "reused": True}
            return {**self._analysis_view(session, analysis), "reused": False}

    def _create_analysis(
        self,
        session: Session,
        post: JobPostModel,
        version: JobPostVersionModel,
        profile: CandidateProfileModel,
        now: datetime,
    ) -> JobMatchAnalysisModel:
        requirement_models = session.scalars(
            select(JobRequirementModel)
            .where(JobRequirementModel.job_post_version_id == version.id)
            .order_by(JobRequirementModel.ordinal)
        ).all()
        facts = session.scalars(
            select(CandidateFactModel)
            .where(
                CandidateFactModel.profile_id == profile.id,
                CandidateFactModel.status == "confirmed",
            )
            .order_by(CandidateFactModel.id)
        ).all()
        fact_set_hash = hashlib.sha256(
            "\n".join(f"{fact.id}:{fact.version}:{fact.value}" for fact in facts).encode("utf-8")
        ).hexdigest()
        requirements = [
            JobRequirement(
                item.id,
                RequirementCategory(item.category),
                RequirementLevel(item.level),
                item.description,
                item.evidence_text,
                item.weight,
            )
            for item in requirement_models
        ]
        evidence: list[CandidateEvidence] = []
        evidence_facts: dict[str, list[CandidateFactModel]] = {}
        for item in requirement_models:
            matches = self._matching_facts(item, facts)
            evidence_facts[item.id] = matches
            decision = EvidenceDecision.MATCHED if matches else EvidenceDecision.GAP
            rationale = (
                "由已确认职业事实支持。" if matches else "未在已确认职业事实中找到可验证证据。"
            )
            evidence.append(
                CandidateEvidence(item.id, decision, tuple(fact.id for fact in matches), rationale)
            )
        result = evaluate_match(requirements, evidence)
        analysis = JobMatchAnalysisModel(
            id=str(uuid4()),
            job_post_id=post.id,
            job_post_version_id=version.id,
            profile_id=profile.id,
            fact_set_hash=fact_set_hash,
            analysis_origin="deterministic",
            hard_gate_passed=int(result.hard_gate_passed),
            score=result.score,
            matched_count=result.matched_count,
            gap_count=result.gap_count,
            must_gap_count=result.must_gap_count,
            recommendation=result.recommendation,
            created_at=now,
        )
        session.add(analysis)
        session.flush()
        for item in evidence:
            matched = evidence_facts[item.requirement_id]
            if matched:
                for fact in matched:
                    session.add(
                        JobMatchEvidenceModel(
                            id=str(uuid4()),
                            analysis_id=analysis.id,
                            requirement_id=item.requirement_id,
                            fact_id=fact.id,
                            fact_version=fact.version,
                            fact_value_snapshot=fact.value,
                            decision=item.decision.value,
                            rationale=item.rationale,
                        )
                    )
            else:
                session.add(
                    JobMatchEvidenceModel(
                        id=str(uuid4()),
                        analysis_id=analysis.id,
                        requirement_id=item.requirement_id,
                        fact_id=None,
                        fact_version=None,
                        fact_value_snapshot=None,
                        decision=item.decision.value,
                        rationale=item.rationale,
                    )
                )
        session.flush()
        return analysis

    def _matching_facts(
        self, requirement: JobRequirementModel, facts: list[CandidateFactModel]
    ) -> list[CandidateFactModel]:
        keywords = [str(value).casefold() for value in json.loads(requirement.keywords_json)]
        description = requirement.description.casefold()
        if requirement.category == RequirementCategory.EDUCATION.value:
            levels = {"大专": 1, "本科": 2, "硕士": 3, "博士": 4}
            required = max(
                (score for name, score in levels.items() if name in description), default=0
            )
            return [
                fact
                for fact in facts
                if max((score for name, score in levels.items() if name in fact.value), default=0)
                >= required
                > 0
            ]
        if requirement.category == RequirementCategory.EXPERIENCE.value:
            required_match = re.search(r"(\d+)\s*年", description)
            if required_match:
                required = int(required_match.group(1))
                return [
                    fact
                    for fact in facts
                    if any(
                        int(value) >= required for value in re.findall(r"(\d+)\s*年", fact.value)
                    )
                ]
        explicit = [
            keyword
            for keyword in keywords
            if keyword
            in {
                "python",
                "java",
                "go",
                "rust",
                "javascript",
                "typescript",
                "react",
                "vue",
                "sql",
                "mysql",
                "postgresql",
                "redis",
                "docker",
                "kubernetes",
                "k8s",
                "fastapi",
                "django",
                "spring",
                "linux",
                "aws",
                "azure",
                "git",
                "算法",
                "数据结构",
                "机器学习",
                "大模型",
            }
        ]
        if explicit:
            found: list[CandidateFactModel] = []
            for keyword in explicit:
                candidates = [fact for fact in facts if keyword in fact.value.casefold()]
                if not candidates:
                    return []
                found.extend(candidates)
            return list({fact.id: fact for fact in found}.values())
        return [
            fact
            for fact in facts
            if any(keyword and keyword in fact.value.casefold() for keyword in keywords)
        ]

    def _job_summary(self, session: Session, post: JobPostModel) -> dict[str, Any]:
        company = session.get(CompanyModel, post.company_id)
        analysis = session.scalar(
            select(JobMatchAnalysisModel)
            .where(JobMatchAnalysisModel.job_post_id == post.id)
            .order_by(JobMatchAnalysisModel.created_at.desc())
        )
        return {
            "id": post.id,
            "company": company.canonical_name if company else "",
            "title": post.title,
            "location": post.location,
            "employment_type": post.employment_type,
            "work_mode": post.work_mode,
            "deadline_at": self._as_utc(post.deadline_at),
            "status": post.status,
            "version": post.version,
            "latest_analysis": self._analysis_summary(analysis),
            "created_at": self._as_utc(post.created_at),
            "updated_at": self._as_utc(post.updated_at),
        }

    def _job_view(
        self,
        session: Session,
        post: JobPostModel,
        *,
        duplicate: bool = False,
        created: bool = False,
    ) -> dict[str, Any]:
        result = self._job_summary(session, post)
        versions = session.scalars(
            select(JobPostVersionModel)
            .where(JobPostVersionModel.job_post_id == post.id)
            .order_by(JobPostVersionModel.version_number.desc())
        ).all()
        latest = versions[0]
        requirements = session.scalars(
            select(JobRequirementModel)
            .where(JobRequirementModel.job_post_version_id == latest.id)
            .order_by(JobRequirementModel.ordinal)
        ).all()
        sources = session.scalars(
            select(JobPostSourceModel)
            .where(JobPostSourceModel.job_post_id == post.id)
            .order_by(JobPostSourceModel.discovered_at)
        ).all()
        analyses = session.scalars(
            select(JobMatchAnalysisModel)
            .where(JobMatchAnalysisModel.job_post_id == post.id)
            .order_by(JobMatchAnalysisModel.created_at.desc())
        ).all()
        opportunity_ids = session.scalars(
            select(OpportunityJobLinkModel.opportunity_id).where(
                OpportunityJobLinkModel.job_post_id == post.id
            )
        ).all()
        result.update(
            {
                "duplicate": duplicate,
                "created": created,
                "target_audience": post.target_audience,
                "raw_text": latest.raw_text,
                "content_hash": latest.content_hash,
                "requirements": [self._requirement_view(item) for item in requirements],
                "versions": [
                    {
                        "id": item.id,
                        "version_number": item.version_number,
                        "content_hash": item.content_hash,
                        "created_at": self._as_utc(item.created_at),
                    }
                    for item in versions
                ],
                "sources": [
                    {
                        "id": item.id,
                        "source_type": item.source_type,
                        "source_url": item.source_url,
                        "display_name": item.display_name,
                        "discovered_at": self._as_utc(item.discovered_at),
                        "last_seen_at": self._as_utc(item.last_seen_at),
                    }
                    for item in sources
                ],
                "analyses": [self._analysis_view(session, item) for item in analyses],
                "opportunity_ids": list(opportunity_ids),
            }
        )
        return result

    def _analysis_view(self, session: Session, analysis: JobMatchAnalysisModel) -> dict[str, Any]:
        result = self._analysis_summary(analysis)
        evidence = session.scalars(
            select(JobMatchEvidenceModel)
            .where(JobMatchEvidenceModel.analysis_id == analysis.id)
            .order_by(JobMatchEvidenceModel.requirement_id)
        ).all()
        grouped: dict[str, dict[str, Any]] = {}
        for item in evidence:
            requirement = session.get(JobRequirementModel, item.requirement_id)
            entry = grouped.setdefault(
                item.requirement_id,
                {
                    "requirement": self._requirement_view(requirement),
                    "decision": item.decision,
                    "rationale": item.rationale,
                    "facts": [],
                },
            )
            if item.fact_id:
                fact = session.get(CandidateFactModel, item.fact_id)
                if fact and fact.status == "confirmed":
                    entry["facts"].append(
                        {
                            "id": fact.id,
                            "category": fact.category,
                            "field_key": fact.field_key,
                            "value": item.fact_value_snapshot,
                            "version": item.fact_version,
                        }
                    )
        result["evidence"] = list(grouped.values())
        return result

    @staticmethod
    def _analysis_summary(item: JobMatchAnalysisModel | None) -> dict[str, Any] | None:
        if item is None:
            return None
        return {
            "id": item.id,
            "job_post_version_id": item.job_post_version_id,
            "analysis_origin": item.analysis_origin,
            "hard_gate_passed": bool(item.hard_gate_passed),
            "score": item.score,
            "matched_count": item.matched_count,
            "gap_count": item.gap_count,
            "must_gap_count": item.must_gap_count,
            "recommendation": item.recommendation,
            "created_at": SqlAlchemyJobGateway._as_utc(item.created_at),
        }

    @staticmethod
    def _requirement_view(item: JobRequirementModel) -> dict[str, Any]:
        return {
            "id": item.id,
            "category": item.category,
            "level": item.level,
            "description": item.description,
            "evidence_text": item.evidence_text,
            "keywords": json.loads(item.keywords_json),
            "weight": item.weight,
            "ordinal": item.ordinal,
        }

    @staticmethod
    def _latest_version(session: Session, job_id: str) -> JobPostVersionModel:
        return session.scalar(
            select(JobPostVersionModel)
            .where(JobPostVersionModel.job_post_id == job_id)
            .order_by(JobPostVersionModel.version_number.desc())
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", "", value).casefold()

    @staticmethod
    def _canonical_content(value: str) -> str:
        return "\n".join(
            line.rstrip()
            for line in value.replace("\r\n", "\n").replace("\r", "\n").strip().splitlines()
        )

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _source_key(url: str | None, company: str, title: str, location: str) -> str:
        return f"url:{url.strip()}" if url else f"manual:{company}|{title}|{location}"

    def _company(self, session: Session, name: str, now: datetime) -> CompanyModel:
        normalized = self._normalize(name)
        alias = session.scalar(
            select(CompanyAliasModel).where(CompanyAliasModel.normalized_alias == normalized)
        )
        if alias:
            return session.get(CompanyModel, alias.company_id)
        company = session.scalar(
            select(CompanyModel).where(CompanyModel.normalized_name == normalized)
        )
        if company is None:
            company = CompanyModel(
                id=str(uuid4()), canonical_name=name, normalized_name=normalized, created_at=now
            )
            session.add(company)
            session.flush()
        return company

    @staticmethod
    def _link_opportunity(
        session: Session,
        opportunity_id: str | None,
        job_post_id: str,
        now: datetime,
    ) -> None:
        if opportunity_id is None:
            return
        if session.get(RecruitmentOpportunityModel, opportunity_id) is None:
            raise LookupError("招聘机会不存在。")
        existing = session.scalar(
            select(OpportunityJobLinkModel).where(
                OpportunityJobLinkModel.opportunity_id == opportunity_id,
                OpportunityJobLinkModel.job_post_id == job_post_id,
            )
        )
        if existing is None:
            session.add(
                OpportunityJobLinkModel(
                    id=str(uuid4()),
                    opportunity_id=opportunity_id,
                    job_post_id=job_post_id,
                    created_at=now,
                )
            )

    @staticmethod
    def _link_mail_analysis(
        session: Session, mail_analysis_id: str | None, job_post_id: str, now: datetime
    ) -> None:
        del now
        if mail_analysis_id is None:
            return
        analysis = session.get(MailIntelligenceAnalysisModel, mail_analysis_id)
        if analysis is None:
            raise LookupError("邮件智能分析不存在。")
        if analysis.application_id is not None:
            raise ValueError("该邮件已经关联正式申请。")
        if analysis.job_post_id not in {None, job_post_id}:
            raise ValueError("该邮件已经关联其他岗位。")
        analysis.job_post_id = job_post_id

    @staticmethod
    def _ensure_profile(session: Session, now: datetime) -> CandidateProfileModel:
        return ensure_profile_model(session, now)
