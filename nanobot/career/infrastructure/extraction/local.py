"""Deterministic baseline fact extractor for offline Part 1 usage."""

from __future__ import annotations

import re

from nanobot.career.application.ports.fact_extractor import ExtractedFact
from nanobot.career.domain.profile.entities import FactCategory


class LocalResumeFactExtractor:
    name = "local_resume_extractor"
    schema_version = "candidate_fact.v1"

    _LABELS = {
        "姓名": (FactCategory.BASIC, "name"),
        "name": (FactCategory.BASIC, "name"),
        "邮箱": (FactCategory.BASIC, "email"),
        "email": (FactCategory.BASIC, "email"),
        "电话": (FactCategory.BASIC, "phone"),
        "手机": (FactCategory.BASIC, "phone"),
        "学校": (FactCategory.EDUCATION, "school"),
        "院校": (FactCategory.EDUCATION, "school"),
        "专业": (FactCategory.EDUCATION, "major"),
        "学历": (FactCategory.EDUCATION, "degree"),
        "目标岗位": (FactCategory.PREFERENCE, "target_role"),
        "求职意向": (FactCategory.PREFERENCE, "target_role"),
        "目标城市": (FactCategory.PREFERENCE, "target_city"),
        "期望城市": (FactCategory.PREFERENCE, "target_city"),
        "技能": (FactCategory.SKILL, "skill"),
        "技术栈": (FactCategory.SKILL, "skill"),
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
    _EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
    _PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")

    def extract(self, *, document_id: str, text: str) -> list[ExtractedFact]:
        del document_id
        facts: list[ExtractedFact] = []
        seen: set[tuple[str, str, str]] = set()
        current_section: FactCategory | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip(" \t-•·")
            if not line:
                continue
            heading = line.rstrip("：:").strip()
            if heading in self._SECTIONS:
                current_section = self._SECTIONS[heading]
                continue
            labeled = re.match(r"^([^：:]{1,12})[：:]\s*(.+)$", line)
            if labeled:
                label = labeled.group(1).strip().lower()
                value = labeled.group(2).strip()
                mapping = self._LABELS.get(label)
                if mapping:
                    category, field_key = mapping
                    values = self._split_values(value) if field_key == "skill" else [value]
                    for item in values:
                        self._append(facts, seen, category, field_key, item, raw_line, 0.92)
                    continue
            if current_section is not None and len(line) >= 2:
                field_key = {
                    FactCategory.EDUCATION: "education_experience",
                    FactCategory.INTERNSHIP: "internship_experience",
                    FactCategory.WORK: "work_experience",
                    FactCategory.PROJECT: "project_experience",
                    FactCategory.SKILL: "skill",
                    FactCategory.AWARD: "award",
                    FactCategory.CERTIFICATE: "certificate",
                }[current_section]
                values = self._split_values(line) if current_section is FactCategory.SKILL else [line]
                for item in values:
                    self._append(facts, seen, current_section, field_key, item, raw_line, 0.72)

        for match in self._EMAIL.finditer(text):
            self._append(facts, seen, FactCategory.BASIC, "email", match.group(), match.group(), 0.98)
        for match in self._PHONE.finditer(text):
            self._append(facts, seen, FactCategory.BASIC, "phone", match.group(), match.group(), 0.96)
        return facts[:200]

    @staticmethod
    def _split_values(value: str) -> list[str]:
        values = [item.strip() for item in re.split(r"[,，、/|]", value) if item.strip()]
        return values or [value]

    @staticmethod
    def _append(
        facts: list[ExtractedFact],
        seen: set[tuple[str, str, str]],
        category: FactCategory,
        field_key: str,
        value: str,
        evidence: str,
        confidence: float,
    ) -> None:
        normalized = " ".join(value.casefold().split())
        key = (category.value, field_key, normalized)
        if not normalized or key in seen:
            return
        seen.add(key)
        facts.append(ExtractedFact(category, field_key, value.strip(), evidence.strip(), confidence))
