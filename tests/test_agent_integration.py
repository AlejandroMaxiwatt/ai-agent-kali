"""Tests de integración del harness (P0/P1) sin llamar al LLM real.

Se monkeypatchean `_goal_request_plan` y `spawn_subagent` para simular el
ciclo completo de un goal: verificación objetiva, rechazo de GOAL_DONE falso,
DAG por dependencias y presupuesto.
"""

import os
import tempfile
import time
import unittest

import agent


class TestP0CommandExecution(unittest.TestCase):
    def setUp(self):
        self._proxy = agent.PROXY_MODE

    def tearDown(self):
        agent.PROXY_MODE = self._proxy
        with agent._subagents_lock:
            agent._subagents_registry.clear()

    def test_proxy_isolation_between_agents(self):
        meta = agent._handle_agent_meta_action(
            "agent:proxy off", proxy_mode="proxychains"
        )
        self.assertEqual(meta["proxy_mode"], "off")
        # El global del proceso NO cambia cuando el modo es scoped.
        self.assertNotEqual(agent.PROXY_MODE, "off")

    def test_run_command_returns_structured_result(self):
        res = agent.run_command(
            "printf hola", auto=True, target=None, proxy_mode="off"
        )
        self.assertIsInstance(res, agent.CommandResult)
        self.assertEqual(res.rc, 0)
        self.assertIn("hola", res.output)
        self.assertEqual(res.proxy_mode, "off")

    def test_run_command_failure_class(self):
        res = agent.run_command(
            "sh -c 'echo boom >&2; exit 7'",
            auto=True, target=None, proxy_mode="off",
        )
        self.assertEqual(res.rc, 7)
        self.assertIsNotNone(res.error_class)

    def test_headless_file_blocks(self):
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            out = agent.process_file_blocks_headless(
                f"[[FILE_WRITE: {path}]]\nlinea1\nlinea2\n[[/FILE_WRITE]]"
            )
            self.assertTrue(out["any"])
            self.assertTrue(out["had_successful_edit_or_write"])
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "linea1\nlinea2")

            out2 = agent.process_file_blocks_headless(f"[[FILE_READ: {path}]]")
            self.assertTrue(out2["read_messages"])
            self.assertIn("linea1", out2["read_messages"][0])
        finally:
            os.unlink(path)


class TestGoalController(unittest.TestCase):
    def setUp(self):
        self._orig_plan = agent._goal_request_plan
        self._orig_spawn = agent.spawn_subagent
        with agent._subagents_lock:
            agent._subagents_registry.clear()

    def tearDown(self):
        agent._goal_request_plan = self._orig_plan
        agent.spawn_subagent = self._orig_spawn
        with agent._subagents_lock:
            agent._subagents_registry.clear()

    def _fake_spawn(self, written_path, order):
        def _spawn(name, skill, task, target=None, goal_context=None,
                   success_criterion=None, allow_destructive=False):
            order.append(name)
            sub = agent.Subagent(
                name, skill, task, target,
                goal_context=goal_context,
                success_criterion=success_criterion,
            )
            sub.status = "done"
            sub.started_at = "now"
            sub.summary = "fake done"
            if written_path:
                with open(written_path, "w", encoding="utf-8") as f:
                    f.write("ok\n")
            with agent._subagents_lock:
                agent._subagents_registry[name] = sub
            return sub, None
        return _spawn

    def test_done_requires_verifier(self):
        crit = tempfile.mktemp(prefix="goal-test-")
        calls = {"n": 0}

        def fake_plan(gr, skills, max_attempts=3):
            calls["n"] += 1
            if calls["n"] == 1:
                # El LLM miente: dice done sin cumplir el criterio.
                return {"action": "done", "reason": "ya está", "summary": "fake"}
            if calls["n"] == 2:
                return {"action": "phase", "subagents": [{
                    "name": "writer", "skill": "x", "task": "escribe",
                    "depends_on": [], "success": f"file_exists:{crit}",
                }]}
            return {"action": "done", "reason": "verificado", "summary": "ok"}

        agent._goal_request_plan = fake_plan
        agent.spawn_subagent = self._fake_spawn(crit, [])
        try:
            gr = agent.GoalRun(
                f"test || criteria: file_exists:{crit}", target=None
            )
            agent._goal_run_loop(gr)
            self.assertEqual(gr.status, "done", gr.outcome_reason)
            self.assertTrue(gr.verifications[-1]["ok"])
            self.assertTrue(any("GOAL_DONE" in d for d in gr.dead_ends))
            self.assertGreaterEqual(gr.current_phase, 2)
        finally:
            try:
                os.unlink(crit)
            except OSError:
                pass

    def test_budget_exhausted(self):
        agent._goal_request_plan = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("no debe planificar si el presupuesto está agotado")
        )
        gr = agent.GoalRun(
            "test || criteria: file_exists:/tmp/no-existe-goal-test", target=None
        )
        gr.budget_seconds = 1
        gr.started_epoch = time.time() - 10
        agent._goal_run_loop(gr)
        self.assertEqual(gr.status, "budget_exhausted")

    def test_phase_dependency_order(self):
        order = []
        agent.spawn_subagent = self._fake_spawn(None, order)
        gr = agent.GoalRun("dag test", target=None)
        res = agent._goal_execute_phase(gr, 1, [
            {"name": "b", "skill": "x", "task": "B", "depends_on": ["a"]},
            {"name": "a", "skill": "x", "task": "A", "depends_on": []},
        ])
        self.assertFalse(res["killed"] or res["timed_out"])
        # b depende de a => a se lanza en la primera ola y b en la segunda.
        self.assertEqual(order, ["p1-a", "p1-b"])


if __name__ == "__main__":
    unittest.main()
