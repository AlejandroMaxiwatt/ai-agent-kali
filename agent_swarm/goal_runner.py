"""Controlador de un objetivo sobre el enjambre permanente.

A diferencia de `GoalRun` (que lanza subagentes temporales por fase), este
runner usa el ReconWorker y el GuardianWorker permanentes:

    plan LLM → enqueue recon → wait → verificar criterios → replan

El LLM no ejecuta comandos: solo propone tareas de recon (nivel 1-2) y
decisiones. El motor de políticas sigue siendo la autoridad final.
"""

from __future__ import annotations

import dataclasses
import json
import os
import threading
import time
from datetime import datetime, timezone

from agent_core.goalspec import GoalSpec, verify_goal_criteria


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclasses.dataclass
class SwarmGoalSpec:
    goal: str
    criteria: list = dataclasses.field(default_factory=list)
    target: str | None = None
    budget_seconds: int = 6 * 3600
    budget_commands: int = 400
    max_rounds: int = 10

    @classmethod
    def from_goal_spec(cls, spec: GoalSpec, target=None,
                       max_rounds: int = 10) -> "SwarmGoalSpec":
        return cls(
            goal=spec.goal,
            criteria=list(spec.criteria),
            target=target or spec.target,
            budget_seconds=spec.budget_seconds or 6 * 3600,
            budget_commands=spec.budget_commands or 400,
            max_rounds=max_rounds,
        )

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SwarmGoalSpec":
        return cls(
            goal=data.get("goal", ""),
            criteria=list(data.get("criteria", [])),
            target=data.get("target"),
            budget_seconds=int(data.get("budget_seconds") or 6 * 3600),
            budget_commands=int(data.get("budget_commands") or 400),
            max_rounds=int(data.get("max_rounds") or 10),
        )


class SwarmGoalRunner(threading.Thread):
    """Hilo que planifica, encola y verifica hasta cumplir el objetivo."""

    def __init__(self, swarm, spec: SwarmGoalSpec, planner,
                 workspace: str, poll_interval: float = 2.0,
                 round_timeout: float = 1800.0, kill_event=None,
                 goal_id: str | None = None,
                 initial_state: dict | None = None):
        super().__init__(name="swarm-goal", daemon=True)
        self.swarm = swarm
        self.spec = spec
        self.planner = planner
        self.workspace = workspace
        self.poll_interval = float(poll_interval)
        self.round_timeout = float(round_timeout)
        self.kill_event = kill_event or threading.Event()
        self.id = goal_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.status = "pending"
        self.rounds = 0
        self.attempts = []
        self.dead_ends = []
        self.verifications = []
        self.summary = ""
        self.outcome_reason = ""
        self.started_at = _now()
        self.started_epoch = time.time()
        self.finished_at = ""
        self.report_path = None
        self.state_dir = os.path.join(workspace, "memory", "swarm", "goals")
        os.makedirs(self.state_dir, exist_ok=True)
        self.state_path = os.path.join(self.state_dir, f"{self.id}.state.json")
        if initial_state:
            self._apply_state(initial_state)
            # Reanudar concede una ventana nueva de presupuesto (igual que
            # `goal resume`), conservando rondas/intentos/dead-ends.
            self.started_at = _now()
            self.started_epoch = time.time()

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "spec": self.spec.to_dict(),
            "status": self.status,
            "rounds": self.rounds,
            "attempts": self.attempts,
            "dead_ends": self.dead_ends,
            "verifications": self.verifications,
            "summary": self.summary,
            "outcome_reason": self.outcome_reason,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "report_path": self.report_path,
            "saved_at": _now(),
        }

    def _apply_state(self, data: dict):
        self.status = data.get("status", "pending")
        self.rounds = int(data.get("rounds", 0))
        self.attempts = list(data.get("attempts", []))
        self.dead_ends = list(data.get("dead_ends", []))
        self.verifications = list(data.get("verifications", []))
        self.summary = data.get("summary", "")
        self.outcome_reason = data.get("outcome_reason", "")
        self.started_at = data.get("started_at", self.started_at)
        self.finished_at = data.get("finished_at", "")
        self.report_path = data.get("report_path")
        # Si se reanuda, conservar el tiempo de inicio original.
        try:
            self.started_epoch = datetime.fromisoformat(
                self.started_at
            ).timestamp()
        except Exception:
            self.started_epoch = time.time()

    def save_state(self):
        try:
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.state_path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Bucle
    # ------------------------------------------------------------------
    def run(self):
        self.status = "running"
        self.swarm.store.add_event(
            "swarm_goal_started", "swarm-goal", payload={
                "goal_id": self.id, "goal": self.spec.goal,
                "criteria": self.spec.criteria, "target": self.spec.target,
                "rounds": self.rounds,
            },
        )
        self.save_state()
        try:
            v0 = self._verify()
            self.verifications.append(v0)
            if v0.get("ok"):
                self.status = "done"
                self.outcome_reason = "Criterios ya cumplidos al inicio."
                self.summary = v0.get("summary", "")
                return

            while self.rounds < self.spec.max_rounds:
                if self.kill_event.is_set():
                    self.status = "killed"
                    self.outcome_reason = "Kill solicitado por el operador."
                    return

                budget = self._budget_status()
                if budget["exhausted"]:
                    self.status = "budget_exhausted"
                    self.outcome_reason = f"Presupuesto agotado: {budget['detail']}"
                    return

                ctx = self.planner_context()
                plan = self.planner(ctx) or {}
                action = (plan.get("action") or "").lower()

                if action == "done":
                    v = self._verify()
                    self.verifications.append(v)
                    if v.get("ok") or v.get("unknown"):
                        self.status = "done"
                        self.outcome_reason = plan.get("reason", "")
                        self.summary = plan.get("summary", "") or v.get("summary", "")
                        return
                    self.dead_ends.append(
                        f"Ronda {self.rounds + 1}: GOAL_DONE rechazado · "
                        f"{v.get('summary', '').splitlines()[0]}"
                    )
                    self.rounds += 1
                    self.save_state()
                    continue

                if action == "blocked":
                    reason = plan.get("reason", "bloqueado")
                    self.dead_ends.append(f"Ronda {self.rounds + 1}: {reason}")
                    self.rounds += 1
                    self.save_state()
                    continue

                tasks = plan.get("tasks") or []
                if not tasks:
                    self.dead_ends.append(
                        f"Ronda {self.rounds + 1}: plan vacío"
                    )
                    self.rounds += 1
                    self.save_state()
                    continue

                enqueued = []
                for t in tasks:
                    if not isinstance(t, dict):
                        continue
                    cmd = (t.get("command") or "").strip()
                    if not cmd:
                        continue
                    target = t.get("target") or self.spec.target
                    try:
                        prio = int(t.get("priority", 5))
                    except (TypeError, ValueError):
                        prio = 5
                    tid, decision = self.swarm.submit_recon_task(
                        cmd, target=target, priority=prio,
                        payload={
                            "origin": "swarm-goal",
                            "goal_id": self.id,
                            "round": self.rounds + 1,
                            "reason": t.get("reason", ""),
                        },
                    )
                    if tid:
                        enqueued.append(tid)
                        self.attempts.append({
                            "round": self.rounds + 1,
                            "task_id": tid,
                            "command": cmd[:300],
                            "target": target,
                            "reason": t.get("reason", ""),
                        })
                    else:
                        self.dead_ends.append(
                            f"Ronda {self.rounds + 1}: rechazada `{cmd[:120]}` "
                            f"· {decision.reason}"
                        )

                self.rounds += 1
                self.save_state()
                if not enqueued:
                    continue

                self._wait_for_idle(self._remaining_round_timeout())
                v = self._verify()
                self.verifications.append(v)
                if v.get("ok"):
                    self.status = "done"
                    self.outcome_reason = "Criterios de éxito verificados."
                    self.summary = v.get("summary", "")
                    return
                self.save_state()

            self.status = "exhausted"
            self.outcome_reason = (
                f"Se agotaron las {self.spec.max_rounds} rondas sin "
                f"cumplir los criterios."
            )
        except Exception as e:
            self.status = "failed"
            self.outcome_reason = f"Excepción: {e}"
            self.swarm.store.add_event(
                "swarm_goal_error", "swarm-goal",
                payload={"goal_id": self.id, "error": str(e)},
            )
        finally:
            self.finished_at = _now()
            try:
                self.report_path = self._generate_report()
            except Exception:
                self.report_path = None
            self.save_state()
            try:
                self.swarm.store.add_event(
                    "swarm_goal_finished", "swarm-goal", payload={
                        "goal_id": self.id, "status": self.status,
                        "reason": self.outcome_reason,
                        "rounds": self.rounds,
                    },
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Contexto / verificación / presupuesto
    # ------------------------------------------------------------------
    def planner_context(self) -> dict:
        store = self.swarm.store
        findings = {}
        for status in ("confirmed", "pending_validation",
                       "needs_more_evidence", "rejected"):
            findings[status] = [
                {"id": f.id, "severity": f.severity, "title": f.title}
                for f in store.list_findings(
                    status=status, target=self.spec.target, limit=10,
                )
            ]
        tasks = [
            {"id": t.id, "status": t.status, "rc": t.rc,
             "command": (t.command or "")[:200]}
            for t in store.list_tasks(limit=12)
        ]
        assets = [
            {"host": a.get("host"), "port": a.get("port"),
             "service": a.get("service"), "version": a.get("version")}
            for a in store.list_assets(self.spec.target, limit=50)
        ]
        budget = self._budget_status()
        return {
            "goal_id": self.id,
            "goal": self.spec.goal,
            "criteria": self.spec.criteria,
            "target": self.spec.target,
            "scope": self.swarm.scope.describe(),
            "autonomy_level": self.swarm.autonomy_level,
            "round": self.rounds + 1,
            "max_rounds": self.spec.max_rounds,
            "budget": budget,
            "assets": assets,
            "findings": findings,
            "tasks": tasks,
            "attempts": self.attempts[-8:],
            "dead_ends": self.dead_ends[-8:],
            "recent_events": store.list_events(10),
        }

    def _verify(self) -> dict:
        return verify_goal_criteria(self.spec.criteria, self.workspace)

    def _budget_status(self) -> dict:
        elapsed = max(0.0, time.time() - self.started_epoch)
        used = 0
        try:
            used = self.swarm.store.count_tasks_since(self.started_at)
        except Exception:
            pass
        reasons = []
        if self.spec.budget_seconds and elapsed >= self.spec.budget_seconds:
            reasons.append(
                f"tiempo {elapsed/60:.0f}/{self.spec.budget_seconds/60:.0f} min"
            )
        if self.spec.budget_commands and used >= self.spec.budget_commands:
            reasons.append(
                f"comandos {used}/{self.spec.budget_commands}"
            )
        return {
            "elapsed_s": elapsed,
            "commands_used": used,
            "budget_seconds": self.spec.budget_seconds,
            "budget_commands": self.spec.budget_commands,
            "exhausted": bool(reasons),
            "detail": " · ".join(reasons),
        }

    def _remaining_round_timeout(self) -> float:
        remaining = self.round_timeout
        if self.spec.budget_seconds:
            left = self.spec.budget_seconds - (
                time.time() - self.started_epoch
            )
            remaining = min(remaining, max(30.0, left))
        return remaining

    def _wait_for_idle(self, timeout: float):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.kill_event.is_set():
                return
            stats = self.swarm.store.task_stats()
            active = sum(
                v.get("pending", 0) + v.get("running", 0)
                for v in stats.values()
            )
            if active == 0:
                # El Guardian puede haber dejado findings pendientes sin
                # tarea de validación; en ese caso pedimos validación.
                pending = self.swarm.store.list_findings(
                    status="pending_validation",
                    target=self.spec.target, limit=500,
                )
                if not pending:
                    return
                for f in pending[:20]:
                    self.swarm.request_validation(f.id)
            time.sleep(self.poll_interval)

    # ------------------------------------------------------------------
    # Informe / estado
    # ------------------------------------------------------------------
    def _generate_report(self) -> str | None:
        store = self.swarm.store
        reports_dir = os.path.join(self.workspace, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        target = self.spec.target or "adhoc"
        safe = "".join(c if c.isalnum() or c in "-_." else "_"
                       for c in target)
        path = os.path.join(
            reports_dir,
            f"swarm-goal-{self.id}-{safe}.md",
        )
        assets = store.list_assets(self.spec.target, limit=200)
        findings = store.list_findings(target=self.spec.target, limit=200)
        decisions = store.list_events(30)
        lines = [
            f"# Informe de objetivo · {self.spec.goal}",
            "",
            f"- **ID:** {self.id}",
            f"- **Estado:** {self.status}",
            f"- **Target:** {self.spec.target or '(ad-hoc)'}",
            f"- **Scope:** {self.swarm.scope.describe()}",
            f"- **Rondas:** {self.rounds}/{self.spec.max_rounds}",
            f"- **Inicio:** {self.started_at}",
            f"- **Fin:** {self.finished_at}",
            f"- **Motivo:** {self.outcome_reason}",
            "",
            "## Criterios",
            "",
        ]
        last_v = self.verifications[-1] if self.verifications else {}
        if last_v.get("results"):
            for r in last_v["results"]:
                lines.append(
                    f"- {'✓' if r.get('ok') else '✗'} "
                    f"{r.get('criterion')} — {r.get('detail')}"
                )
        else:
            lines.append("(sin criterios verificables)")
        lines += ["", "## Activos", ""]
        for a in assets:
            lines.append(
                f"- `{a.get('host')}:{a.get('port') or ''}` "
                f"{a.get('service') or ''} {a.get('version') or ''}"
            )
        lines += ["", "## Hallazgos", ""]
        for f in findings:
            lines.append(
                f"- #{f.id} [{f.severity}] ({f.status}) {f.title}"
            )
        lines += ["", "## Intentos", ""]
        for a in self.attempts:
            lines.append(
                f"- Ronda {a.get('round')} · tarea #{a.get('task_id')} · "
                f"`{a.get('command')}`"
            )
        lines += ["", "## Dead-ends", ""]
        for d in self.dead_ends:
            lines.append(f"- {d}")
        lines += ["", "## Eventos recientes", ""]
        for e in decisions:
            lines.append(f"- {e.get('ts')} · {e.get('type')} · "
                         f"{e.get('agent') or ''}")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return path

    def status_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.spec.goal,
            "target": self.spec.target,
            "status": self.status,
            "rounds": self.rounds,
            "max_rounds": self.spec.max_rounds,
            "criteria": self.spec.criteria,
            "budget": self._budget_status(),
            "summary": self.summary,
            "outcome_reason": self.outcome_reason,
            "report_path": self.report_path,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def _load_state(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_swarm_goals(workspace: str) -> list[dict]:
    state_dir = os.path.join(workspace, "memory", "swarm", "goals")
    if not os.path.isdir(state_dir):
        return []
    out = []
    for name in os.listdir(state_dir):
        if not name.endswith(".state.json"):
            continue
        data = _load_state(os.path.join(state_dir, name))
        if data:
            out.append(data)
    out.sort(key=lambda d: d.get("started_at", ""), reverse=True)
    return out


def load_swarm_goal(workspace: str, goal_id: str) -> dict | None:
    path = os.path.join(
        workspace, "memory", "swarm", "goals", f"{goal_id}.state.json"
    )
    return _load_state(path)
