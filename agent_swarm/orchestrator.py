"""Orquestador determinista del enjambre.

No es un tercer modelo: gestiona colas, workers permanentes, políticas,
límites y trazabilidad. Los modelos (principal, Recon, Guardian) razonan,
pero no pueden modificar sus propias restricciones.
"""

from __future__ import annotations

import re
import threading

from .models import AutonomyLevel, PolicyDecision
from .policy import PolicyEngine, Scope, command_fingerprint
from .store import Store
from .workers import GuardianWorker, ReconWorker


class SwarmOrchestrator:
    """Ciclo de vida y API del enjambre."""

    def __init__(self, store_path: str, target: str | None = None,
                 scope_text: str = "",
                 autonomy_level: int = AutonomyLevel.PREAPPROVED,
                 runner=None, llm_validator=None, llm_planner=None,
                 poll_interval: float = 1.0,
                 per_minute: int = 30, per_hour: int = 300):
        self.store = Store(store_path)
        self.target = target
        self.scope = Scope.from_text(scope_text, target)
        self.autonomy_level = int(autonomy_level)
        self.policy = PolicyEngine(
            self.store, self.scope, autonomy_level,
            per_minute=per_minute, per_hour=per_hour,
        )
        self.stop_event = threading.Event()
        self._started = False
        self._lock = threading.Lock()
        self.recon = ReconWorker(
            self.store, self.policy, runner, self.stop_event,
            target=target, llm_planner=llm_planner,
            poll_interval=poll_interval,
        )
        self.guardian = GuardianWorker(
            self.store, self.policy, self.stop_event,
            llm_validator=llm_validator, poll_interval=poll_interval,
        )

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def start(self):
        with self._lock:
            if self._started:
                return
            self._started = True
            self.store.add_event(
                "swarm_started", "orchestrator",
                payload={
                    "target": self.target,
                    "scope": self.scope.describe(),
                    "autonomy": self.autonomy_level,
                },
            )
            self.recon.start()
            self.guardian.start()

    def stop(self, timeout: float = 5.0):
        with self._lock:
            if not self._started:
                return
            self._started = False
            self.stop_event.set()
        for w in (self.recon, self.guardian):
            if w.is_alive():
                w.join(timeout=timeout)
        self.store.add_event("swarm_stopped", "orchestrator")
        self.store.close()

    def is_running(self) -> bool:
        return bool(self._started and (
            self.recon.is_alive() or self.guardian.is_alive()
        ))

    # ------------------------------------------------------------------
    # Autorización / trazabilidad
    # ------------------------------------------------------------------
    def authorize_command(self, command: str, agent_role: str = "main",
                          target: str | None = None) -> PolicyDecision:
        return self.policy.authorize(command, agent_role, target or self.target)

    def record_command(self, command: str, rc: int, output: str,
                       agent_role: str = "main",
                       target: str | None = None) -> int:
        """Registra un comando del agente principal/subagente para auditoría
        y para que cuente en los límites de frecuencia."""
        target = target or self.target
        fp = command_fingerprint(command, target)
        role = agent_role if agent_role in ("main", "recon", "validation",
                                            "subagent") else "main"
        tid = self.store.enqueue_task(
            role, kind="command", target=target, command=command,
            priority=5, payload={"agent": agent_role}, fingerprint=fp,
        )
        self.store.finish_task(
            tid, "done" if rc == 0 else "failed", output or "", rc,
        )
        self.store.add_event(
            "command_executed", agent_role, tid,
            {"command": command, "rc": rc, "bytes": len(output or "")},
        )
        return tid

    # ------------------------------------------------------------------
    # API de tareas / hallazgos
    # ------------------------------------------------------------------
    def submit_recon_task(self, command: str, target: str | None = None,
                          priority: int = 5, payload: dict | None = None):
        target = target or self.target
        decision = self.policy.authorize(command, "recon", target)
        if decision.blocked or not decision.allowed:
            return None, decision
        if decision.fingerprint:
            dup = self.store.find_duplicate(decision.fingerprint, 3600)
            if dup:
                return None, PolicyDecision(
                    False, True, False, AutonomyLevel.HUMAN_APPROVAL,
                    f"duplicado de tarea #{dup.id}", fingerprint=decision.fingerprint,
                    duplicate_of=dup.id, target=target,
                )
        tid = self.store.enqueue_task(
            "recon", kind="command", target=target, command=command,
            priority=priority, payload=payload or {},
            fingerprint=decision.fingerprint,
        )
        self.store.add_event(
            "recon_task_submitted", "orchestrator", tid,
            {"command": command, "priority": priority},
        )
        return tid, decision

    def submit_finding(self, title: str, target: str | None = None,
                       severity: str = "info", claim: str = "",
                       evidence: str = "", created_by: str = "main",
                       auto_validate: bool = True) -> int:
        target = target or self.target
        fid = self.store.add_finding(
            target=target, title=title, severity=severity,
            claim=claim or title, evidence=evidence,
            created_by=created_by,
        )
        self.store.add_event(
            "finding_submitted", created_by, payload={
                "finding_id": fid, "title": title, "severity": severity,
            },
        )
        if auto_validate:
            self.request_validation(fid)
        return fid

    def cancel_task(self, task_id: int, reason: str = "") -> bool:
        ok = self.store.cancel_task(task_id, reason)
        if ok:
            self.store.add_event(
                "task_cancelled", "orchestrator", task_id,
                {"reason": reason},
            )
        return ok

    def request_validation(self, finding_id: int) -> int | None:
        finding = self.store.get_finding(finding_id)
        if not finding:
            return None
        tid = self.store.enqueue_task(
            "validation", kind="validate", target=finding.target,
            finding_id=finding_id, priority=3,
        )
        self.store.add_event(
            "validation_requested", "orchestrator", tid,
            {"finding_id": finding_id},
        )
        return tid

    def add_evidence(self, finding_id: int, path: str = "",
                     excerpt: str = "", task_id: int | None = None) -> int:
        sha = self.store.file_sha256(path) if path else ""
        return self.store.add_evidence(
            finding_id=finding_id, task_id=task_id, path=path,
            sha256=sha, excerpt=excerpt,
        )

    def block_target(self, target: str, reason: str = "") -> int:
        bid = self.store.add_block(target, reason)
        self.store.add_event(
            "target_blocked", "orchestrator",
            payload={"target": target, "reason": reason},
        )
        return bid

    def clear_blocks(self, target: str | None = None):
        self.store.clear_blocks(target)

    # ------------------------------------------------------------------
    # Plan de recon desde el scope
    # ------------------------------------------------------------------
    def plan_from_scope(self, enqueue: bool = False,
                        target: str | None = None) -> list[str]:
        target = target or self.target
        cmds: list[str] = []
        for dom in sorted(self.scope.domains):
            cmds.append(f"subfinder -d {dom} -silent")
            cmds.append(f"whatweb https://{dom}")
        for ip in sorted(self.scope.ips):
            cmds.append(f"nmap -sV -T4 {ip}")
        for net in self.scope.networks:
            cmds.append(f"nmap -sn -T4 {net}")
        # Deduplicar preservando orden.
        seen = set()
        cmds = [c for c in cmds if not (c in seen or seen.add(c))]
        if enqueue:
            for c in cmds:
                self.submit_recon_task(c, target=target)
        return cmds

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    def status(self) -> dict:
        return {
            "running": self.is_running(),
            "target": self.target,
            "scope": self.scope.describe(),
            "scope_empty": self.scope.is_empty(),
            "autonomy_level": self.autonomy_level,
            "workers": {
                "recon": self.recon.is_alive(),
                "guardian": self.guardian.is_alive(),
            },
            "stats": self.store.stats(),
            "agents": self.store.list_agents(),
            "recent_events": self.store.list_events(10),
        }

    def format_status(self) -> str:
        s = self.status()
        st = s["stats"]
        lines = [
            f"Enjambre: {'ACTIVO' if s['running'] else 'detenido'}",
            f"Target: {s['target'] or '(ninguno)'}",
            f"Scope: {s['scope']}",
            f"Autonomía: {s['autonomy_level']} (máx. autoaprobado; "
            f"nivel 3 siempre pide aprobación humana)",
            f"Workers: recon={'ON' if s['workers']['recon'] else 'off'} · "
            f"guardian={'ON' if s['workers']['guardian'] else 'off'}",
            f"Tareas: {st['tasks']}",
            f"Hallazgos: {st['findings']}",
            f"Activos: {st['assets']} · eventos: {st['events']} · "
            f"bloqueos activos: {st['active_blocks']}",
        ]
        if s["scope_empty"]:
            lines.append("⚠ Scope vacío: los comandos con host serán bloqueados.")
        return "\n".join(lines)
