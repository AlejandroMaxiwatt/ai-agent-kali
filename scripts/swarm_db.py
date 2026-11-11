#!/usr/bin/env python3
"""Visor de la base de datos del enjambre (SQLite/PostgreSQL) y Redis.

Uso rápido:
    python3 scripts/swarm_db.py --list
    python3 scripts/swarm_db.py --target empresa2 --section all
    python3 scripts/swarm_db.py --target empresa2 --section findings
    python3 scripts/swarm_db.py --target empresa2 --sql "SELECT * FROM tasks LIMIT 5"
    python3 scripts/swarm_db.py --store postgres --dsn "postgresql://..." --section stats
    python3 scripts/swarm_db.py --target empresa2 --redis redis://127.0.0.1:6379/0 --section redis

Es SOLO LECTURA: abre SQLite con mode=ro y PostgreSQL en transacción readonly.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sqlite3
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWARM_DIR = os.path.join(REPO_ROOT, "memory", "swarm")

SECTIONS = (
    "stats", "tasks", "queue", "findings", "events",
    "assets", "decisions", "evidence", "blocks", "redis", "all",
)

READ_ONLY_SQL = re.compile(r"^\s*(SELECT|WITH|PRAGMA|EXPLAIN|SHOW)\b", re.I)


def safe_target(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name or "default")


def discover_dbs() -> list[str]:
    return sorted(glob.glob(os.path.join(SWARM_DIR, "*.db")))


def resolve_db(args) -> str | None:
    if args.db:
        return os.path.abspath(os.path.expanduser(args.db))
    if args.target:
        return os.path.join(SWARM_DIR, f"{safe_target(args.target)}.db")
    dbs = discover_dbs()
    if len(dbs) == 1:
        return dbs[0]
    return None


# ---------------------------------------------------------------------------
# Conexiones / consultas
# ---------------------------------------------------------------------------
class DB:
    def __init__(self, args):
        self.backend = (args.store or "sqlite").lower()
        self.conn = None
        self.cur = None
        self.path = None
        if self.backend in ("postgres", "postgresql", "pg"):
            if not args.dsn:
                sys.exit("ERROR: --store postgres requiere --dsn")
            try:
                import psycopg2
                from psycopg2.extras import RealDictCursor
            except Exception as e:
                sys.exit(f"ERROR: falta psycopg2 ({e}). "
                         f"Instala: pip install psycopg2-binary")
            self.conn = psycopg2.connect(args.dsn)
            self.conn.set_session(readonly=True, autocommit=False)
            self.cur = self.conn.cursor(cursor_factory=RealDictCursor)
            self.path = args.dsn
        else:
            path = resolve_db(args)
            if path is None:
                dbs = discover_dbs()
                if not dbs:
                    sys.exit(
                        "No hay bases SQLite en memory/swarm/.\n"
                        "Inicia el enjambre con: swarm start --target <target>"
                    )
                sys.exit(
                    "Hay varias bases. Elige una con --target o --db:\n  "
                    + "\n  ".join(dbs)
                )
            if not os.path.isfile(path):
                sys.exit(f"No existe la base: {path}")
            self.path = path
            # mode=ro: nunca escribe, aunque el enjambre esté corriendo.
            uri = f"file:{path}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True, timeout=10)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA busy_timeout=5000")

    def query(self, sql: str, params=()) -> list[dict]:
        if self.cur is not None:  # PostgreSQL
            self.cur.execute(sql.replace("?", "%s"), params)
            return [dict(r) for r in self.cur.fetchall()]
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        try:
            if self.conn is not None:
                self.conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def _cell(value, max_width=42) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ⏎ ").replace("\r", " ")
    if len(text) > max_width:
        text = text[:max_width - 1] + "…"
    return text


def render_table(rows: list[dict], columns=None, max_width=42):
    if not rows:
        print("  (sin resultados)")
        return
    columns = columns or list(rows[0].keys())
    table = [[_cell(r.get(c), max_width) for c in columns] for r in rows]
    widths = [
        max(len(str(c)), *(len(row[i]) for row in table))
        for i, c in enumerate(columns)
    ]
    print("  " + " | ".join(str(c).ljust(widths[i])
                            for i, c in enumerate(columns)))
    print("  " + "-+-".join("-" * w for w in widths))
    for row in table:
        print("  " + " | ".join(row[i].ljust(widths[i])
                               for i in range(len(columns))))


def print_title(text: str):
    print()
    print(f"── {text} " + "─" * max(0, 66 - len(text)))


# ---------------------------------------------------------------------------
# Secciones
# ---------------------------------------------------------------------------
def section_stats(db: DB):
    print_title("Resumen")
    render_table(db.query(
        "SELECT role, status, COUNT(*) AS n FROM tasks "
        "GROUP BY role, status ORDER BY role, status"
    ))
    print()
    render_table(db.query(
        "SELECT status, COUNT(*) AS n FROM findings "
        "GROUP BY status ORDER BY status"
    ))
    totals = db.query(
        "SELECT "
        "(SELECT COUNT(*) FROM assets) AS assets, "
        "(SELECT COUNT(*) FROM evidence) AS evidence, "
        "(SELECT COUNT(*) FROM decisions) AS decisions, "
        "(SELECT COUNT(*) FROM events) AS events, "
        "(SELECT COUNT(*) FROM blocks WHERE active=1) AS blocks_activos"
    )
    print()
    render_table(totals)


def _target_where(args, column="target"):
    if args.target:
        return f" WHERE {column}=?", (args.target,)
    return "", ()


def section_tasks(db: DB, args):
    print_title(f"Tareas (últimas {args.limit})")
    where, params = _target_where(args)
    sql = (
        "SELECT id, role, status, priority, rc, target, "
        "substr(COALESCE(command, 'validate #' || finding_id), 1, 90) AS trabajo, "
        "created_at, finished_at FROM tasks"
        + where +
        " ORDER BY id DESC LIMIT ?"
    )
    render_table(db.query(sql, params + (args.limit,)), max_width=48)


def section_queue(db: DB, args):
    print_title("Cola pendiente / en ejecución")
    where, params = _target_where(args)
    extra = " AND " if where else " WHERE "
    sql = (
        "SELECT id, role, status, priority, target, "
        "substr(COALESCE(command, 'validate #' || finding_id), 1, 100) AS trabajo "
        "FROM tasks" + where + extra +
        "status IN ('pending','running') ORDER BY priority ASC, id ASC"
    )
    render_table(db.query(sql, params), max_width=52)


def section_findings(db: DB, args):
    print_title(f"Hallazgos (últimos {args.limit})")
    where, params = _target_where(args)
    sql = (
        "SELECT id, severity, status, target, title, created_by, "
        "validated_by, confidence, created_at FROM findings"
        + where + " ORDER BY id DESC LIMIT ?"
    )
    render_table(db.query(sql, params + (args.limit,)), max_width=50)


def section_events(db: DB, args):
    print_title(f"Eventos (últimos {args.limit})")
    sql = ("SELECT id, ts, type, agent, task_id, payload "
           "FROM events ORDER BY id DESC LIMIT ?")
    render_table(db.query(sql, (args.limit,)), max_width=60)


def section_assets(db: DB, args):
    print_title(f"Activos (últimos {args.limit})")
    where, params = _target_where(args)
    sql = ("SELECT id, target, host, port, service, version, source, "
           "confidence, created_at FROM assets"
           + where + " ORDER BY id DESC LIMIT ?")
    render_table(db.query(sql, params + (args.limit,)), max_width=44)


def section_decisions(db: DB, args):
    print_title(f"Decisiones (últimas {args.limit})")
    sql = ("SELECT id, finding_id, task_id, agent, decision, reason, "
           "created_at FROM decisions ORDER BY id DESC LIMIT ?")
    render_table(db.query(sql, (args.limit,)), max_width=60)


def section_evidence(db: DB, args):
    print_title(f"Evidencias (últimas {args.limit})")
    sql = ("SELECT id, finding_id, task_id, path, sha256, created_at "
           "FROM evidence ORDER BY id DESC LIMIT ?")
    render_table(db.query(sql, (args.limit,)), max_width=52)


def section_blocks(db: DB, args):
    print_title("Bloqueos activos")
    where, params = _target_where(args)
    extra = " AND " if where else " WHERE "
    sql = ("SELECT id, target, reason, created_at FROM blocks"
           + where + extra + "active=1 ORDER BY id DESC")
    render_table(db.query(sql, params), max_width=60)


def section_redis(url: str, limit: int):
    print_title(f"Redis Streams · {url}")
    try:
        import redis
    except Exception:
        print("  Falta el paquete `redis`. Instala: pip install redis")
        return
    try:
        r = redis.Redis.from_url(url, decode_responses=True)
        r.ping()
    except Exception as e:
        print(f"  No se pudo conectar: {e}")
        return
    stream = "maxiwatt:swarm"
    try:
        length = r.xlen(stream)
        print(f"  Stream: {stream} · eventos: {length}")
        info = r.xinfo_stream(stream)
        print(f"  Primer ID: {info.get('first-entry', ['?'])[0]}"
              f" · Último ID: {info.get('last-entry', ['?'])[0]}")
        entries = r.xrevrange(stream, count=limit)
        rows = []
        for entry_id, fields in entries:
            try:
                payload = json.loads(fields.get("payload") or "{}")
            except Exception:
                payload = {}
            rows.append({
                "id": entry_id,
                "type": fields.get("type", ""),
                "agent": fields.get("agent", ""),
                "task_id": fields.get("task_id", ""),
                "payload": json.dumps(payload, ensure_ascii=False),
            })
        print()
        render_table(rows, max_width=60)
    except Exception as e:
        print(f"  Error leyendo el stream: {e}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(
        description="Visor de solo lectura de la BD del enjambre "
                    "(SQLite/PostgreSQL) y Redis Streams.",
    )
    p.add_argument("--target", "-t", help="target del enjambre (nombre)")
    p.add_argument("--db", help="ruta explícita a la BD SQLite")
    p.add_argument("--store", choices=("sqlite", "postgres"),
                   default="sqlite", help="backend de la BD")
    p.add_argument("--dsn", help="DSN de PostgreSQL")
    p.add_argument("--redis", help="URL de Redis (ej. redis://127.0.0.1:6379/0)")
    p.add_argument("--section", "-s", choices=SECTIONS, default="all",
                   help="qué mostrar (default: all)")
    p.add_argument("--limit", "-n", type=int, default=20,
                   help="número de filas (default: 20)")
    p.add_argument("--sql", help="consulta SQL de solo lectura")
    p.add_argument("--json", action="store_true",
                   help="salida JSON en lugar de tabla")
    p.add_argument("--list", action="store_true",
                   help="lista las bases SQLite disponibles y sale")
    args = p.parse_args(argv)

    if args.list:
        dbs = discover_dbs()
        if not dbs:
            print("No hay bases en", SWARM_DIR)
        else:
            print(f"Bases en {SWARM_DIR}:")
            for db in dbs:
                size = os.path.getsize(db) / 1024
                print(f"  - {os.path.basename(db)}  ({size:.1f} KB)")
        return 0

    if args.sql and not READ_ONLY_SQL.match(args.sql):
        sys.exit("ERROR: --sql solo permite SELECT/WITH/PRAGMA/EXPLAIN/SHOW")

    db = None
    if args.section != "redis" or not args.redis:
        db = DB(args)

    try:
        if args.sql:
            rows = db.query(args.sql)
            if args.json:
                print(json.dumps(rows, ensure_ascii=False, indent=2))
            else:
                print_title("Consulta")
                render_table(rows, max_width=70)
            return 0

        if args.json:
            data = {}
            if db is not None:
                for name, sql in {
                    "tasks": "SELECT * FROM tasks ORDER BY id DESC LIMIT ?",
                    "findings": "SELECT * FROM findings ORDER BY id DESC LIMIT ?",
                    "events": "SELECT * FROM events ORDER BY id DESC LIMIT ?",
                    "assets": "SELECT * FROM assets ORDER BY id DESC LIMIT ?",
                }.items():
                    data[name] = db.query(sql, (args.limit,))
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0

        section = args.section
        if section in ("all", "stats") and db is not None:
            section_stats(db)
        if section in ("all", "queue") and db is not None:
            section_queue(db, args)
        if section in ("all", "findings") and db is not None:
            section_findings(db, args)
        if section in ("all", "tasks") and db is not None:
            section_tasks(db, args)
        if section in ("all", "events") and db is not None:
            section_events(db, args)
        if section in ("all", "assets") and db is not None:
            section_assets(db, args)
        if section in ("all", "decisions") and db is not None:
            section_decisions(db, args)
        if section in ("all", "evidence") and db is not None:
            section_evidence(db, args)
        if section in ("all", "blocks") and db is not None:
            section_blocks(db, args)
        if section in ("all", "redis") and args.redis:
            section_redis(args.redis, args.limit)
        return 0
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    sys.exit(main())
