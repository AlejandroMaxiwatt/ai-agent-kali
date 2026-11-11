"""Memoria compartida y cola de tareas del enjambre (SQLite).

Diseño local-first: un único fichero SQLite en `memory/swarm/swarm.db`.
No requiere PostgreSQL/Redis para funcionar. La interfaz está pensada para
poder sustituirse por un backend distribuido más adelante.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from .models import (Asset, Decision, Evidence, Finding, Task)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _loads(value, default):
    try:
        return json.loads(value) if value else default
    except Exception:
        return default


class Store:
    """Almacén thread-safe de tareas, hallazgos, evidencias y eventos."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock = threading.RLock()
        # Bus de eventos opcional (Redis Streams, etc.). Si es None, los
        # eventos solo se persisten en SQLite.
        self.event_bus = None
        self._conn = sqlite3.connect(
            self.path, check_same_thread=False, timeout=15,
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=15000")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._create_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def _create_schema(self):
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            status TEXT NOT NULL,
            last_seen TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_claim
            ON tasks(role, status, priority, id);
        CREATE INDEX IF NOT EXISTS idx_tasks_fingerprint
            ON tasks(fingerprint, created_at);

        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT,
            host TEXT NOT NULL,
            port INTEGER,
            service TEXT DEFAULT '',
            version TEXT DEFAULT '',
            source TEXT DEFAULT '',
            confidence REAL DEFAULT 0.5,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_assets_target ON assets(target);
        CREATE INDEX IF NOT EXISTS idx_assets_host ON assets(host);

        CREATE TABLE IF NOT EXISTS findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );
        CREATE INDEX IF NOT EXISTS idx_findings_status
            ON findings(status, created_at);

        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            finding_id INTEGER,
            task_id INTEGER,
            path TEXT DEFAULT '',
            sha256 TEXT DEFAULT '',
            excerpt TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(finding_id) REFERENCES findings(id)
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_finding
            ON evidence(finding_id);

        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            finding_id INTEGER,
            task_id INTEGER,
            agent TEXT DEFAULT '',
            decision TEXT NOT NULL,
            reason TEXT DEFAULT '',
            policy TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_decisions_finding
            ON decisions(finding_id);

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            type TEXT NOT NULL,
            agent TEXT DEFAULT '',
            task_id INTEGER,
            payload TEXT DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

        CREATE TABLE IF NOT EXISTS blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            reason TEXT DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_blocks_target
            ON blocks(target, active);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Agentes
    # ------------------------------------------------------------------
    def register_agent(self, agent_id: str, role: str, status: str = "running"):
        with self._lock:
            self._conn.execute(
                """INSERT INTO agents(id, role, status, last_seen)
                   VALUES(?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     role=excluded.role,
                     status=excluded.status,
                     last_seen=excluded.last_seen""",
                (agent_id, role, status, _now()),
            )
            self._conn.commit()

    def list_agents(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM agents ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Tareas
    # ------------------------------------------------------------------
    def enqueue_task(self, role: str, kind: str = "command", target=None,
                     command=None, finding_id=None, priority: int = 5,
                     payload=None, fingerprint: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO tasks
                   (role, kind, target, command, finding_id, priority, status,
                    created_at, payload, fingerprint)
                   VALUES(?,?,?,?,?,?, 'pending', ?,?,?)""",
                (role, kind, target, command, finding_id, int(priority),
                 _now(), _json(payload), fingerprint),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def claim_task(self, role: str, agent: str = "") -> Task | None:
        """Reclama atómicamente la tarea pendiente de mayor prioridad."""
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                row = self._conn.execute(
                    """SELECT * FROM tasks
                       WHERE role=? AND status='pending'
                       ORDER BY priority ASC, id ASC LIMIT 1""",
                    (role,),
                ).fetchone()
                if row is None:
                    self._conn.execute("COMMIT")
                    return None
                now = _now()
                self._conn.execute(
                    """UPDATE tasks SET status='running', started_at=?,
                       attempts=attempts+1, agent=?
                       WHERE id=?""",
                    (now, agent, row["id"]),
                )
                self._conn.execute("COMMIT")
                task = self._row_to_task(row)
                task.status = "running"
                task.started_at = now
                task.agent = agent
                task.attempts += 1
                return task
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def finish_task(self, task_id: int, status: str, result: str = "",
                    rc: int | None = None):
        with self._lock:
            # No sobrescribir una tarea cancelada por el operador.
            self._conn.execute(
                """UPDATE tasks SET status=?, result=?, rc=?, finished_at=?
                   WHERE id=? AND status<>'cancelled'""",
                (status, (result or "")[:20000], rc, _now(), task_id),
            )
            self._conn.commit()

    def cancel_task(self, task_id: int, reason: str = "") -> bool:
        """Cancela una tarea pendiente o marca una en ejecución.

        Para una tarea en ejecución no se puede matar el subproceso desde
        aquí (lo controla `run_command`), pero se marca como cancelada para
        que no se encole ningún seguimiento y no se sobrescriba el estado.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if row is None:
                return False
            if row["status"] in ("done", "failed", "blocked", "cancelled"):
                return False
            self._conn.execute(
                """UPDATE tasks SET status='cancelled', finished_at=?,
                   result=? WHERE id=?""",
                (_now(), f"cancelada: {reason}"[:2000], task_id),
            )
            self._conn.commit()
            return True

    def requeue_task(self, task_id: int):
        with self._lock:
            self._conn.execute(
                """UPDATE tasks SET status='pending', started_at='',
                   finished_at='' WHERE id=?""",
                (task_id,),
            )
            self._conn.commit()

    def get_task(self, task_id: int) -> Task | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
        return self._row_to_task(row) if row else None

    def list_tasks(self, role: str | None = None, status: str | None = None,
                   limit: int = 50) -> list[Task]:
        q = "SELECT * FROM tasks WHERE 1=1"
        args = []
        if role:
            q += " AND role=?"; args.append(role)
        if status:
            q += " AND status=?"; args.append(status)
        q += " ORDER BY id DESC LIMIT ?"; args.append(int(limit))
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [self._row_to_task(r) for r in rows]

    def find_duplicate(self, fingerprint: str, window_s: int = 3600,
                       exclude_task_id: int | None = None) -> Task | None:
        if not fingerprint:
            return None
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_s)
                  ).isoformat(timespec="seconds")
        q = """SELECT * FROM tasks
               WHERE fingerprint=? AND created_at>=?
                 AND status IN ('pending','running','done')"""
        args = [fingerprint, cutoff]
        if exclude_task_id is not None:
            q += " AND id<>?"; args.append(exclude_task_id)
        q += " ORDER BY id DESC LIMIT 1"
        with self._lock:
            row = self._conn.execute(q, args).fetchone()
        return self._row_to_task(row) if row else None

    def count_recent_tasks(self, target: str | None, tool: str,
                           window_s: int = 60) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_s)
                  ).isoformat(timespec="seconds")
        q = """SELECT COUNT(*) AS n FROM tasks
               WHERE created_at>=? AND command LIKE ?"""
        args = [cutoff, f"%{tool}%"]
        if target:
            q += " AND target=?"; args.append(target)
        with self._lock:
            row = self._conn.execute(q, args).fetchone()
        return int(row["n"]) if row else 0

    def task_stats(self) -> dict:
        with self._lock:
            rows = self._conn.execute(
                """SELECT role, status, COUNT(*) AS n
                   FROM tasks GROUP BY role, status"""
            ).fetchall()
        out: dict = {}
        for r in rows:
            out.setdefault(r["role"], {})[r["status"]] = int(r["n"])
        return out

    # ------------------------------------------------------------------
    # Activos
    # ------------------------------------------------------------------
    def add_asset(self, target, host, port=None, service="", version="",
                  source="", confidence=0.5) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO assets
                   (target, host, port, service, version, source,
                    confidence, created_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (target, host, port, service, version, source,
                 float(confidence), _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def list_assets(self, target: str | None = None, limit: int = 200):
        q = "SELECT * FROM assets"
        args = []
        if target:
            q += " WHERE target=?"; args.append(target)
        q += " ORDER BY id DESC LIMIT ?"; args.append(int(limit))
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Hallazgos / evidencias / decisiones
    # ------------------------------------------------------------------
    def add_finding(self, target, title, severity="info",
                    status="pending_validation", claim="", evidence="",
                    confidence=0.0, created_by="main") -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO findings
                   (target, title, severity, status, claim, evidence,
                    confidence, created_by, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (target, title, severity, status, claim, evidence,
                 float(confidence), created_by, _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def get_finding(self, finding_id: int) -> Finding | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM findings WHERE id=?", (finding_id,)
            ).fetchone()
        return self._row_to_finding(row) if row else None

    def list_findings(self, status: str | None = None,
                      target: str | None = None,
                      limit: int = 100) -> list[Finding]:
        q = "SELECT * FROM findings WHERE 1=1"
        args = []
        if status:
            q += " AND status=?"; args.append(status)
        if target:
            q += " AND target=?"; args.append(target)
        q += " ORDER BY id DESC LIMIT ?"; args.append(int(limit))
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [self._row_to_finding(r) for r in rows]

    def update_finding_status(self, finding_id: int, status: str,
                              validated_by: str = ""):
        with self._lock:
            self._conn.execute(
                """UPDATE findings SET status=?, validated_by=?,
                   validated_at=? WHERE id=?""",
                (status, validated_by, _now(), finding_id),
            )
            self._conn.commit()

    def add_evidence(self, finding_id: int | None, task_id: int | None,
                     path: str = "", sha256: str = "",
                     excerpt: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO evidence
                   (finding_id, task_id, path, sha256, excerpt, created_at)
                   VALUES(?,?,?,?,?,?)""",
                (finding_id, task_id, path, sha256,
                 (excerpt or "")[:8000], _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def evidence_for_finding(self, finding_id: int) -> list[Evidence]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM evidence WHERE finding_id=? ORDER BY id",
                (finding_id,),
            ).fetchall()
        return [self._row_to_evidence(r) for r in rows]

    def add_decision(self, finding_id=None, task_id=None, agent="",
                     decision="", reason="", policy=None) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO decisions
                   (finding_id, task_id, agent, decision, reason, policy,
                    created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (finding_id, task_id, agent, decision, reason,
                 _json(policy), _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def decisions_for_finding(self, finding_id: int) -> list[Decision]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM decisions WHERE finding_id=? ORDER BY id",
                (finding_id,),
            ).fetchall()
        return [self._row_to_decision(r) for r in rows]

    # ------------------------------------------------------------------
    # Eventos / bloqueos
    # ------------------------------------------------------------------
    def add_event(self, type_: str, agent: str = "", task_id=None,
                  payload=None) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO events(ts, type, agent, task_id, payload)
                   VALUES(?,?,?,?,?)""",
                (_now(), type_, agent, task_id, _json(payload)),
            )
            self._conn.commit()
            event_id = int(cur.lastrowid)
        # Publicación opcional externa (Redis Streams, etc.). No debe
        # romper el flujo si el bus está caído.
        if self.event_bus is not None:
            try:
                self.event_bus.publish(type_, payload or {},
                                       agent=agent, task_id=task_id)
            except Exception:
                pass
        return event_id

    def list_events(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = _loads(d.get("payload"), {})
            out.append(d)
        return out

    def add_block(self, target: str, reason: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO blocks(target, reason, active, created_at)
                   VALUES(?,?,1,?)""",
                (target, reason, _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def active_block(self, target: str | None) -> dict | None:
        if not target:
            return None
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM blocks WHERE target=? AND active=1
                   ORDER BY id DESC LIMIT 1""",
                (target,),
            ).fetchone()
        return dict(row) if row else None

    def clear_blocks(self, target: str | None = None):
        with self._lock:
            if target:
                self._conn.execute(
                    "UPDATE blocks SET active=0 WHERE target=?", (target,)
                )
            else:
                self._conn.execute("UPDATE blocks SET active=0")
            self._conn.commit()

    # ------------------------------------------------------------------
    # Resumen / cierre
    # ------------------------------------------------------------------
    def stats(self) -> dict:
        with self._lock:
            def count(sql, args=()):
                row = self._conn.execute(sql, args).fetchone()
                if row is None:
                    return 0
                if isinstance(row, dict):
                    return int(next(iter(row.values())))
                return int(row[0])
            return {
                "tasks": self.task_stats(),
                "findings": {
                    "total": count("SELECT COUNT(*) FROM findings"),
                    "pending_validation": count(
                        "SELECT COUNT(*) FROM findings WHERE status='pending_validation'"
                    ),
                    "confirmed": count(
                        "SELECT COUNT(*) FROM findings WHERE status='confirmed'"
                    ),
                    "rejected": count(
                        "SELECT COUNT(*) FROM findings WHERE status='rejected'"
                    ),
                },
                "assets": count("SELECT COUNT(*) FROM assets"),
                "events": count("SELECT COUNT(*) FROM events"),
                "active_blocks": count(
                    "SELECT COUNT(*) FROM blocks WHERE active=1"
                ),
            }

    def close(self):
        with self._lock:
            try:
                self._conn.commit()
                self._conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Row → dataclass
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_task(r) -> Task:
        return Task(
            id=r["id"], role=r["role"], kind=r["kind"],
            target=r["target"], command=r["command"],
            finding_id=r["finding_id"], priority=r["priority"],
            status=r["status"], created_at=r["created_at"],
            started_at=r["started_at"] or "",
            finished_at=r["finished_at"] or "",
            payload=_loads(r["payload"], {}), result=r["result"] or "",
            rc=r["rc"], agent=r["agent"] or "",
            attempts=r["attempts"] or 0,
            fingerprint=r["fingerprint"] or "",
        )

    @staticmethod
    def _row_to_finding(r) -> Finding:
        return Finding(
            id=r["id"], target=r["target"], title=r["title"],
            severity=r["severity"], status=r["status"],
            claim=r["claim"] or "", evidence=r["evidence"] or "",
            confidence=r["confidence"] or 0.0,
            created_by=r["created_by"] or "",
            validated_by=r["validated_by"] or "",
            created_at=r["created_at"] or "",
            validated_at=r["validated_at"] or "",
        )

    @staticmethod
    def _row_to_evidence(r) -> Evidence:
        return Evidence(
            id=r["id"], finding_id=r["finding_id"], task_id=r["task_id"],
            path=r["path"] or "", sha256=r["sha256"] or "",
            excerpt=r["excerpt"] or "", created_at=r["created_at"] or "",
        )

    @staticmethod
    def _row_to_decision(r) -> Decision:
        return Decision(
            id=r["id"], finding_id=r["finding_id"], task_id=r["task_id"],
            agent=r["agent"] or "", decision=r["decision"],
            reason=r["reason"] or "",
            policy=_loads(r["policy"], {}),
            created_at=r["created_at"] or "",
        )

    @staticmethod
    def file_sha256(path: str) -> str:
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
        except OSError:
            return ""
        return h.hexdigest()
