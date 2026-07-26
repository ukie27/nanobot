"""Verified, portable CareerConsole workspace archives."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from career_console.infrastructure.configuration.schema import ConfigurationDocument
from career_console.infrastructure.workspace.manager import (
    WorkspaceManager,
    WorkspaceManifest,
    WorkspacePaths,
)

ARCHIVE_SCHEMA = "career-console.portable.v1"
VAULT_SCHEMA = "career-console.secret-vault.v1"
VAULT_AAD = b"CareerConsole portable secret vault v1"
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_MEMBER_COUNT = 10_000
MAX_COMPRESSION_RATIO = 200
PBKDF2_ITERATIONS = 600_000


class PortableWorkspaceError(ValueError):
    """A safe, user-facing portable archive validation error."""


class PortableWorkspaceService:
    def __init__(
        self, *, root: Path, secret_store: Any, manager: WorkspaceManager,
        database_head: str,
    ) -> None:
        self.paths = WorkspacePaths(root.resolve())
        self.secret_store = secret_store
        self.manager = manager
        self.database_head = database_head

    def export(self, *, include_secrets: bool = False, passphrase: str | None = None) -> dict[str, Any]:
        if include_secrets and (passphrase is None or len(passphrase) < 12):
            raise PortableWorkspaceError("导出凭据时必须提供至少 12 个字符的密码。")
        self.paths.exports.mkdir(parents=True, exist_ok=True)
        self.paths.runtime.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        filename = f"CareerConsole-{stamp}-{uuid4().hex[:8]}.ccworkspace"
        final_path = self.paths.exports / filename
        temporary_path = self.paths.runtime / f".{filename}.tmp"
        staging = Path(tempfile.mkdtemp(prefix="portable-export-", dir=self.paths.runtime))
        try:
            database = staging / "career-console.sqlite3"
            self._snapshot_database(database)
            sources = self._export_sources(database)
            if include_secrets:
                vault = staging / "vault.enc"
                vault.write_bytes(self._encrypt_secrets(passphrase or ""))
                sources["workspace/secrets/vault.enc"] = vault
            files = []
            total_size = 0
            with zipfile.ZipFile(
                temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
            ) as archive:
                for archive_name, source in sorted(sources.items()):
                    digest, size = _hash_file(source)
                    if size > MAX_MEMBER_BYTES:
                        raise PortableWorkspaceError(
                            f"工作区文件超过 512 MiB 限制：{archive_name}"
                        )
                    total_size += size
                    if total_size > MAX_ARCHIVE_BYTES:
                        raise PortableWorkspaceError("工作区数据超过 2 GiB 导出限制。")
                    files.append({"path": archive_name, "sha256": digest, "size": size})
                    archive.write(source, archive_name)
                manifest = {
                    "schemaVersion": ARCHIVE_SCHEMA,
                    "product": "CareerConsole",
                    "createdAt": datetime.now(UTC).isoformat(),
                    "databaseRevision": _database_revision(database),
                    "secrets": "encrypted" if include_secrets else "excluded",
                    "files": files,
                }
                archive.writestr(
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                )
            os.replace(temporary_path, final_path)
            digest, size = _hash_file(final_path)
            return {
                "filename": filename,
                "path": str(final_path),
                "sha256": digest,
                "size_bytes": size,
                "file_count": len(files),
                "secrets_included": include_secrets,
                "download_url": f"/api/v1/workspace/portable-exports/{filename}",
            }
        finally:
            temporary_path.unlink(missing_ok=True)
            shutil.rmtree(staging, ignore_errors=True)

    def import_archive(
        self, *, archive_path: Path, parent: Path, passphrase: str | None = None,
    ) -> dict[str, Any]:
        archive_path = archive_path.resolve(strict=True)
        if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise PortableWorkspaceError("工作区归档超过 2 GiB 限制。")
        check = self.manager.validate_parent(parent)
        if not check["valid"]:
            raise PortableWorkspaceError(str(check["error"]))
        target = Path(check["workspace_path"])
        if target.exists() and any(target.iterdir()):
            raise PortableWorkspaceError("导入目标必须不存在或为空。")
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.parent / f".CareerConsole-import-{uuid4().hex}"
        restored_secrets: dict[str, str] = {}
        previous_secrets: dict[str, str | None] = {}
        updated_secret_refs: list[str] = []
        completed = False
        try:
            staging.mkdir()
            manifest = self._extract_verified(archive_path, staging)
            workspace_paths = WorkspacePaths(staging)
            try:
                workspace_manifest = WorkspaceManifest.model_validate_json(
                    workspace_paths.manifest.read_text(encoding="utf-8")
                )
                ConfigurationDocument.model_validate_json(
                    (workspace_paths.config / "application.json").read_text(encoding="utf-8")
                )
            except (OSError, ValueError) as exc:
                raise PortableWorkspaceError("归档中的工作区或配置文件无效。") from exc
            self._validate_database(workspace_paths.database, manifest)
            vault_path = workspace_paths.secrets / "vault.enc"
            if manifest["secrets"] == "encrypted":
                if passphrase is None:
                    raise PortableWorkspaceError("该归档包含加密凭据，请输入导出密码。")
                restored_secrets = self._decrypt_secrets(
                    vault_path.read_bytes(), passphrase, workspace_manifest.workspace_id
                )
                vault_path.unlink()
            for directory in workspace_paths.directories()[1:]:
                directory.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.rmdir()
            shutil.copytree(staging, target)
            for reference, secret in restored_secrets.items():
                try:
                    previous_secrets[reference] = self.secret_store.get(reference)
                except LookupError:
                    previous_secrets[reference] = None
                self.secret_store.set(reference, secret)
                updated_secret_refs.append(reference)
            self.manager.registry.activate(target, workspace_manifest.workspace_id)
            completed = True
            return {
                "workspace_path": str(target),
                "workspace_id": workspace_manifest.workspace_id,
                "database_revision": manifest["databaseRevision"],
                "secrets_restored": len(restored_secrets),
                "restart_required": target != self.paths.root,
            }
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            if not completed:
                shutil.rmtree(target, ignore_errors=True)
                for reference in reversed(updated_secret_refs):
                    try:
                        previous = previous_secrets[reference]
                        if previous is None:
                            self.secret_store.delete(reference)
                        else:
                            self.secret_store.set(reference, previous)
                    except Exception:
                        continue

    def resolve_export(self, filename: str) -> Path:
        if not filename.endswith(".ccworkspace") or Path(filename).name != filename:
            raise FileNotFoundError(filename)
        path = (self.paths.exports / filename).resolve(strict=True)
        if path.parent != self.paths.exports.resolve():
            raise FileNotFoundError(filename)
        return path

    def _snapshot_database(self, destination: Path) -> None:
        if not self.paths.database.is_file():
            raise PortableWorkspaceError("当前工作区数据库不存在。")
        with sqlite3.connect(self.paths.database) as source:
            with sqlite3.connect(destination) as target:
                source.backup(target)

    def _export_sources(self, database: Path) -> dict[str, Path]:
        sources = {
            "workspace/workspace.json": self.paths.manifest,
            "workspace/data/career-console.sqlite3": database,
        }
        for directory_name in ("config", "blobs", "integrations"):
            directory = self.paths.root / directory_name
            if not directory.exists():
                continue
            for root, directories, files in os.walk(directory, followlinks=False):
                root_path = Path(root)
                unsafe = [name for name in [*directories, *files] if _is_link(root_path / name)]
                if unsafe:
                    raise PortableWorkspaceError(
                        f"工作区包含不允许导出的链接或重解析点：{directory_name}/{unsafe[0]}"
                    )
                for name in files:
                    source = root_path / name
                    relative = source.relative_to(self.paths.root).as_posix()
                    sources[f"workspace/{relative}"] = source
        return sources

    def _encrypt_secrets(self, passphrase: str) -> bytes:
        document = ConfigurationDocument.model_validate_json(
            (self.paths.config / "application.json").read_text(encoding="utf-8")
        )
        references = sorted(_secret_references(document.model_dump(mode="json")))
        values: dict[str, str] = {}
        for reference in references:
            try:
                values[reference] = self.secret_store.get(reference)
            except LookupError:
                continue
        plaintext = json.dumps(
            {"schemaVersion": VAULT_SCHEMA, "secrets": values},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode()
        salt, nonce = os.urandom(16), os.urandom(12)
        key = _derive_key(passphrase, salt)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, VAULT_AAD)
        envelope = {
            "schemaVersion": VAULT_SCHEMA,
            "kdf": "PBKDF2-HMAC-SHA256",
            "iterations": PBKDF2_ITERATIONS,
            "cipher": "AES-256-GCM",
            "salt": base64.b64encode(salt).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
        return (json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n").encode()

    def _decrypt_secrets(
        self, encoded: bytes, passphrase: str, workspace_id: str,
    ) -> dict[str, str]:
        try:
            envelope = json.loads(encoded)
            if (
                envelope["schemaVersion"] != VAULT_SCHEMA
                or envelope["iterations"] != PBKDF2_ITERATIONS
            ):
                raise PortableWorkspaceError("不支持的加密 Vault 格式。")
            salt = base64.b64decode(envelope["salt"], validate=True)
            nonce = base64.b64decode(envelope["nonce"], validate=True)
            ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
            plaintext = AESGCM(_derive_key(passphrase, salt)).decrypt(
                nonce, ciphertext, VAULT_AAD
            )
            payload = json.loads(plaintext)
        except PortableWorkspaceError:
            raise
        except Exception as exc:
            raise PortableWorkspaceError("Vault 密码错误或加密内容已损坏。") from exc
        secrets = payload.get("secrets")
        prefix = f"career-console:{workspace_id}:"
        if payload.get("schemaVersion") != VAULT_SCHEMA or not isinstance(secrets, dict):
            raise PortableWorkspaceError("加密 Vault 内容无效。")
        if any(
            not isinstance(reference, str) or not reference.startswith(prefix)
            or not isinstance(secret, str) or not secret
            for reference, secret in secrets.items()
        ):
            raise PortableWorkspaceError("Vault 包含不属于该工作区的凭据引用。")
        return secrets

    def _extract_verified(self, source: Path, staging: Path) -> dict[str, Any]:
        try:
            with zipfile.ZipFile(source) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_MEMBER_COUNT + 1:
                    raise PortableWorkspaceError("归档文件数量超过限制。")
                names = [item.filename for item in infos]
                if len(names) != len(set(names)):
                    raise PortableWorkspaceError("归档包含重复路径。")
                if "manifest.json" not in names:
                    raise PortableWorkspaceError("归档缺少 manifest.json。")
                manifest_info = archive.getinfo("manifest.json")
                if manifest_info.file_size > 2 * 1024 * 1024:
                    raise PortableWorkspaceError("归档 manifest 过大。")
                manifest = json.loads(archive.read(manifest_info))
                self._validate_manifest(manifest)
                expected = {item["path"]: item for item in manifest["files"]}
                if set(names) != {*expected, "manifest.json"}:
                    raise PortableWorkspaceError("归档文件列表与 manifest 不一致。")
                total = 0
                for info in infos:
                    if info.filename == "manifest.json":
                        continue
                    _validate_member(info)
                    metadata = expected[info.filename]
                    if info.file_size != metadata["size"]:
                        raise PortableWorkspaceError(f"归档大小校验失败：{info.filename}")
                    total += info.file_size
                    if total > MAX_ARCHIVE_BYTES:
                        raise PortableWorkspaceError("归档解压后大小超过 2 GiB 限制。")
                    relative = PurePosixPath(info.filename).relative_to("workspace")
                    destination = staging.joinpath(*relative.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    with archive.open(info) as reader, destination.open("wb") as writer:
                        while chunk := reader.read(1024 * 1024):
                            digest.update(chunk)
                            writer.write(chunk)
                    if digest.hexdigest() != metadata["sha256"]:
                        raise PortableWorkspaceError(f"归档哈希校验失败：{info.filename}")
                return manifest
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, TypeError) as exc:
            raise PortableWorkspaceError("工作区归档格式无效。") from exc

    def _validate_manifest(self, manifest: dict[str, Any]) -> None:
        if manifest.get("schemaVersion") != ARCHIVE_SCHEMA:
            raise PortableWorkspaceError("不支持的工作区归档版本。")
        if manifest.get("product") != "CareerConsole":
            raise PortableWorkspaceError("归档不属于 CareerConsole。")
        revision = manifest.get("databaseRevision")
        if not isinstance(revision, str) or not revision or len(revision) > 100:
            raise PortableWorkspaceError("归档数据库 revision 无效。")
        if manifest.get("secrets") not in {"excluded", "encrypted"}:
            raise PortableWorkspaceError("归档的凭据模式无效。")
        files = manifest.get("files")
        if not isinstance(files, list) or not files or len(files) > MAX_MEMBER_COUNT:
            raise PortableWorkspaceError("归档文件清单无效。")
        for item in files:
            if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
                raise PortableWorkspaceError("归档文件清单无效。")
            _validate_archive_path(item["path"])
            if (
                not isinstance(item["sha256"], str) or len(item["sha256"]) != 64
                or not isinstance(item["size"], int) or not 0 <= item["size"] <= MAX_MEMBER_BYTES
            ):
                raise PortableWorkspaceError("归档文件元数据无效。")
        required = {
            "workspace/workspace.json", "workspace/config/application.json",
            "workspace/data/career-console.sqlite3",
        }
        paths = {item["path"] for item in files}
        if not required.issubset(paths):
            raise PortableWorkspaceError("归档缺少必要工作区文件。")
        vault = "workspace/secrets/vault.enc"
        if (manifest["secrets"] == "encrypted") != (vault in paths):
            raise PortableWorkspaceError("归档 Vault 状态与文件清单不一致。")

    def _validate_database(self, path: Path, manifest: dict[str, Any]) -> None:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
        revision = _database_revision(path)
        if result is None or result[0] != "ok":
            raise PortableWorkspaceError("归档数据库未通过 SQLite quick_check。")
        if revision != manifest.get("databaseRevision"):
            raise PortableWorkspaceError("归档数据库 revision 与 manifest 不一致。")
        if revision and revision > self.database_head:
            raise PortableWorkspaceError("归档由更高版本的 CareerConsole 创建，请先升级应用。")


def _validate_archive_path(value: Any) -> None:
    if not isinstance(value, str) or "\\" in value:
        raise PortableWorkspaceError("归档包含不安全路径。")
    path = PurePosixPath(value)
    if (
        path.is_absolute() or not path.parts or path.parts[0] != "workspace"
        or ".." in path.parts or path.as_posix() != value
        or any(":" in part or "\x00" in part for part in path.parts)
    ):
        raise PortableWorkspaceError("归档包含不安全路径。")


def _validate_member(info: zipfile.ZipInfo) -> None:
    _validate_archive_path(info.filename)
    if info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:
        raise PortableWorkspaceError("归档不允许目录项或符号链接。")
    if info.file_size > MAX_MEMBER_BYTES:
        raise PortableWorkspaceError("归档单个文件超过 512 MiB 限制。")
    if info.compress_size == 0 and info.file_size > 0:
        raise PortableWorkspaceError("归档包含异常压缩成员。")
    if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise PortableWorkspaceError("归档包含异常压缩比成员。")


def _hash_file(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _database_revision(path: Path) -> str | None:
    try:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            ).fetchone()
            if table is None:
                return None
            row = connection.execute(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ).fetchone()
            return str(row[0]) if row else None
    except sqlite3.Error:
        return None


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS,
    ).derive(passphrase.encode("utf-8"))


def _secret_references(value: Any) -> set[str]:
    references: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "secret_ref" and isinstance(item, str):
                references.add(item)
            else:
                references.update(_secret_references(item))
    elif isinstance(value, list):
        for item in value:
            references.update(_secret_references(item))
    return references


def _is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(path))
