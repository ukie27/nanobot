"""Application-material use-case orchestration."""

from __future__ import annotations

from typing import Any

from nanobot.career.application.ports.material_gateway import MaterialGateway
from nanobot.career.domain.materials import MaterialType


class MaterialApplicationService:
    def __init__(self, gateway: MaterialGateway) -> None:
        self.gateway = gateway

    def generate(
        self,
        *,
        job_post_id: str,
        material_type: MaterialType,
        name: str,
        resume_id: str | None = None,
    ) -> dict[str, Any]:
        return self.gateway.create_material(
            job_post_id=job_post_id,
            material_type=material_type,
            name=name,
            resume_id=resume_id,
        )

    def edit(
        self, material_id: str, *, expected_version: int, blocks: list[dict[str, str]]
    ) -> dict[str, Any]:
        return self.gateway.edit_material(
            material_id, expected_version=expected_version, blocks=blocks
        )

    def review(self, material_id: str) -> dict[str, Any]:
        return self.gateway.review_material(material_id)

    def finalize(self, material_id: str, *, expected_version: int) -> dict[str, Any]:
        return self.gateway.finalize_material(material_id, expected_version=expected_version)
