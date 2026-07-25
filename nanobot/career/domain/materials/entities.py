"""Pure validation and review rules for fact-bound application materials."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class MaterialType(StrEnum):
    RESUME = "resume"
    COVER_LETTER = "cover_letter"
    INTRODUCTION = "introduction"


class VersionStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    FINAL = "final"


@dataclass(frozen=True, slots=True)
class FactSnapshot:
    id: str
    fact_id: str
    fact_version: int
    value: str


@dataclass(frozen=True, slots=True)
class MaterialBlock:
    id: str
    section: str
    text: str
    fact_snapshot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MaterialFinding:
    severity: str
    code: str
    message: str
    block_id: str | None = None


_PLACEHOLDER = re.compile(
    r"\{\{[^}]+\}\}|\[[^\]]*(?:待填|待补|TODO)[^\]]*\]|\b(?:TODO|TBD)\b", re.I
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?%?")
_SAFE_FRAMING = (
    "重点经历",
    "核心能力",
    "相关经验",
    "专业技能",
    "教育背景",
    "项目成果",
    "工作亮点",
    "个人优势",
    "我具备",
    "我拥有",
    "本人",
    "Core experience",
    "Key skill",
    "Relevant experience",
)


def review_material(
    blocks: list[MaterialBlock],
    snapshots: list[FactSnapshot],
    *,
    uncovered_requirement_count: int = 0,
    hard_gap_count: int = 0,
) -> list[MaterialFinding]:
    """Reject unsupported claims while allowing wording around verbatim evidence."""
    findings: list[MaterialFinding] = []
    snapshot_by_id = {item.id: item for item in snapshots}
    seen_ids: set[str] = set()
    for block in blocks:
        text = block.text.strip()
        if block.id in seen_ids:
            findings.append(
                MaterialFinding("error", "duplicate_block_id", "材料块 ID 重复。", block.id)
            )
            continue
        seen_ids.add(block.id)
        if not text:
            findings.append(MaterialFinding("error", "empty_claim", "事实表达不能为空。", block.id))
            continue
        if _PLACEHOLDER.search(text):
            findings.append(
                MaterialFinding("error", "unresolved_placeholder", "存在未解析占位符。", block.id)
            )
        linked = [
            snapshot_by_id[item_id]
            for item_id in block.fact_snapshot_ids
            if item_id in snapshot_by_id
        ]
        if len(linked) != len(block.fact_snapshot_ids) or not linked:
            findings.append(
                MaterialFinding(
                    "error",
                    "invalid_fact_reference",
                    "每条事实表达必须引用有效的事实快照。",
                    block.id,
                )
            )
            continue
        normalized_text = _normalize(text)
        if not any(_normalize(item.value) in normalized_text for item in linked):
            findings.append(
                MaterialFinding(
                    "error",
                    "unsupported_claim",
                    "编辑后的表达必须保留至少一条引用事实的完整原文。",
                    block.id,
                )
            )
        else:
            residual = text
            for item in linked:
                residual = residual.replace(item.value, "")
            for phrase in _SAFE_FRAMING:
                residual = residual.replace(phrase, "")
            residual = re.sub(r"[\s\W_]+", "", residual, flags=re.UNICODE)
            if residual:
                findings.append(
                    MaterialFinding(
                        "error",
                        "unsupported_claim",
                        "编辑只能调整格式或使用受控引导语，不能加入事实快照外的新陈述。",
                        block.id,
                    )
                )
        allowed_numbers = {token for item in linked for token in _NUMBER.findall(item.value)}
        introduced_numbers = set(_NUMBER.findall(text)) - allowed_numbers
        if introduced_numbers:
            findings.append(
                MaterialFinding(
                    "error", "unsupported_number", "表达中出现了事实快照没有支持的数字。", block.id
                )
            )
    if uncovered_requirement_count:
        findings.append(
            MaterialFinding(
                "warning",
                "requirement_not_covered",
                f"还有 {uncovered_requirement_count} 项已匹配岗位要求未在材料中体现。",
            )
        )
    if hard_gap_count:
        findings.append(
            MaterialFinding(
                "warning",
                "hard_requirement_gap",
                f"岗位仍有 {hard_gap_count} 个硬性条件缺口，材料不会虚构经历填补。",
            )
        )
    return findings


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()
