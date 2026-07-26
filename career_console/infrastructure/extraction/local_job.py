"""Offline, deterministic job-description extractor."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from career_console.application.ports.job_extractor import (
    ExtractedJob,
    ExtractedRequirement,
)
from career_console.domain.common.errors import CareerDomainError
from career_console.domain.jobs import RequirementCategory, RequirementLevel

_FIELD_PATTERNS = {
    "title": re.compile(r"^(?:职位|岗位|职位名称|岗位名称|title)\s*[：:]\s*(.+)$", re.I),
    "company": re.compile(r"^(?:公司|公司名称|企业|company)\s*[：:]\s*(.+)$", re.I),
    "location": re.compile(r"^(?:地点|工作地点|城市|location)\s*[：:]\s*(.+)$", re.I),
    "employment_type": re.compile(r"^(?:类型|工作类型|employment\s*type)\s*[：:]\s*(.+)$", re.I),
    "work_mode": re.compile(r"^(?:工作方式|办公方式|work\s*mode)\s*[：:]\s*(.+)$", re.I),
    "target_audience": re.compile(r"^(?:招聘对象|面向人群|target)\s*[：:]\s*(.+)$", re.I),
    "deadline": re.compile(r"^(?:截止时间|申请截止|deadline)\s*[：:]\s*(.+)$", re.I),
}
_MUST_WORDS = ("必须", "要求", "需具备", "至少", "本科", "硕士", "年以上", "required", "must")
_PREFERRED_WORDS = ("优先", "加分", "熟悉", "了解", "preferred", "nice to have")
_SKILL_TERMS = (
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
)


class LocalJobExtractor:
    name = "local_job_rules"
    schema_version = "job_requirement.v1"

    def extract(self, text: str) -> ExtractedJob:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise CareerDomainError(
                "Job description cannot be empty.", code="empty_job_description"
            )
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        fields: dict[str, str] = {}
        metadata_lines: set[int] = set()
        for index, line in enumerate(lines):
            clean = re.sub(r"^[#>*\-•\d.、\s]+", "", line).strip()
            for name, pattern in _FIELD_PATTERNS.items():
                match = pattern.match(clean)
                if match:
                    fields[name] = match.group(1).strip()
                    metadata_lines.add(index)
                    break
        requirements = self._requirements(lines, metadata_lines)
        return ExtractedJob(
            title=fields.get("title") or self._fallback_title(lines),
            company=fields.get("company") or "待确认公司",
            location=fields.get("location"),
            employment_type=fields.get("employment_type"),
            work_mode=fields.get("work_mode"),
            target_audience=fields.get("target_audience"),
            deadline_at=self._deadline(fields.get("deadline")),
            requirements=tuple(requirements),
        )

    @staticmethod
    def _fallback_title(lines: list[str]) -> str:
        for line in lines[:5]:
            clean = re.sub(r"^[#>*\-•\s]+", "", line).strip()
            if (
                clean
                and len(clean) <= 100
                and not any(pattern.match(clean) for pattern in _FIELD_PATTERNS.values())
            ):
                return clean
        return "待确认岗位"

    def _requirements(
        self, lines: list[str], metadata_lines: set[int]
    ) -> list[ExtractedRequirement]:
        result: list[ExtractedRequirement] = []
        in_section = False
        for index, original in enumerate(lines):
            plain = re.sub(r"^[#>*\-•\d.、）)\s]+", "", original).strip()
            lowered = plain.casefold()
            if re.search(
                r"(任职要求|岗位要求|职位要求|任职资格|requirements|qualifications)", lowered
            ):
                in_section = True
                continue
            if re.search(r"(岗位职责|职位描述|福利|我们提供|responsibilities|benefits)", lowered):
                in_section = False
                continue
            bullet = original.lstrip().startswith(("-", "*", "•")) or bool(
                re.match(r"^\s*\d+[.、）)]", original)
            )
            requirement_word = any(word in lowered for word in (*_MUST_WORDS, *_PREFERRED_WORDS))
            if (
                index in metadata_lines
                or len(plain) < 3
                or not (in_section or requirement_word or bullet)
            ):
                continue
            level = (
                RequirementLevel.PREFERRED
                if any(word in lowered for word in _PREFERRED_WORDS)
                else RequirementLevel.MUST
            )
            category = self._category(lowered)
            keywords = tuple(
                dict.fromkeys(term for term in _SKILL_TERMS if term in lowered)
            ) or tuple(self._tokens(plain)[:5])
            result.append(
                ExtractedRequirement(
                    category,
                    level,
                    plain[:1000],
                    original[:1000],
                    keywords,
                    2
                    if category in {RequirementCategory.EDUCATION, RequirementCategory.EXPERIENCE}
                    else 1,
                )
            )
        return result

    @staticmethod
    def _category(text: str) -> RequirementCategory:
        if any(
            term in text
            for term in ("本科", "硕士", "博士", "学历", "degree", "bachelor", "master")
        ):
            return RequirementCategory.EDUCATION
        if any(term in text for term in ("经验", "experience")) or re.search(r"\d+\s*年", text):
            return RequirementCategory.EXPERIENCE
        if any(term in text for term in ("英语", "日语", "语言", "english", "language")):
            return RequirementCategory.LANGUAGE
        if any(term in text for term in _SKILL_TERMS):
            return RequirementCategory.SKILL
        if any(term in text for term in ("远程", "现场", "remote", "hybrid", "onsite")):
            return RequirementCategory.WORK_MODE
        return RequirementCategory.OTHER

    @staticmethod
    def _tokens(text: str) -> list[str]:
        latin = re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,30}", text.casefold())
        chinese = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
        stop = {"要求", "优先", "熟悉", "具备", "具有", "负责", "能够", "以及", "相关"}
        return [token for token in [*latin, *chinese] if token not in stop]

    @staticmethod
    def _deadline(value: str | None) -> datetime | None:
        if not value:
            return None
        match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", value)
        if not match:
            return None
        local = datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            23,
            59,
            59,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        )
        return local.astimezone(UTC)
