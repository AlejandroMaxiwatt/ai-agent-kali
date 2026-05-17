"""
Hook: after_command
===================

Se invoca DESPUÉS de ejecutar un comando shell, tanto si tuvo éxito
como si falló. Si `rc != 0` el dispatcher también invoca `on_error`
después de este hook.

Misión por defecto:
  1. Añadir una línea de resultado a logs/audit/commands.jsonl
     (apareada con la entrada `before_command` por timestamp + comando).
  2. Mantener un índice ligero de archivos de output producidos en
     logs/audit/artifacts.jsonl, útil para saber qué se ha generado
     durante la sesión sin tener que recorrer ./scans, ./evidence, etc.

Formato JSONL (logs/audit/commands.jsonl):

    {
      "ts":          "...",
      "event":       "after_command",
      "session_id":  "...",
      "target":      "empresa2" | null,
      "command":     "<comando>",
      "rc":          0,
      "duration_s":  3.42,
      "stdout_len":  1280,
      "stderr_len":  0,
      "output_files": ["./scans/x.txt"]   (rutas detectadas por agent.py)
    }

Formato JSONL (logs/audit/artifacts.jsonl), una línea por archivo:

    {
      "ts": "...",
      "session_id": "...",
      "target": "...",
      "path": "./scans/x.txt",
      "abs_path": "/home/.../scans/x.txt",
      "exists": true,
      "size": 1280
    }
"""

import json
import os
from datetime import datetime


def run(ctx):
    workspace = ctx.get("workspace") or os.path.expanduser("~/ai-agent-kali")
    log_dir = os.path.join(workspace, "logs", "audit")
    os.makedirs(log_dir, exist_ok=True)

    commands_log = os.path.join(log_dir, "commands.jsonl")
    artifacts_log = os.path.join(log_dir, "artifacts.jsonl")

    ts = datetime.now().isoformat(timespec="seconds")
    output_files = ctx.get("output_files") or []

    entry = {
        "ts": ts,
        "event": "after_command",
        "session_id": ctx.get("session_id"),
        "target": ctx.get("target"),
        "command": ctx.get("command"),
        "rc": ctx.get("rc"),
        "duration_s": ctx.get("duration_s"),
        "stdout_len": ctx.get("stdout_len"),
        "stderr_len": ctx.get("stderr_len"),
        "output_files": output_files,
    }
    with open(commands_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    for rel in output_files:
        abs_path = os.path.abspath(rel)
        try:
            exists = os.path.exists(abs_path)
            size = os.path.getsize(abs_path) if exists else 0
        except OSError:
            exists, size = False, 0
        artifact = {
            "ts": ts,
            "session_id": ctx.get("session_id"),
            "target": ctx.get("target"),
            "path": rel,
            "abs_path": abs_path,
            "exists": exists,
            "size": size,
        }
        with open(artifacts_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(artifact, ensure_ascii=False) + "\n")
