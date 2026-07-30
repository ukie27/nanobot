"""Deterministic business-object extractor for offline profile imports."""

from __future__ import annotations

import re
from collections import defaultdict

from career_console.application.ports.fact_extractor import ExtractedFact
from career_console.domain.profile.entities import FactCategory
from career_console.domain.profile.privacy import remove_contact_information


class LocalResumeFactExtractor:
    """Conservatively group related resume lines into reviewable business objects."""

    name = "local_resume_object_extractor"
    schema_version = "candidate_profile_object.v2"

    _LABELS = {
        "姓名": (FactCategory.BASIC, "姓名"),
        "name": (FactCategory.BASIC, "姓名"),
        "学校": (FactCategory.EDUCATION, "学校"),
        "院校": (FactCategory.EDUCATION, "学校"),
        "专业": (FactCategory.EDUCATION, "专业"),
        "学历": (FactCategory.EDUCATION, "学历"),
        "目标岗位": (FactCategory.PREFERENCE, "目标岗位"),
        "求职意向": (FactCategory.PREFERENCE, "目标岗位"),
        "目标城市": (FactCategory.PREFERENCE, "目标城市"),
        "期望城市": (FactCategory.PREFERENCE, "目标城市"),
        "技能": (FactCategory.SKILL, "技能"),
        "技术栈": (FactCategory.SKILL, "技术栈"),
    }
    _SECTIONS = {
        "教育经历": FactCategory.EDUCATION,
        "教育背景": FactCategory.EDUCATION,
        "实习经历": FactCategory.INTERNSHIP,
        "工作经历": FactCategory.WORK,
        "项目经历": FactCategory.PROJECT,
        "项目经验": FactCategory.PROJECT,
        "专业技能": FactCategory.SKILL,
        "技能清单": FactCategory.SKILL,
        "获奖经历": FactCategory.AWARD,
        "荣誉奖项": FactCategory.AWARD,
        "证书": FactCategory.CERTIFICATE,
        "证书资质": FactCategory.CERTIFICATE,
    }
    _TITLES = {
        FactCategory.BASIC: "基础信息",
        FactCategory.EDUCATION: "教育经历",
        FactCategory.INTERNSHIP: "实习经历",
        FactCategory.WORK: "工作经历",
        FactCategory.PROJECT: "项目经历",
        FactCategory.SKILL: "技能画像",
        FactCategory.AWARD: "奖项荣誉",
        FactCategory.CERTIFICATE: "证书资质",
        FactCategory.PREFERENCE: "求职偏好",
        FactCategory.CONSTRAINT: "限制条件",
    }

    def extract(self, *, document_id: str, text: str) -> list[ExtractedFact]:
        del document_id
        labeled: dict[FactCategory, list[tuple[str, str]]] = defaultdict(list)
        section_blocks: list[tuple[FactCategory, list[str]]] = []
        current_section: FactCategory | None = None
        current_evidence: list[str] = []

        def flush_section() -> None:
            nonlocal current_evidence
            if current_section is not None and current_evidence:
                section_blocks.append((current_section, current_evidence))
            current_evidence = []

        for raw_line in text.splitlines():
            stripped = remove_contact_information(raw_line).strip()
            line = stripped.strip("-•· \t")
            if not line:
                flush_section()
                continue
            heading = line.rstrip("：:").strip()
            if heading in self._SECTIONS:
                flush_section()
                current_section = self._SECTIONS[heading]
                continue
            if current_section is not None:
                current_evidence.append(stripped)
                continue
            match = re.match(r"^([^：:]{1,12})[：:]\s*(.+)$", line)
            if match:
                mapping = self._LABELS.get(match.group(1).strip().lower())
                if mapping:
                    category, canonical_label = mapping
                    labeled[category].append(
                        (f"{canonical_label}：{match.group(2).strip()}", stripped)
                    )
        flush_section()

        facts: list[ExtractedFact] = []
        seen: set[tuple[str, str]] = set()
        for category in (
            FactCategory.BASIC,
            FactCategory.EDUCATION,
            FactCategory.PREFERENCE,
        ):
            entries = labeled.get(category, [])
            if entries:
                self._append_object(
                    facts,
                    seen,
                    category=category,
                    object_key={
                        FactCategory.BASIC: "profile_summary",
                        FactCategory.EDUCATION: "education:summary",
                        FactCategory.PREFERENCE: "preference:job_search",
                    }[category],
                    title=self._title_for_entries(category, [value for value, _ in entries]),
                    content="\n".join(value for value, _ in entries),
                    evidence=[evidence for _, evidence in entries],
                    confidence=0.92,
                )

        skill_lines = [value for value, _ in labeled.get(FactCategory.SKILL, [])]
        skill_evidence = [evidence for _, evidence in labeled.get(FactCategory.SKILL, [])]
        remaining_blocks: list[tuple[FactCategory, list[str]]] = []
        for category, evidence in section_blocks:
            if category is FactCategory.SKILL:
                skill_lines.extend(item.strip("-•· \t") for item in evidence)
                skill_evidence.extend(evidence)
            else:
                remaining_blocks.append((category, evidence))
        if skill_lines:
            self._append_object(
                facts,
                seen,
                category=FactCategory.SKILL,
                object_key="skill_profile",
                title="技能画像",
                content="\n".join(skill_lines),
                evidence=skill_evidence,
                confidence=0.86,
            )

        category_indexes: dict[FactCategory, int] = defaultdict(int)
        for category, evidence in remaining_blocks:
            category_indexes[category] += 1
            content_lines = [item.strip("-•· \t") for item in evidence]
            title = self._object_title(category, content_lines[0])
            self._append_object(
                facts,
                seen,
                category=category,
                object_key=f"{category.value}:{category_indexes[category]}",
                title=title,
                content="\n".join(content_lines),
                evidence=evidence,
                confidence=0.78,
            )
        return facts[:100]

    @classmethod
    def _title_for_entries(cls, category: FactCategory, values: list[str]) -> str:
        if category is FactCategory.BASIC:
            name = next(
                (item.partition("：")[2] for item in values if item.startswith("姓名：")),
                "",
            )
            return f"{name}的基础信息" if name else cls._TITLES[category]
        if category is FactCategory.EDUCATION:
            school = next(
                (item.partition("：")[2] for item in values if item.startswith("学校：")),
                "",
            )
            return school or cls._TITLES[category]
        return cls._TITLES[category]

    @classmethod
    def _object_title(cls, category: FactCategory, first_line: str) -> str:
        candidate = first_line.strip("：: ")
        if 1 <= len(candidate) <= 80:
            return candidate
        return cls._TITLES[category]

    @staticmethod
    def _append_object(
        facts: list[ExtractedFact],
        seen: set[tuple[str, str]],
        *,
        category: FactCategory,
        object_key: str,
        title: str,
        content: str,
        evidence: list[str],
        confidence: float,
    ) -> None:
        normalized = " ".join(content.casefold().split())
        dedup_key = (category.value, normalized)
        clean_evidence = tuple(dict.fromkeys(item.strip() for item in evidence if item.strip()))
        if not normalized or not clean_evidence or dedup_key in seen:
            return
        seen.add(dedup_key)
        facts.append(
            ExtractedFact(
                category=category,
                field_key=object_key,
                value=content.strip(),
                evidence_text="\n".join(clean_evidence),
                confidence=confidence,
                title=title.strip(),
                evidence_texts=clean_evidence,
            )
        )
