"""Deterministic Career application.

The legacy :class:`CareerStore` remains importable from ``nanobot.career.store``
while the replacement architecture is delivered module by module. It is not
re-exported here so new code cannot accidentally build on the legacy store.
"""

__all__: list[str] = []
