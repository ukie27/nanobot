"""Constrained discovery for public pages that clearly represent one concrete JD."""

from __future__ import annotations

from urllib.parse import urlsplit

from career_console.application.ports.job_recommendation import (
    DiscoveredJobDescription,
    JobDiscoveryResult,
)
from career_console.domain.common.errors import CareerDomainError


class SafeHtmlJobDescriptionDiscovery:
    """First version: accept only a readable, explicit single-job public page."""

    _JD_MARKERS = (
        "职位描述",
        "岗位描述",
        "岗位职责",
        "任职要求",
        "职位要求",
        "job description",
        "responsibilities",
        "qualifications",
    )

    def __init__(self, fetcher: object) -> None:
        self.fetcher = fetcher

    def discover(self, *, opportunity: dict) -> JobDiscoveryResult:
        url = str(opportunity.get("application_url") or "").strip()
        parsed = urlsplit(url)
        if parsed.path in {"", "/"}:
            return JobDiscoveryResult(
                status="unsupported", error_code="jd_discovery_recruitment_homepage"
            )
        try:
            title, text = self.fetcher.fetch(url)
        except CareerDomainError as exc:
            return JobDiscoveryResult(status="processing_failed", error_code=exc.code)
        lowered = text.casefold()
        marker_count = sum(marker.casefold() in lowered for marker in self._JD_MARKERS)
        if len(text) < 300 or marker_count < 2:
            return JobDiscoveryResult(
                status="unsupported", error_code="jd_discovery_not_single_job"
            )
        company = str(opportunity.get("company") or "").strip()
        normalized_text = text
        if company and not any(
            line.startswith(("公司：", "公司:", "公司名称：", "company:"))
            for line in text.splitlines()[:20]
        ):
            normalized_text = f"公司：{company}\n{text}"
        return JobDiscoveryResult(
            status="succeeded",
            jobs=(DiscoveredJobDescription(name=title, url=url, text=normalized_text),),
        )
