"""Tests de normalización de mensajes para plantillas Jinja estrictas."""

import unittest
from types import SimpleNamespace

import agent


class TestNormalizeMessagesForApi(unittest.TestCase):
    def test_leading_system_messages_are_merged(self):
        msgs = [
            {"role": "system", "content": "prompt principal"},
            {"role": "system", "content": "fecha"},
            {"role": "system", "content": "scans"},
            {"role": "user", "content": "hola"},
        ]
        out = agent._normalize_messages_for_api(msgs)
        self.assertEqual(out[0]["role"], "system")
        self.assertEqual(out[0]["content"],
                         "prompt principal\n\nfecha\n\nscans")
        self.assertEqual(out[1:], [{"role": "user", "content": "hola"}])
        self.assertEqual(
            [m["role"] for m in out if m["role"] == "system"], ["system"]
        )

    def test_mid_history_system_is_demoted_to_user(self):
        msgs = [
            {"role": "system", "content": "prompt"},
            {"role": "user", "content": "pregunta"},
            {"role": "assistant", "content": "respuesta"},
            {"role": "system", "content": "[FILE_READ: x] contenido"},
            {"role": "user", "content": "sigue"},
        ]
        out = agent._normalize_messages_for_api(msgs)
        self.assertEqual(out[0]["content"], "prompt")
        self.assertTrue(all(m["role"] != "system" for m in out[1:]))
        self.assertEqual(out[3]["role"], "user")
        self.assertIn("[SISTEMA · contexto inyectado]", out[3]["content"])
        self.assertIn("[FILE_READ: x] contenido", out[3]["content"])
        self.assertEqual(out[4]["content"], "sigue")

    def test_does_not_mutate_input(self):
        msgs = [
            {"role": "system", "content": "a"},
            {"role": "system", "content": "b"},
            {"role": "user", "content": "c"},
        ]
        snapshot = [dict(m) for m in msgs]
        agent._normalize_messages_for_api(msgs)
        self.assertEqual(msgs, snapshot)

    def test_empty_and_no_system(self):
        self.assertEqual(agent._normalize_messages_for_api([]), [])
        msgs = [{"role": "user", "content": "x"}]
        self.assertEqual(agent._normalize_messages_for_api(msgs), msgs)


class TestCreateCompletionNormalizes(unittest.TestCase):
    def test_create_completion_sends_single_system(self):
        captured = {}

        class FakeCompletions:
            def create(self, **kwargs):
                captured.update(kwargs)
                return "ok"

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        )
        old = agent.client
        agent.client = fake_client
        try:
            out = agent._create_completion(
                model="m",
                messages=[
                    {"role": "system", "content": "uno"},
                    {"role": "system", "content": "dos"},
                    {"role": "user", "content": "hola"},
                    {"role": "system", "content": "tres"},
                ],
            )
        finally:
            agent.client = old

        self.assertEqual(out, "ok")
        sent = captured["messages"]
        self.assertEqual(sent[0], {"role": "system", "content": "uno\n\ndos"})
        self.assertEqual(sent[1], {"role": "user", "content": "hola"})
        self.assertEqual(sent[2]["role"], "user")
        self.assertIn("tres", sent[2]["content"])


if __name__ == "__main__":
    unittest.main()
