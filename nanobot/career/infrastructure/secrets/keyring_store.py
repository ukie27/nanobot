"""SecretStore implementations."""

from __future__ import annotations


class KeyringSecretStore:
    """Store credentials in the user's OS credential vault, never in SQLite."""

    SERVICE = "nanobot-career"

    @staticmethod
    def _keyring():
        try:
            import keyring
        except ImportError as exc:  # pragma: no cover - installation guard
            raise RuntimeError("缺少 keyring 依赖，无法安全保存邮箱授权码。") from exc
        return keyring

    def set(self, reference: str, secret: str) -> None:
        if not secret:
            raise ValueError("邮箱授权码不能为空。")
        self._keyring().set_password(self.SERVICE, reference, secret)

    def get(self, reference: str) -> str:
        value = self._keyring().get_password(self.SERVICE, reference)
        if not value:
            raise LookupError("邮箱授权码不存在或已从系统凭据库删除。")
        return value

    def delete(self, reference: str) -> None:
        keyring = self._keyring()
        try:
            keyring.delete_password(self.SERVICE, reference)
        except keyring.errors.PasswordDeleteError:
            pass


class InMemorySecretStore:
    """Explicit test double; never selected by production wiring."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, reference: str, secret: str) -> None:
        self.values[reference] = secret

    def get(self, reference: str) -> str:
        try:
            return self.values[reference]
        except KeyError as exc:
            raise LookupError("Secret not found.") from exc

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)
