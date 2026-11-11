"""Tests del protocolo FINDING: del agente principal."""

import unittest

import agent


class TestFindingProtocol(unittest.TestCase):
    def test_extract(self):
        text = (
            "Análisis...\n"
            "FINDING: high | Apache CVE-2021-41773 | /cgi-bin devolvió "
            "/etc/passwd con uid=0\n"
            "Siguientes pasos: ..."
        )
        findings = agent.extract_findings(text)
        self.assertEqual(len(findings), 1)
        sev, title, claim = findings[0]
        self.assertEqual(sev, "high")
        self.assertEqual(title, "Apache CVE-2021-41773")
        self.assertIn("uid=0", claim)

    def test_case_insensitive(self):
        text = "FINDING: CRITICAL | X | evidencia"
        self.assertEqual(agent.extract_findings(text)[0][0], "critical")

    def test_invalid_severity_ignored(self):
        self.assertEqual(
            agent.extract_findings("FINDING: apocaliptico | X | Y"), []
        )

    def test_strip(self):
        text = "Antes\nFINDING: low | X | Y\nDespués"
        cleaned = agent.strip_findings(text)
        self.assertNotIn("FINDING:", cleaned)
        self.assertIn("Antes", cleaned)
        self.assertIn("Después", cleaned)

    def test_integration_with_fake_swarm(self):
        class FakeSwarm:
            def __init__(self):
                self.calls = []

            def submit_finding(self, title, severity="info", claim="",
                               created_by="main"):
                self.calls.append({
                    "title": title, "severity": severity,
                    "claim": claim, "created_by": created_by,
                })
                return 42

        fake = FakeSwarm()
        old = agent._SWARM
        agent._SWARM = fake
        try:
            text = (
                "Evidencia real.\n"
                "FINDING: high | SQLi en login | id=1 devolvió error SQL\n"
                "Siguiente: validar."
            )
            cleaned, msgs = agent._process_swarm_findings(text)
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(fake.calls[0]["severity"], "high")
            self.assertEqual(fake.calls[0]["title"], "SQLi en login")
            self.assertEqual(fake.calls[0]["created_by"], "main")
            self.assertTrue(any("#42" in m for m in msgs))
            self.assertNotIn("FINDING:", cleaned)
            self.assertIn("Evidencia real.", cleaned)
        finally:
            agent._SWARM = old

    def test_swarm_task_parser(self):
        text = (
            "Delego el recon:\n"
            "SWARM_TASK: nmap -sV 10.0.0.1\n"
            "  SWARM_TASK: whatweb https://example.com\n"
            "fin"
        )
        tasks = agent.extract_swarm_tasks(text)
        self.assertEqual(tasks, [
            "nmap -sV 10.0.0.1", "whatweb https://example.com",
        ])
        cleaned = agent.strip_swarm_tasks(text)
        self.assertNotIn("SWARM_TASK:", cleaned)
        self.assertIn("Delego el recon", cleaned)

    def test_swarm_task_integration_with_fake_swarm(self):
        class FakeSwarm:
            target = "t"

            def __init__(self):
                self.calls = []

            def submit_recon_task(self, command, target=None):
                self.calls.append((command, target))
                return 42, type("D", (), {"reason": "ok"})()

        fake = FakeSwarm()
        old = agent._SWARM
        agent._SWARM = fake
        try:
            cleaned, msgs = agent._process_swarm_tasks(
                "texto\nSWARM_TASK: nmap -sV 10.0.0.1\nfin"
            )
            self.assertEqual(fake.calls, [("nmap -sV 10.0.0.1", "t")])
            self.assertTrue(any("#42" in m for m in msgs))
            self.assertNotIn("SWARM_TASK:", cleaned)
        finally:
            agent._SWARM = old

    def test_no_swarm_still_strips(self):
        old = agent._SWARM
        agent._SWARM = None
        try:
            cleaned, msgs = agent._process_swarm_findings(
                "texto\nFINDING: low | X | Y\nfin"
            )
            self.assertEqual(msgs, [])
            self.assertNotIn("FINDING:", cleaned)
        finally:
            agent._SWARM = old


if __name__ == "__main__":
    unittest.main()
