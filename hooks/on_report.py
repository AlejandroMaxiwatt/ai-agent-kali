"""
Hook: on_report
===============

Se invoca cuando el comando `report` / `informe` ha terminado de
generar un informe técnico (reports/informe-<target>-<ts>.md ya está
escrito en disco).

Misión por defecto:
  1. Validar el archivo: existe, tamaño no nulo, número de líneas,
     hash sha256 (para integridad / no-repudio).
  2. Apuntar todo eso en reports/INDEX.md (índice humano-legible) y
     en logs/audit/reports.jsonl (consultable).
  3. Si pandoc está disponible y el archivo es > 0 bytes, también se
     puede registrar la línea de conversión a PDF sugerida — esto se
     deja comentado, descomenta si quieres que se ejecute solo.

Formato reports/INDEX.md (entrada por informe, encabezado se crea si
no existe todavía):

    - [2026-05-13 14:22] empresa2  ·  informe-empresa2-20260513-1422.md  ·  18.4KB / 412 líneas  ·  sha256:abcd…

Formato logs/audit/reports.jsonl:

    {
      "ts": "...",
      "event": "on_report",
      "session_id": "...",
      "target": "empresa2",
      "path": "/home/.../reports/informe-empresa2-...md",
      "rel_path": "reports/informe-empresa2-...md",
      "size_bytes": 18800,
      "lines": 412,
      "sha256": "..."
    }
"""

import hashlib
import json
import os
from datetime import datetime


_INDEX_HEADER = (
    "# Índice de informes generados\n\n"
    "<!-- Línea por informe: fecha · target · archivo · tamaño/líneas · sha256. "
    "Lo mantiene hooks/on_report.py. -->\n\n"
)


def _sha256(path, chunk=65536):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                buf = f.read(chunk)
                if not buf:
                    break
                h.update(buf)
        return h.hexdigest()
    except OSError:
        return None


def run(ctx):
    workspace = ctx.get("workspace") or os.path.expanduser("~/ai-agent-kali")
    report_path = ctx.get("report_path")
    if not report_path or not os.path.isfile(report_path):
        return

    target = ctx.get("target") or "?"
    rel_path = os.path.relpath(report_path, workspace)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        size = os.path.getsize(report_path)
    except OSError:
        size = 0
    try:
        with open(report_path, "r", encoding="utf-8", errors="replace") as f:
            n_lines = sum(1 for _ in f)
    except OSError:
        n_lines = 0
    digest = _sha256(report_path) or "?"

    size_str = f"{size}B" if size < 1024 else f"{size/1024:.1f}KB"
    short_hash = digest[:12] if digest != "?" else "?"

    # 1) Índice humano-legible en reports/INDEX.md
    reports_dir = os.path.join(workspace, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    index_path = os.path.join(reports_dir, "INDEX.md")
    if not os.path.exists(index_path):
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(_INDEX_HEADER)
    entry_line = (
        f"- [{ts}] {target}  ·  {os.path.basename(report_path)}  ·  "
        f"{size_str} / {n_lines} líneas  ·  sha256:{short_hash}\n"
    )
    with open(index_path, "a", encoding="utf-8") as f:
        f.write(entry_line)

    # 2) JSONL auditable
    audit_dir = os.path.join(workspace, "logs", "audit")
    os.makedirs(audit_dir, exist_ok=True)
    audit_path = os.path.join(audit_dir, "reports.jsonl")
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": "on_report",
        "session_id": ctx.get("session_id"),
        "target": target,
        "path": report_path,
        "rel_path": rel_path,
        "size_bytes": size,
        "lines": n_lines,
        "sha256": digest,
    }
    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
