"""Workspace integration and local data-governance orchestration."""

from __future__ import annotations

from typing import Any


class GovernanceApplicationService:
    def __init__(self, gateway) -> None:
        self.gateway = gateway

    def overview(self) -> dict[str, Any]:
        return self.gateway.overview()

    def search(self, query: str) -> list[dict[str, Any]]:
        return self.gateway.search(query=query)

    def review_queue(self) -> list[dict[str, Any]]:
        return self.gateway.review_queue()

    def integration_health(self) -> dict[str, Any]:
        return self.gateway.integration_health()

    def create_backup(self) -> dict[str, Any]:
        return self.gateway.create_backup_bundle()

    def export_data(self) -> dict[str, Any]:
        return self.gateway.export_user_data()

    def garbage_collect(self) -> dict[str, Any]:
        return self.gateway.garbage_collect()

    def delete_connector(self, connector_type: str, *, confirmation: str) -> dict[str, Any]:
        if confirmation != f"DELETE {connector_type}":
            raise ValueError(f"请输入 DELETE {connector_type} 以确认删除。")
        return self.gateway.delete_connector_data(connector_type)

    def delete_all(self, *, confirmation: str) -> dict[str, Any]:
        if confirmation != "DELETE ALL CAREER DATA":
            raise ValueError("请输入 DELETE ALL CAREER DATA 以确认删除。")
        return self.gateway.delete_all_personal_data()
