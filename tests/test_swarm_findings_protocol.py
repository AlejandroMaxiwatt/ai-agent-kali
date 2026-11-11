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


if __name__ == "__main__":
    unittest.main()
