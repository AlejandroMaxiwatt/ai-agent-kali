"""Selección del backend de memoria compartida."""

from __future__ import annotations

from .store import Store


def make_store(backend: str = "sqlite", path: str | None = None,
               dsn: str | None = None):
    """Devuelve un Store SQLite o PostgreSQL.

    - `sqlite` (default): local-first, sin dependencias.
    - `postgres`: requiere `psycopg2-binary` y un servidor accesible.
    """
    backend = (backend or "sqlite").strip().lower()
    if backend in ("postgres", "postgresql", "pg"):
        from .postgres_store import PostgresStore
        return PostgresStore(dsn or path or "")
    if backend not in ("sqlite", "local", "default"):
        raise ValueError(
            f"backend de store desconocido: {backend!r} "
            f"(usa 'sqlite' o 'postgres')"
        )
    if not path:
        raise ValueError("el backend sqlite necesita un path")
    return Store(path)
