"""Tests del núcleo desacoplado (agent_core). No requieren Rich ni LLM."""

import os
import tempfile
import unittest

from agent_core.goalspec import GoalSpec, parse_duration_seconds, verify_goal_criteria
from agent_core.results import CommandResult


class TestCommandResult(unittest.TestCase):
    def test_defaults_and_str(self):
        r = CommandResult(rc=0, output="hola")
        self.assertTrue(r.ok)
        self.assertEqual(str(r), "hola")
        self.assertEqual(r.artifacts, [])

    def test_failure(self):
        r = CommandResult(rc=7, stderr="boom")
        self.assertFalse(r.ok)


class TestGoalSpec(unittest.TestCase):
    def test_full_spec(self):
        s = GoalSpec.parse(
            "Comprometer TYPO3 || criteria: file_exists:/tmp/x; "
            "file_contains:/tmp/x:FLAG\\{ ; cmd_rc:true || "
            "budget: 2h, 50 comandos || constraints: no_destructive, "
            "no_bruteforce || target: acme"
        )
        self.assertEqual(s.goal, "Comprometer TYPO3")
        self.assertEqual(len(s.criteria), 3)
        self.assertEqual(s.budget_seconds, 7200)
        self.assertEqual(s.budget_commands, 50)
        self.assertEqual(s.constraints, ["no_destructive", "no_bruteforce"])
        self.assertEqual(s.target, "acme")

    def test_plain_goal(self):
        s = GoalSpec.parse("solo un objetivo")
        self.assertEqual(s.goal, "solo un objetivo")
        self.assertEqual(s.criteria, [])
        self.assertIsNone(s.budget_seconds)

    def test_line_based_spec(self):
        s = GoalSpec.parse(
            "goal: Comprometer el panel\n"
            "criteria:\n"
            "  - file_exists:/tmp/x\n"
            "  - cmd_rc:true\n"
            "budget: 1h, 20 comandos\n"
            "constraints: no_destructive\n"
            "target: acme\n"
        )
        self.assertEqual(s.goal, "Comprometer el panel")
        self.assertEqual(s.criteria, ["file_exists:/tmp/x", "cmd_rc:true"])
        self.assertEqual(s.budget_seconds, 3600)
        self.assertEqual(s.budget_commands, 20)
        self.assertEqual(s.constraints, ["no_destructive"])
        self.assertEqual(s.target, "acme")

    def test_duration(self):
        self.assertEqual(parse_duration_seconds("90"), 90)
        self.assertEqual(parse_duration_seconds("30m"), 1800)
        self.assertEqual(parse_duration_seconds("2h"), 7200)
        self.assertIsNone(parse_duration_seconds("xx"))


class TestVerifier(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("hola FLAG{abc} mundo\n")
        os.makedirs("/tmp/agent-core-test-dir", exist_ok=True)

    def tearDown(self):
        os.unlink(self.path)
        try:
            os.rmdir("/tmp/agent-core-test-dir")
        except OSError:
            pass

    def test_all_types(self):
        v = verify_goal_criteria([
            f"file_exists:{self.path}",
            f"file_contains:{self.path}:FLAG\\{{",
            "cmd_rc:true",
            "cmd_rc:false",
            f"file_missing:{self.path}.nope",
            "dir_exists:/tmp/agent-core-test-dir",
            "port_open:127.0.0.1:1",
        ])
        self.assertFalse(v["ok"])
        self.assertEqual(
            [r["ok"] for r in v["results"]],
            [True, True, True, False, True, True, False],
        )

    def test_all_ok(self):
        v = verify_goal_criteria([
            f"file_exists:{self.path}",
            "cmd_rc:true",
        ])
        self.assertTrue(v["ok"])
        self.assertFalse(v["unknown"])

    def test_no_criteria(self):
        v = verify_goal_criteria([])
        self.assertIsNone(v["ok"])
        self.assertTrue(v["unknown"])


if __name__ == "__main__":
    unittest.main()
