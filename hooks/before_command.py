"""
Hook: before_command
====================

Se invoca ANTES de ejecutar un comando shell propuesto por el modelo,
independientemente de si lo lanza el flujo normal o el autopilot.

Misión por defecto: dejar trazabilidad de auditoría. Cada comando se
registra en logs/audit/commands.jsonl como una entrada JSON Lines con:

    {
      "ts":          "2026-05-13T14:22:33",
      "event":       "before_command",
      "session_id":  "20260513-142000",
      "target":      "empresa2"   (o null),
      "skills":      ["recon"],
      "category":    "intrusive"  | "safe" | "destructive",
      "proxy_mode":  "proxychains" | "torify" | "off",
      "auto":        false        (true si autopilot/sin confirmación),
      "command":     "<comando original tal como lo propuso el modelo>"
    }

No bloquea ni modifica el comando. Si quieres impedir un comando, lanza
una excepción `HookAbort` (definida en agent.py); el dispatcher lo
respeta y aborta la ejecución antes de tocar el shell.
"""

import json
import os
from datetime import datetime


def run(ctx):
    workspace = ctx.get("workspace") or os.path.expanduser("~/ai-agent-kali")
    log_dir = os.path.join(workspace, "logs", "audit")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "commands.jsonl")

    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": "before_command",
        "session_id": ctx.get("session_id"),
        "target": ctx.get("target"),
        "skills": ctx.get("skills") or [],
        "category": ctx.get("category"),
        "proxy_mode": ctx.get("proxy_mode"),
        "auto": bool(ctx.get("auto")),
        "command": ctx.get("command"),
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
