from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_DOMAIN_ROOTS = {
    "alembic",
    "fastapi",
    "nanobot.agent",
    "nanobot.api",
    "nanobot.career.api",
    "nanobot.career.infrastructure",
    "sqlalchemy",
}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_domain_does_not_depend_on_framework_or_infrastructure() -> None:
    domain = Path("nanobot/career/domain")
    violations: list[str] = []
    for path in domain.rglob("*.py"):
        for module in imported_modules(path):
            if any(
                module == root or module.startswith(f"{root}.") for root in FORBIDDEN_DOMAIN_ROOTS
            ):
                violations.append(f"{path}: {module}")
    assert violations == []
