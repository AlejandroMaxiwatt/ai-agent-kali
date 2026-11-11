"""Tests del motor de políticas determinista del enjambre."""

import os
import tempfile
import unittest

from agent_swarm.models import AutonomyLevel
from agent_swarm.policy import (
    PolicyEngine,
    Scope,
    classify_risk,
    command_fingerprint,
    extract_hosts,
)
from agent_swarm.store import Store


class TestScope(unittest.TestCase):
    def test_parse_and_contains(self):
        scope = Scope.from_text(
            "En alcance: example.com, sub.example.org, 10.0.0.5, "
            "192.168.1.0/24\nFuera de alcance: bad.example.com 8.8.8.8",
            target="acme",
        )
        self.assertTrue(scope.contains("example.com"))
        self.assertTrue(scope.contains("www.example.com"))
        self.assertTrue(scope.contains("sub.example.org"))
        self.assertTrue(scope.contains("10.0.0.5"))
        self.assertTrue(scope.contains("192.168.1.42"))
        self.assertFalse(scope.contains("8.8.8.8"))
        self.assertFalse(scope.contains("bad.example.com"))
        self.assertFalse(scope.contains("other.com"))
        self.assertTrue(scope.contains("acme"))

    def test_empty_scope(self):
        self.assertTrue(Scope.from_text("").is_empty())

    def test_extract_hosts(self):
        hosts = extract_hosts(
            "nmap -sV 10.0.0.1 && curl https://example.com/a/b"
        )
        self.assertIn("10.0.0.1", hosts)
        self.assertIn("example.com", hosts)


class TestRisk(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(int(classify_risk("ls -la")[0]), 1)
        self.assertEqual(int(classify_risk("nmap -sV 10.0.0.1")[0]), 2)
        self.assertEqual(
            int(classify_risk("sqlmap -u http://x/?id=1")[0]), 3
        )
        self.assertEqual(int(classify_risk("rm -rf /tmp/x")[0]), 4)
        # Desconocida → aprobación humana.
        self.assertEqual(int(classify_risk("binario-raro --x")[0]), 3)

    def test_bash_wrapper_unwrapped(self):
        self.assertEqual(
            int(classify_risk('bash -c "nmap -sV 10.0.0.1"')[0]), 2
        )

    def test_fingerprint_stable(self):
        a = command_fingerprint("nmap -sV 10.0.0.1 -oN out.txt", "t")
        b = command_fingerprint("nmap  -sV  10.0.0.1", "t")
        self.assertEqual(a, b)
        c = command_fingerprint("nmap -sV 10.0.0.2", "t")
        self.assertNotEqual(a, c)


class TestPolicyEngine(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.path)
        self.store = Store(self.path)
        self.scope = Scope.from_text("10.0.0.0/24 example.com", target="t")
        self.policy = PolicyEngine(
            self.store, self.scope, autonomy_level=2,
            per_minute=30, per_hour=300,
        )

    def tearDown(self):
        self.store.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(self.path + suffix)
            except OSError:
                pass

    def test_in_scope_allowed(self):
        d = self.policy.authorize("nmap -sV 10.0.0.1", "main", "t")
        self.assertTrue(d.allowed)
        self.assertFalse(d.blocked)
        self.assertEqual(int(d.level), AutonomyLevel.PREAPPROVED)

    def test_out_of_scope_blocked(self):
        d = self.policy.authorize("nmap -sV 8.8.8.8", "main", "t")
        self.assertTrue(d.blocked)
        self.assertIn("fuera de alcance", d.reason)

    def test_no_scope_blocks_hosts(self):
        p = PolicyEngine(self.store, Scope(), autonomy_level=2)
        d = p.authorize("nmap -sV 10.0.0.1", "main", "t")
        self.assertTrue(d.blocked)
        self.assertIn("scope", d.reason)

    def test_level3_requires_human_approval(self):
        d = self.policy.authorize(
            "sqlmap -u http://example.com/?id=1", "main", "t"
        )
        self.assertFalse(d.allowed)
        self.assertFalse(d.blocked)
        self.assertTrue(d.requires_approval)
        self.assertEqual(int(d.level), AutonomyLevel.HUMAN_APPROVAL)

    def test_background_role_cannot_level3(self):
        d = self.policy.authorize(
            "sqlmap -u http://example.com/?id=1", "recon", "t"
        )
        self.assertTrue(d.blocked)

    def test_destructive_blocked(self):
        d = self.policy.authorize("rm -rf /tmp/x", "main", "t")
        self.assertTrue(d.blocked)

    def test_duplicate_requires_approval(self):
        cmd = "nmap -sV 10.0.0.1"
        d1 = self.policy.authorize(cmd, "main", "t")
        self.assertTrue(d1.allowed)
        self.store.enqueue_task(
            "main", target="t", command=cmd, fingerprint=d1.fingerprint,
        )
        d2 = self.policy.authorize(cmd, "main", "t")
        self.assertTrue(d2.requires_approval)
        self.assertIn("duplicado", d2.reason)

    def test_rate_limit(self):
        p = PolicyEngine(self.store, self.scope, autonomy_level=2,
                         per_minute=1, per_hour=100)
        d1 = p.authorize("nmap -sV 10.0.0.1", "main", "t")
        self.assertTrue(d1.allowed)
        self.store.enqueue_task("main", target="t",
                                command="nmap -sV 10.0.0.1",
                                fingerprint=d1.fingerprint)
        d2 = p.authorize("nmap -sV 10.0.0.2", "main", "t")
        self.assertTrue(d2.requires_approval)
        self.assertIn("rate limit", d2.reason)


if __name__ == "__main__":
    unittest.main()
