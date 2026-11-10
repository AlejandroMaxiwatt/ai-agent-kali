"""Tests de la tabla de despacho del REPL (refactor de main)."""

import unittest

import agent


def resolve(user_input):
    """Devuelve el nombre del handler que atendería `user_input` o None."""
    cmd_lower = user_input.lower()
    first_word = cmd_lower.split(maxsplit=1)[0] if cmd_lower else ""
    for kind, names, handler in agent._REPL_TABLE:
        key = cmd_lower if kind == "exact" else first_word
        if key in names:
            return handler.__name__
    return None


class TestReplDispatch(unittest.TestCase):
    def test_exact_commands(self):
        self.assertEqual(resolve("salir"), "_repl_salir")
        self.assertEqual(resolve("help"), "_repl_help")
        self.assertEqual(resolve("comandos"), "_repl_comandos")
        self.assertEqual(resolve("compact"), "_repl_compact")

    def test_exact_does_not_match_with_args(self):
        # El comportamiento original: "refresh foo" no es el comando refresh.
        self.assertIsNone(resolve("refresh ahora"))
        self.assertIsNone(resolve("compact ya"))

    def test_first_word_commands(self):
        self.assertEqual(resolve("models 2"), "_repl_models")
        self.assertEqual(resolve("goal status"), "_repl_goal")
        self.assertEqual(resolve("target acme"), "_repl_target")
        self.assertEqual(resolve("subagent list"), "_repl_subagent")
        self.assertEqual(resolve("auto steps 5"), "_repl_auto")
        self.assertEqual(resolve("timeout status"), "_repl_timeout")
        self.assertEqual(resolve("copy 2"), "_repl_copy")
        self.assertEqual(resolve("resume s-1"), "_repl_resume")

    def test_objetivo_collision_resolves_to_goal(self):
        # En el REPL original, "objetivo" siempre entraba por el handler goal.
        self.assertEqual(resolve("objetivo"), "_repl_goal")

    def test_free_text_falls_through(self):
        self.assertIsNone(resolve("texto libre para el modelo"))
        self.assertIsNone(resolve("@archivo.py"))

    def test_exit_sentinel(self):
        self.assertIs(
            agent._repl_salir("salir", "salir", "salir"),
            agent._REPL_EXIT,
        )

    def test_use_with_instruction_falls_through(self):
        orig_activate = agent.activate_skill
        orig_save = agent.save_session
        agent.activate_skill = lambda name: True
        agent.save_session = lambda: None
        try:
            result = agent._repl_use(
                "use recon analiza el target",
                "use recon analiza el target",
                "use",
            )
            self.assertIsInstance(result, tuple)
            self.assertIs(result[0], agent._REPL_FALLTHROUGH)
            self.assertEqual(result[1], "analiza el target")

            result2 = agent._repl_use("use recon", "use recon", "use")
            self.assertIs(result2, agent._REPL_HANDLED)
        finally:
            agent.activate_skill = orig_activate
            agent.save_session = orig_save


if __name__ == "__main__":
    unittest.main()
