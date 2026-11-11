"""Modelos de datos del enjambre."""

from __future__ import annotations

import dataclasses
from enum import IntEnum


class AutonomyLevel(IntEnum):
    """Niveles de autonomía (1 = automático, 4 = bloqueado)."""
    AUTO = 1
    PREAPPROVED = 2
    HUMAN_APPROVAL = 3
    BLOCKED = 4


@dataclasses.dataclass
class PolicyDecision:
    """Resultado del motor de políticas para un comando."""
    allowed: bool
    requires_approval: bool
    blocked: bool
    level: int
    reason: str = ""
    fingerprint: str = ""
    duplicate_of: int | None = None
    target: str | None = None


@dataclasses.dataclass
class Task:
    """Tarea de la cola (reconocimiento o validación)."""
    id: int | None = None
    role: str = "recon"          # recon | validation
    kind: str = "command"        # command | validate | block
    target: str | None = None
    command: str | None = None
    finding_id: int | None = None
    priority: int = 5
    status: str = "pending"      # pending | running | done | failed | blocked
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    payload: dict = dataclasses.field(default_factory=dict)
    result: str = ""
    rc: int | None = None
    agent: str = ""
    attempts: int = 0
    fingerprint: str = ""
    # Evento transitorio de cancelación (no se persiste en SQLite).
    cancel_event: object = dataclasses.field(
        default=None, repr=False, compare=False,
    )


@dataclasses.dataclass
class Finding:
    """Hallazgo propuesto por el agente principal o Recon."""
    id: int | None = None
    target: str | None = None
    title: str = ""
    severity: str = "info"       # info | low | medium | high | critical
    status: str = "pending_validation"
    claim: str = ""
    evidence: str = ""
    confidence: float = 0.0
    created_by: str = "main"
    validated_by: str = ""
    created_at: str = ""
    validated_at: str = ""


@dataclasses.dataclass
class Evidence:
    """Evidencia asociada a un hallazgo."""
    id: int | None = None
    finding_id: int | None = None
    task_id: int | None = None
    path: str = ""
    sha256: str = ""
    excerpt: str = ""
    created_at: str = ""


@dataclasses.dataclass
class Decision:
    """Decisión del Guardian o del motor de políticas."""
    id: int | None = None
    finding_id: int | None = None
    task_id: int | None = None
    agent: str = ""
    decision: str = ""           # confirmed | rejected | needs_more_evidence | blocked | approved
    reason: str = ""
    policy: dict = dataclasses.field(default_factory=dict)
    created_at: str = ""


@dataclasses.dataclass
class Asset:
    """Activo descubierto (host, puerto, servicio, tecnología)."""
    id: int | None = None
    target: str | None = None
    host: str = ""
    port: int | None = None
    service: str = ""
    version: str = ""
    source: str = ""
    confidence: float = 0.5
    created_at: str = ""
