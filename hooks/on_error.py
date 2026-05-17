"""
Hook: on_error
==============

Se invoca cuando un comando shell devuelve rc != 0 (y NO ha sido
cancelado por el usuario). Se llama DESPUÉS de `after_command`, así
que la entrada del comando ya está en logs/audit/commands.jsonl.

Misión por defecto:
  1. Escribir un registro humano-legible en logs/errors.log con el
     comando, rc, stderr (truncado) y contexto, para revisión manual.
  2. Añadir un JSONL en logs/audit/errors.jsonl, agrupable por sesión
     o target, para post-análisis.

Si el agente está en modo autopilot la propia infraestructura intenta
auto-fixes; este hook NO inyecta lógica de remediación — sólo deja
registro. Si quieres añadir reglas de retry/escalación, hazlo aquí
modificando este archivo: tienes acceso a `ctx` completo.

Formato logs/errors.log (texto plano):

    [2026-05-13T14:22:33] session=20260513-142000 target=empresa2 rc=2
    cmd: nmap -p 22 --script ssh-user-enum host
    stderr:
        'ssh-user-enum' did not match a category, filename or directory
    output_files: ./scans/ssh_enum.txt (no existe / 0 bytes)
    ---
"""

import json
import os
from datetime import datetime


_MAX_STDERR_PREVIEW = 4000


def _truncate(text, limit):
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[...truncado a {limit} chars de {len(text)}]"


def run(ctx):
    workspace = ctx.get("workspace") or os.path.expanduser("~/ai-agent-kali")
    log_dir = os.path.join(workspace, "logs")
    audit_dir = os.path.join(log_dir, "audit")
    os.makedirs(audit_dir, exist_ok=True)

    text_log = os.path.join(log_dir, "errors.log")
    json_log = os.path.join(audit_dir, "errors.jsonl")

    ts = datetime.now().isoformat(timespec="seconds")
    rc = ctx.get("rc")
    command = ctx.get("command", "")
    stderr_preview = _truncate(ctx.get("stderr") or "", _MAX_STDERR_PREVIEW)

    output_files = ctx.get("output_files") or []
    files_block = ""
    if output_files:
        rows = []
        for rel in output_files:
            try:
                abs_path = os.path.abspath(rel)
                if not os.path.exists(abs_path):
                    rows.append(f"    {rel}  (no existe)")
                else:
                    size = os.path.getsize(abs_path)
                    rows.append(f"    {rel}  ({size}B)")
            except OSError:
                rows.append(f"    {rel}  (error stat)")
        files_block = "output_files:\n" + "\n".join(rows) + "\n"

    with open(text_log, "a", encoding="utf-8") as f:
        f.write(
            f"[{ts}] session={ctx.get('session_id')} "
            f"target={ctx.get('target')} rc={rc}\n"
            f"cmd: {command}\n"
            f"stderr:\n    " + stderr_preview.replace("\n", "\n    ") + "\n"
            + files_block
            + "---\n"
        )

    entry = {
        "ts": ts,
        "event": "on_error",
        "session_id": ctx.get("session_id"),
        "target": ctx.get("target"),
        "command": command,
        "rc": rc,
        "stderr_preview": stderr_preview,
        "output_files": output_files,
        "autopilot": bool(ctx.get("auto")),
    }
    with open(json_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
