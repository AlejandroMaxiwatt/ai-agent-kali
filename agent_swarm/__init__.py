"""Enjambre de subagentes permanentes + orquestador determinista.

Arquitectura (ver docs/SWARM_ARCHITECTURE.md):

    Agente principal
        │  autoriza comandos
        ▼
    PolicyEngine (determinista, fuera de los modelos)
        │
        ├── ReconWorker   (subagente permanente de reconocimiento)
        └── GuardianWorker (subagente permanente de validación/guardia)

Memoria compartida: SQLite (memory/swarm/swarm.db).
Eventos: tabla `events` + Condition en proceso.
"""

from .models import (
    AutonomyLevel,
    Decision,
    Evidence,
    Finding,
    PolicyDecision,
    Task,
)
from .orchestrator import SwarmOrchestrator
from .policy import PolicyEngine, Scope
from .store import Store

__all__ = [
    "AutonomyLevel",
    "Decision",
    "Evidence",
    "Finding",
    "PolicyDecision",
    "Task",
    "SwarmOrchestrator",
    "PolicyEngine",
    "Scope",
    "Store",
]
