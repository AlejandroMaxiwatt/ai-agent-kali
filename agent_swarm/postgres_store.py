"""Adaptador PostgreSQL con la misma API que `Store` (SQLite).

Reutiliza toda la lógica de `Store` mediante un wrapper de conexión que
traduce los placeholders `?` a `%s` y devuelve filas tipo dict. Solo se
sobrescriben las operaciones que dependen del dialecto:
- creación del schema (`SERIAL`, sin PRAGMA),
- `INSERT ... RETURNING id` (no hay `lastrowid`),
- `claim_task` atómico con `FOR UPDATE SKIP LOCKED`.

Uso:
    from agent_swarm.postgres_store import PostgresStore
    store = PostgresStore("postgresql://user:pass@host:5432/db")

Requiere `psycopg2-binary` (opcional; no se importa en el flujo SQLite).
"""

from __future__ import annotations

import json
import threading

import psycopg2
from psycopg2.extras import RealDictCursor

from .store import Store, _now


class _PGConnWrapper:
    """Mimetiza la parte de `sqlite3.Connection` que usa `Store`."""

    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor(cursor_factory=RealDictCursor)

    def execute(self, sql, params=()):
        self.cur.execute(sql.replace("?", "%s"), params)
        return self.cur

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        try:
            self.cur.close()
        finally:
            self.conn.close()


_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        role TEXT NOT NULL,
        status TEXT NOT NULL,
        last_seen TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS tasks (
        id SERIAL PRIMARY KEY,
        role TEXT NOT NULL,
        kind TEXT NOT NULL,
        target TEXT,
        command TEXT,
        finding_id INTEGER,
        priority INTEGER NOT NULL DEFAULT 5,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        started_at TEXT DEFAULT '',
        finished_at TEXT DEFAULT '',
        payload TEXT DEFAULT '{}',
        result TEXT DEFAULT '',
        rc INTEGER,
        agent TEXT DEFAULT '',
        attempts INTEGER NOT NULL DEFAULT 0,
        fingerprint TEXT DEFAULT ''
    )""",
    """CREATE INDEX IF NOT EXISTS idx_tasks_claim
       ON tasks(role, status, priority, id)""",
    """CREATE INDEX IF NOT EXISTS idx_tasks_fingerprint
       ON tasks(fingerprint, created_at)""",
    """CREATE TABLE IF NOT EXISTS assets (
        id SERIAL PRIMARY KEY,
        target TEXT,
        host TEXT NOT NULL,
        port INTEGER,
        service TEXT DEFAULT '',
        version TEXT DEFAULT '',
        source TEXT DEFAULT '',
        confidence REAL DEFAULT 0.5,
        created_at TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS idx_assets_target ON assets(target)""",
    """CREATE INDEX IF NOT EXISTS idx_assets_host ON assets(host)""",
    """CREATE TABLE IF NOT EXISTS findings (
        id SERIAL PRIMARY KEY,
        target TEXT,
        title TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'info',
        status TEXT NOT NULL DEFAULT 'pending_validation',
        claim TEXT DEFAULT '',
        evidence TEXT DEFAULT '',
        confidence REAL DEFAULT 0.0,
        created_by TEXT DEFAULT 'main',
        validated_by TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        validated_at TEXT DEFAULT ''
    )""",
    """CREATE INDEX IF NOT EXISTS idx_findings_status
       ON findings(status, created_at)""",
    """CREATE TABLE IF NOT EXISTS evidence (
        id SERIAL PRIMARY KEY,
        finding_id INTEGER REFERENCES findings(id),
        task_id INTEGER,
        path TEXT DEFAULT '',
        sha256 TEXT DEFAULT '',
        excerpt TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS idx_evidence_finding
       ON evidence(finding_id)""",
    """CREATE TABLE IF NOT EXISTS decisions (
        id SERIAL PRIMARY KEY,
        finding_id INTEGER,
        task_id INTEGER,
        agent TEXT DEFAULT '',
        decision TEXT NOT NULL,
        reason TEXT DEFAULT '',
        policy TEXT DEFAULT '{}',
        created_at TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS idx_decisions_finding
       ON decisions(finding_id)""",
    """CREATE TABLE IF NOT EXISTS events (
        id SERIAL PRIMARY KEY,
        ts TEXT NOT NULL,
        type TEXT NOT NULL,
        agent TEXT DEFAULT '',
        task_id INTEGER,
        payload TEXT DEFAULT '{}'
    )""",
    """CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)""",
    """CREATE TABLE IF NOT EXISTS blocks (
        id SERIAL PRIMARY KEY,
        target TEXT NOT NULL,
        reason TEXT DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS idx_blocks_target
       ON blocks(target, active)""",
]


class PostgresStore(Store):
    """Store respaldado por PostgreSQL."""

    def __init__(self, dsn: str):
        if not dsn:
            raise ValueError("PostgresStore requiere un DSN")
        self.dsn = dsn
        self.path = dsn
        self._lock = threading.RLock()
        self.event_bus = None
        self._conn = _PGConnWrapper(psycopg2.connect(dsn))
        self._conn.conn.autocommit = False
        with self._lock:
            self._create_schema()

    def _create_schema(self):
        for stmt in _SCHEMA:
            self._conn.execute(stmt)
        self._conn.commit()

    # ------------------------------------------------------------------
    # INSERT ... RETURNING id
    # ------------------------------------------------------------------
    def enqueue_task(self, role, kind="command", target=None, command=None,
                     finding_id=None, priority=5, payload=None,
                     fingerprint="") -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO tasks
                   (role, kind, target, command, finding_id, priority,
                    status, created_at, payload, fingerprint)
                   VALUES(?,?,?,?,?,?, 'pending', ?,?,?)
                   RETURNING id""",
                (role, kind, target, command, finding_id, int(priority),
                 _now(), json.dumps(payload or {}),
                 fingerprint),
            )
            row = cur.fetchone()
            self._conn.commit()
            return int(row["id"])

    def claim_task(self, role: str, agent: str = ""):
        """Reclama una tarea con FOR UPDATE SKIP LOCKED (multi-proceso)."""
        now = _now()
        with self._lock:
            try:
                cur = self._conn.execute(
                    """UPDATE tasks
                       SET status='running', started_at=?, attempts=attempts+1,
                           agent=?
                       WHERE id = (
                           SELECT id FROM tasks
                           WHERE role=? AND status='pending'
                           ORDER BY priority ASC, id ASC
                           LIMIT 1 FOR UPDATE SKIP LOCKED
                       )
                       RETURNING *""",
                    (now, agent, role),
                )
                row = cur.fetchone()
                self._conn.commit()
                if row is None:
                    return None
                return self._row_to_task(row)
            except Exception:
                self._conn.rollback()
                raise

    def add_asset(self, target, host, port=None, service="", version="",
                  source="", confidence=0.5) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO assets
                   (target, host, port, service, version, source,
                    confidence, created_at)
                   VALUES(?,?,?,?,?,?,?,?)
                   RETURNING id""",
                (target, host, port, service, version, source,
                 float(confidence), _now()),
            )
            row = cur.fetchone()
            self._conn.commit()
            return int(row["id"])

    def add_finding(self, target, title, severity="info",
                    status="pending_validation", claim="", evidence="",
                    confidence=0.0, created_by="main") -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO findings
                   (target, title, severity, status, claim, evidence,
                    confidence, created_by, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   RETURNING id""",
                (target, title, severity, status, claim, evidence,
                 float(confidence), created_by, _now()),
            )
            row = cur.fetchone()
            self._conn.commit()
            return int(row["id"])

    def add_evidence(self, finding_id, task_id, path="", sha256="",
                     excerpt="") -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO evidence
                   (finding_id, task_id, path, sha256, excerpt, created_at)
                   VALUES(?,?,?,?,?,?)
                   RETURNING id""",
                (finding_id, task_id, path, sha256,
                 (excerpt or "")[:8000], _now()),
            )
            row = cur.fetchone()
            self._conn.commit()
            return int(row["id"])

    def add_decision(self, finding_id=None, task_id=None, agent="",
                     decision="", reason="", policy=None) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO decisions
                   (finding_id, task_id, agent, decision, reason, policy,
                    created_at)
                   VALUES(?,?,?,?,?,?,?)
                   RETURNING id""",
                (finding_id, task_id, agent, decision, reason,
                 json.dumps(policy or {}), _now()),
            )
            row = cur.fetchone()
            self._conn.commit()
            return int(row["id"])

    def add_event(self, type_: str, agent: str = "", task_id=None,
                  payload=None) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO events(ts, type, agent, task_id, payload)
                   VALUES(?,?,?,?,?)
                   RETURNING id""",
                (_now(), type_, agent, task_id,
                 json.dumps(payload or {})),
            )
            row = cur.fetchone()
            self._conn.commit()
            event_id = int(row["id"])
        if self.event_bus is not None:
            try:
                self.event_bus.publish(type_, payload or {},
                                       agent=agent, task_id=task_id)
            except Exception:
                pass
        return event_id

    def add_block(self, target: str, reason: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO blocks(target, reason, active, created_at)
                   VALUES(?,?,1,?)
                   RETURNING id""",
                (target, reason, _now()),
            )
            row = cur.fetchone()
            self._conn.commit()
            return int(row["id"])

    def close(self):
        with self._lock:
            try:
                self._conn.commit()
                self._conn.close()
            except Exception:
                pass
