"""Especificación de objetivos y verificador objetivo de criterios.

Sintaxis de la línea de goal (todo tras ``||`` es opcional)::

    goal <descripción> || criteria: file_exists:evidence/x.txt; \
        file_contains:notes.md:FLAG\\{ ; cmd_rc:test -s evidence/x.txt || \
        budget: 4h, 300 comandos || constraints: no_destructive || \
        target: acme

Criterios soportados:
    file_exists:<ruta>
    file_missing:<ruta>
    dir_exists:<ruta>
    file_contains:<ruta>:<regex>
    file_not_contains:<ruta>:<regex>
    cmd_rc:<comando>
    cmd_output:<comando>@@@<regex>   (@@@ evita romper URLs con ':')
    port_open:<host>:<puerto>

Este módulo no importa Rich ni el cliente LLM: es testeable de forma aislada.
"""

from __future__ import annotations

import dataclasses
import datetime
import os
import re
import socket
import subprocess


def parse_duration_seconds(text: str | None) -> int | None:
    """Convierte '90', '30m', '2h', '3600s' a segundos. None si no aplica."""
    m = re.fullmatch(r"\s*(\d+)\s*([smh]?)\s*", (text or "").lower())
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    return n * {"": 1, "s": 1, "m": 60, "h": 3600}[unit]


@dataclasses.dataclass
class GoalSpec:
    """Objetivo + criterios + presupuesto + restricciones."""
    goal: str = ""
    criteria: list = dataclasses.field(default_factory=list)
    budget_seconds: int | None = None
    budget_commands: int | None = None
    constraints: list = dataclasses.field(default_factory=list)
    target: str | None = None

    @classmethod
    def parse(cls, text: str) -> "GoalSpec":
        raw = (text or "").strip()
        # Tolerancia para specs en archivo con formato por líneas:
        #   goal: ...
        #   criteria: ...
        #   budget: ...
        # Convertimos las líneas-clave en secciones `||` sin tocar las
        # líneas de continuación.
        if "||" not in raw and re.search(
            r"(?im)^\s*(criteria|criterios|budget|presupuesto|constraints|"
            r"restricciones|target)\s*:",
            raw,
        ):
            raw = "\n".join(
                ("|| " + ln) if re.match(
                    r"(?i)^\s*(criteria|criterios|budget|presupuesto|"
                    r"constraints|restricciones|target)\s*:", ln
                ) else ln
                for ln in raw.splitlines()
            )
        parts = [p.strip() for p in raw.split("||")]
        goal_text = parts[0].strip() if parts else ""
        goal_text = re.sub(r"(?i)^goal\s*:\s*", "", goal_text).strip()
        spec = cls(goal=goal_text)
        for part in parts[1:]:
            if not part:
                continue
            key, sep, value = part.partition(":")
            if not sep:
                continue
            key_l = key.strip().lower()
            value = value.strip()
            if key_l in ("criteria", "criterios", "criterion", "criterio"):
                items = re.split(r"[;\n]+", value)
                for x in items:
                    x = re.sub(r"^[-*·]\s*", "", x.strip()).strip()
                    if x and x.lower() not in ("none", "ninguno"):
                        spec.criteria.append(x)
            elif key_l in ("budget", "presupuesto", "limite", "límite"):
                m_cmds = re.search(
                    r"(\d+)\s*(?:comandos?|commands?|cmds?)", value, re.I
                )
                if m_cmds:
                    spec.budget_commands = int(m_cmds.group(1))
                m_secs = re.search(
                    r"(\d+)\s*(?:h|hs|horas?|m|min|minutos?|s|seg|segundos?)",
                    value, re.I,
                )
                if m_secs:
                    spec.budget_seconds = parse_duration_seconds(m_secs.group(0))
                else:
                    m_num = re.match(r"\s*(\d+)\s*$", value.split(",")[0])
                    if m_num:
                        spec.budget_seconds = int(m_num.group(1))
            elif key_l in ("constraints", "restricciones", "limites", "límites"):
                spec.constraints.extend(
                    x.strip().lower()
                    for x in re.split(r"[;,]+", value) if x.strip()
                )
            elif key_l in ("target", "objetivo"):
                spec.target = value or None
        return spec

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "GoalSpec":
        if not data:
            return cls()
        return cls(
            goal=data.get("goal", ""),
            criteria=list(data.get("criteria", [])),
            budget_seconds=data.get("budget_seconds"),
            budget_commands=data.get("budget_commands"),
            constraints=list(data.get("constraints", [])),
            target=data.get("target"),
        )


def resolve_path(path: str, workspace: str | None = None) -> str:
    """Resuelve una ruta de criterio contra el workspace (o absoluta)."""
    p = os.path.expanduser((path or "").strip())
    if os.path.isabs(p):
        return p
    return os.path.join(workspace or os.getcwd(), p)


def _criterion_file_contains(path, pattern, workspace):
    full = resolve_path(path, workspace)
    if not os.path.isfile(full):
        return False, f"no existe: {full}"
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        return False, f"error leyendo {full}: {e}"
    try:
        found = re.search(pattern, content, re.MULTILINE) is not None
    except re.error as e:
        return False, f"regex inválida '{pattern}': {e}"
    return found, ("patrón encontrado" if found else f"patrón NO encontrado: {pattern}")


def _criterion_cmd(command, workspace, expect_regex=None):
    try:
        proc = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=120, stdin=subprocess.DEVNULL,
            cwd=workspace or os.getcwd(),
        )
    except subprocess.TimeoutExpired:
        return False, f"timeout (120s): {command}"
    except Exception as e:
        return False, f"error ejecutando criterio: {e}"
    combined = (proc.stdout or "") + (proc.stderr or "")
    if expect_regex:
        try:
            found = re.search(expect_regex, combined, re.MULTILINE) is not None
        except re.error as e:
            return False, f"regex inválida '{expect_regex}': {e}"
        return (proc.returncode == 0 and found,
                f"rc={proc.returncode} · regex {'OK' if found else 'NO encontrada'}")
    return proc.returncode == 0, f"rc={proc.returncode}"


def _criterion_port_open(host, port):
    try:
        with socket.create_connection((host, int(port)), timeout=3):
            return True, f"{host}:{port} abierto"
    except Exception as e:
        return False, f"{host}:{port} no conecta ({e})"


def verify_goal_criteria(criteria, workspace: str | None = None) -> dict:
    """Evalúa la lista de criterios SIN intervención del LLM.

    Devuelve ``{ok: bool|None, unknown: bool, results: [...], summary: str}``.
    ``ok=None/unknown=True`` cuando no hay criterios: el sistema cae al
    juicio del LLM-orquestador (comportamiento clásico).
    """
    results = []
    for raw in (criteria or []):
        crit = (raw or "").strip()
        if not crit:
            continue
        kind, sep, rest = crit.partition(":")
        kind_l = kind.strip().lower()
        rest = rest.strip()
        ok, detail = False, "criterio no reconocido"
        try:
            if kind_l == "file_exists":
                full = resolve_path(rest, workspace)
                ok = os.path.isfile(full)
                detail = f"{full} {'existe' if ok else 'NO existe'}"
            elif kind_l == "file_missing":
                full = resolve_path(rest, workspace)
                ok = not os.path.exists(full)
                detail = f"{full} {'ausente' if ok else 'EXISTE (no deseado)'}"
            elif kind_l == "dir_exists":
                full = resolve_path(rest, workspace)
                ok = os.path.isdir(full)
                detail = f"{full} {'es directorio' if ok else 'NO es directorio'}"
            elif kind_l in ("file_contains", "file_not_contains"):
                path, sep2, pattern = rest.partition(":")
                if not sep2:
                    ok, detail = False, "sintaxis: file_contains:<ruta>:<regex>"
                else:
                    ok, detail = _criterion_file_contains(path, pattern, workspace)
                    if kind_l == "file_not_contains":
                        ok = not ok
            elif kind_l in ("cmd_rc", "cmd_output"):
                if kind_l == "cmd_rc":
                    ok, detail = _criterion_cmd(rest, workspace)
                else:
                    # `@@@` es el separador recomendado porque las URLs y
                    # muchos comandos contienen `:` y `::`.
                    if "@@@" in rest:
                        command, pattern = rest.split("@@@", 1)
                    elif "::" in rest:
                        command, pattern = rest.split("::", 1)
                    else:
                        command, sep2, pattern = rest.partition(":")
                    if not command.strip() or not pattern.strip():
                        ok, detail = False, (
                            "sintaxis: cmd_output:<comando>@@@<regex>"
                        )
                    else:
                        ok, detail = _criterion_cmd(
                            command.strip(), workspace, pattern.strip(),
                        )
            elif kind_l == "port_open":
                host, sep2, port = rest.rpartition(":")
                if not sep2 or not port.isdigit():
                    ok, detail = False, "sintaxis: port_open:<host>:<puerto>"
                else:
                    ok, detail = _criterion_port_open(host, port)
            else:
                ok, detail = False, f"tipo desconocido '{kind}'"
        except Exception as e:
            ok, detail = False, f"excepción evaluando criterio: {e}"
        results.append({"criterion": crit, "ok": bool(ok), "detail": detail})

    if not results:
        return {"ok": None, "unknown": True, "results": [],
                "summary": "sin criterios verificables (decide el LLM)"}

    n_ok = sum(1 for r in results if r["ok"])
    summary = f"{n_ok}/{len(results)} criterios cumplidos"
    for r in results:
        summary += f"\n  {'✓' if r['ok'] else '✗'} {r['criterion']} — {r['detail']}"
    return {
        "ok": n_ok == len(results),
        "unknown": False,
        "results": results,
        "summary": summary,
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
    }
