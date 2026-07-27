from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_console.infrastructure.configuration.schema import (
    ConfigurationUpdate,
    ProviderConfiguration,
)
from career_console.infrastructure.database.migrations import head_revision
from career_console.infrastructure.secrets import InMemorySecretStore
from career_console.infrastructure.settings import CareerSettings
from career_console.infrastructure.workspace import (
    BootstrapRegistry,
    PortableWorkspaceError,
    PortableWorkspaceService,
    WorkspaceManager,
)
from career_console.interfaces.http import create_app


def _portable_service(client: TestClient, tmp_path: Path) -> tuple[PortableWorkspaceService, InMemorySecretStore, WorkspaceManager]:
    secrets = InMemorySecretStore()
    manager = WorkspaceManager(BootstrapRegistry(tmp_path / "machine" / "bootstrap.json"))
    service = PortableWorkspaceService(
        root=client.app.state.settings.data_dir,
        secret_store=secrets,
        manager=manager,
        database_head=head_revision(client.app.state.settings),
    )
    return service, secrets, manager


def test_portable_workspace_round_trip_without_secrets(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "source")
    with TestClient(create_app(settings)) as client:
        service, _, manager = _portable_service(client, tmp_path)
        exported = service.export()
        archive_path = Path(exported["path"])
        assert exported["secrets_included"] is False
        assert exported["download_url"].endswith(".ccworkspace")
        with zipfile.ZipFile(archive_path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["schemaVersion"] == "career-console.portable.v1"
            assert manifest["secrets"] == "excluded"
            assert "workspace/secrets/vault.enc" not in archive.namelist()

        imported = service.import_archive(
            archive_path=archive_path, parent=tmp_path / "restored"
        )
        target = tmp_path / "restored" / "CareerConsole"
        assert imported["workspace_path"] == str(target.resolve())
        assert imported["secrets_restored"] == 0
        assert imported["restart_required"] is True
        assert (target / "data" / "career-console.sqlite3").is_file()
        assert manager.registry.active_workspace() is None
        assert manager.registry.pending_workspace() == target.resolve()


def test_portable_workspace_encrypts_and_restores_referenced_secrets(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "source")
    with TestClient(create_app(settings)) as client:
        service, secrets, _ = _portable_service(client, tmp_path)
        configuration_service = client.app.state.configuration_service
        document = configuration_service.store.load()
        workspace_id = json.loads(
            (settings.data_dir / "workspace.json").read_text(encoding="utf-8")
        )["workspaceId"]
        reference = f"career-console:{workspace_id}:provider:main:api-key"
        updated = document.configuration.model_copy(deep=True)
        updated.providers["main"] = ProviderConfiguration(
            provider_type="openai", display_name="Main", default_model="gpt-test",
            secret_ref=reference,
        )
        configuration_service.update(ConfigurationUpdate(
            expected_revision=document.revision,
            reason="portable test",
            configuration=updated,
        ))
        secrets.set(reference, "top-secret-value")

        exported = service.export(
            include_secrets=True, passphrase="correct horse battery staple"
        )
        archive_path = Path(exported["path"])
        assert b"top-secret-value" not in archive_path.read_bytes()
        secrets.delete(reference)
        imported = service.import_archive(
            archive_path=archive_path,
            parent=tmp_path / "encrypted-restore",
            passphrase="correct horse battery staple",
        )
        assert imported["secrets_restored"] == 1
        assert secrets.get(reference) == "top-secret-value"


def test_portable_workspace_rejects_wrong_password_and_zip_slip(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "source")
    with TestClient(create_app(settings)) as client:
        service, _, _ = _portable_service(client, tmp_path)
        exported = service.export(include_secrets=True, passphrase="valid-long-password")
        with pytest.raises(PortableWorkspaceError, match="密码错误|已损坏"):
            service.import_archive(
                archive_path=Path(exported["path"]),
                parent=tmp_path / "wrong-password",
                passphrase="wrong-long-password",
            )
        assert not (tmp_path / "wrong-password" / "CareerConsole").exists()

        malicious = tmp_path / "zip-slip.ccworkspace"
        manifest = {
            "schemaVersion": "career-console.portable.v1",
            "product": "CareerConsole",
            "databaseRevision": "20260726_0026",
            "secrets": "excluded",
            "files": [{"path": "workspace/../outside.txt", "sha256": "0" * 64, "size": 0}],
        }
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("workspace/../outside.txt", b"")
        with pytest.raises(PortableWorkspaceError, match="不安全路径"):
            service.import_archive(
                archive_path=malicious, parent=tmp_path / "zip-slip-target"
            )
        assert not (tmp_path / "outside.txt").exists()


def test_portable_workspace_rejects_hash_tampering(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "source")
    with TestClient(create_app(settings)) as client:
        service, _, _ = _portable_service(client, tmp_path)
        original = Path(service.export()["path"])
        tampered = tmp_path / "tampered.ccworkspace"
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(tampered, "w") as target:
            for info in source.infolist():
                content = source.read(info)
                if info.filename == "workspace/workspace.json":
                    content += b" "
                target.writestr(info, content)
        with pytest.raises(PortableWorkspaceError, match="大小校验|哈希校验"):
            service.import_archive(
                archive_path=tampered, parent=tmp_path / "tampered-target"
            )


def test_portable_workspace_api_exports_downloadable_archive(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "source")
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/workspace/portable-export", json={
            "include_secrets": False, "passphrase": None,
        })
        assert response.status_code == 200, response.text
        payload = response.json()
        downloaded = client.get(payload["download_url"])
        assert downloaded.status_code == 200
        assert downloaded.content.startswith(b"PK")

        manager = WorkspaceManager(BootstrapRegistry(tmp_path / "api-machine" / "bootstrap.json"))
        client.app.state.portable_workspace.manager = manager
        imported = client.post(
            "/api/v1/workspace/portable-import",
            data={"parent_directory": str(tmp_path / "api-restored")},
            files={"file": (payload["filename"], downloaded.content, "application/zip")},
        )
        assert imported.status_code == 200, imported.text
        assert imported.json()["restart_required"] is True
        assert manager.registry.pending_workspace() == (
            tmp_path / "api-restored" / "CareerConsole"
        ).resolve()
