"""Tests de integración del orquestador del enjambre."""

import os
import shutil
import tempfile
import time
import unittest
from types import SimpleNamespace

from agent_swarm.orchestrator import SwarmOrchestrator


class TestSwarmOrchestrator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="swarm-test-")
        self.db = os.path.join(self.tmp, "swarm.db")
        self.orch = SwarmOrchestrator(
            store_path=self.db, target="t",
            scope_text="10.0.0.0/24 example.com",
            autonomy_level=2, runner=self._runner, poll_interval=0.05,
        )
        self.orch.start()

    def tearDown(self):
        self._wait_idle()
        self.orch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _runner(command, task):
        return SimpleNamespace(rc=0, output=(
            "PORT   STATE SERVICE VERSION\n"
            "80/tcp open  http    Apache httpd 2.4.49\n"
            "443/tcp open https\n"
        ))

    def _wait(self, fn, timeout=6.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            value = fn()
            if value:
                return value
            time.sleep(0.05)
        return fn()

    def _wait_idle(self, timeout=6.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            stats = self.orch.store.task_stats()
            active = sum(
                v.get("pending", 0) + v.get("running", 0)
                for v in stats.values()
            )
            if active == 0:
                return
            time.sleep(0.05)

    def _wait_task(self, tid):
        def check():
            t = self.orch.store.get_task(tid)
            return t if t and t.status in ("done", "failed", "blocked") else None
        return self._wait(check)

    def test_recon_assets_and_followups(self):
        tid, decision = self.orch.submit_recon_task("nmap -sV 10.0.0.1")
        self.assertIsNotNone(tid)
        self.assertTrue(decision.allowed)
        task = self._wait_task(tid)
        self.assertEqual(task.status, "done")

        # El worker marca la tarea como done antes de procesar activos y
        # seguimientos; esperamos a que termine ese post-proceso.
        def ready():
            assets = self.orch.store.list_assets("t")
            tasks = self.orch.store.list_tasks(role="recon", limit=20)
            followup = any("whatweb" in (t.command or "") for t in tasks)
            return (assets, tasks) if len(assets) >= 2 and followup else None

        assets, tasks = self._wait(ready)
        self.assertGreaterEqual(len(assets), 2)
        self.assertTrue(any("whatweb" in (t.command or "") for t in tasks))

    def test_cancel_running_task(self):
        def slow_runner(command, task):
            for _ in range(500):
                if (task.cancel_event is not None
                        and task.cancel_event.is_set()):
                    return SimpleNamespace(rc=-2, output="cancelado")
                time.sleep(0.01)
            return SimpleNamespace(rc=0, output="done")

        self.orch.recon.runner = slow_runner
        tid, decision = self.orch.submit_recon_task("sleep 1")
        self.assertIsNotNone(tid, decision)

        def running():
            t = self.orch.store.get_task(tid)
            return t if t and t.status == "running" else None

        self.assertIsNotNone(self._wait(running))
        self.assertTrue(self.orch.cancel_task(tid, "cancelación de test"))

        def cancelled():
            t = self.orch.store.get_task(tid)
            return t if t and t.status == "cancelled" else None

        task = self._wait(cancelled)
        self.assertIsNotNone(task, self.orch.store.get_task(tid))

    def test_out_of_scope_task_rejected(self):
        tid, decision = self.orch.submit_recon_task("nmap -sV 8.8.8.8")
        self.assertIsNone(tid)
        self.assertTrue(decision.blocked)

    def test_guardian_confirms_with_proof(self):
        ev = os.path.join(self.tmp, "evidence.txt")
        with open(ev, "w", encoding="utf-8") as f:
            f.write("CVE-2021-41773 exploit confirmed uid=0 root shell\n")
        fid = self.orch.submit_finding(
            "Apache RCE", severity="critical",
            claim="Apache 2.4.49 vulnerable a CVE-2021-41773",
            auto_validate=False,
        )
        self.orch.add_evidence(fid, path=ev)
        self.orch.request_validation(fid)

        def resolved():
            finding = self.orch.store.get_finding(fid)
            return finding if finding.status != "pending_validation" else None

        finding = self._wait(resolved)
        self.assertEqual(finding.status, "confirmed", finding)

    def test_guardian_llm_second_opinion(self):
        # Determinista no concluyente → el validador LLM (falso) confirma.
        self.orch.guardian.llm_validator = (
            lambda finding, texts, scope: {
                "decision": "confirmed", "confidence": 0.9,
                "reason": "validación LLM simulada",
            }
        )
        fid = self.orch.submit_finding(
            "Hallazgo sin prueba determinista", severity="high",
            claim="La versión 1.2 parece vulnerable",
            auto_validate=False,
        )
        self.orch.request_validation(fid)

        def resolved():
            finding = self.orch.store.get_finding(fid)
            return finding if finding.status != "pending_validation" else None

        finding = self._wait(resolved)
        self.assertEqual(finding.status, "confirmed", finding)
        decisions = self.orch.store.decisions_for_finding(fid)
        self.assertTrue(any(d.decision == "confirmed" for d in decisions))

    def test_guardian_requires_more_evidence_for_version_only(self):
        fid = self.orch.submit_finding(
            "Apache version match", severity="high",
            claim="La versión 2.4.49 coincide con una afectada",
        )

        def resolved():
            finding = self.orch.store.get_finding(fid)
            return finding if finding.status != "pending_validation" else None

        finding = self._wait(resolved)
        self.assertEqual(finding.status, "needs_more_evidence", finding)

    def test_guardian_rejects_out_of_scope(self):
        fid = self.orch.submit_finding(
            "Fuera de alcance", target="8.8.8.8", severity="high",
            claim="CVE-2021-41773 exploit confirmed",
        )

        def resolved():
            finding = self.orch.store.get_finding(fid)
            return finding if finding.status != "pending_validation" else None

        finding = self._wait(resolved)
        self.assertEqual(finding.status, "rejected", finding)


if __name__ == "__main__":
    unittest.main()
