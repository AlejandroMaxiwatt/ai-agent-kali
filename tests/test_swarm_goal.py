"""Tests del controlador `swarm goal` sobre el enjambre permanente."""

import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace

from agent_swarm import SwarmOrchestrator
from agent_swarm.goal_runner import SwarmGoalRunner, SwarmGoalSpec


class TestSwarmGoalRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="swarm-goal-test-")
        self.db = os.path.join(self.tmp, "swarm.db")
        self.crit = os.path.join(self.tmp, "done.txt")

        def runner(command, task):
            # Simula una herramienta que produce un hallazgo y deja la
            # evidencia/criterio en disco.
            with open(self.crit, "w", encoding="utf-8") as f:
                f.write("ok\n")
            return SimpleNamespace(
                rc=0,
                output=("PORT   STATE SERVICE VERSION\n"
                        "80/tcp open  http    Apache httpd 2.4.49\n"),
            )

        self.orch = SwarmOrchestrator(
            store_path=self.db, target="t",
            scope_text="10.0.0.0/24", autonomy_level=2,
            runner=runner, poll_interval=0.05,
        )
        self.orch.start()
        self.calls = 0

        def planner(context):
            self.calls += 1
            if self.calls == 1:
                return {
                    "action": "plan",
                    "tasks": [{
                        "command": "nmap -sV 10.0.0.1",
                        "target": "10.0.0.1",
                        "priority": 3,
                        "reason": "descubrir servicios",
                    }],
                }
            return {
                "action": "done",
                "reason": "El criterio se cumplió",
                "summary": "Activo descubierto y criterio verificado",
            }

        self.spec = SwarmGoalSpec(
            goal="Reconocer 10.0.0.1",
            criteria=[f"file_exists:{self.crit}"],
            target="t", budget_seconds=60, budget_commands=50,
            max_rounds=3,
        )
        self.goal = SwarmGoalRunner(
            self.orch, self.spec, planner, self.tmp,
            poll_interval=0.05, round_timeout=10,
        )

    def tearDown(self):
        self.goal.kill_event.set()
        if self.goal.is_alive():
            self.goal.join(timeout=5)
        self.orch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_goal_completes_and_verifies(self):
        self.goal.start()
        self.goal.join(timeout=15)
        self.assertFalse(self.goal.is_alive())
        self.assertEqual(self.goal.status, "done", self.goal.outcome_reason)
        self.assertTrue(os.path.exists(self.crit))
        self.assertGreaterEqual(self.calls, 1)
        self.assertTrue(self.goal.verifications)
        self.assertTrue(self.goal.verifications[-1]["ok"])
        self.assertTrue(self.goal.attempts)
        self.assertTrue(self.goal.report_path)
        self.assertTrue(os.path.exists(self.goal.report_path))

    def test_budget_exhausted(self):
        self.spec.budget_seconds = 1
        self.goal.started_epoch -= 10
        # El planner no debe llegar a ejecutarse si ya nació agotado.
        self.goal.planner = lambda ctx: (_ for _ in ()).throw(
            AssertionError("no debe planificar sin presupuesto")
        )
        self.goal.start()
        self.goal.join(timeout=10)
        self.assertEqual(self.goal.status, "budget_exhausted")


if __name__ == "__main__":
    unittest.main()
