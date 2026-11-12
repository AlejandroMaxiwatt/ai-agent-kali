"""Tests del backend Strata (motor de inferencia OpenAI-compatible)."""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

import agent


class TestStrataConfig(unittest.TestCase):
    def test_backend_registered(self):
        cfg = agent.BACKENDS["strata"]
        self.assertEqual(cfg["base_url"], agent.STRATA_BASE_URL)
        self.assertEqual(cfg["fallback"], agent.STRATA_MODEL_FALLBACK)
        self.assertFalse(cfg["needs_key"])
        self.assertEqual(cfg["key_env"], "STRATA_API_KEY")

    def test_default_backend_is_strata(self):
        # Sin AGENT_BACKEND en el entorno, el default es Strata.
        if "AGENT_BACKEND" not in os.environ:
            self.assertEqual(agent._ACTIVE_BACKEND, "strata")
        self.assertIn(agent._ACTIVE_BACKEND, agent.BACKENDS)
        self.assertEqual(agent.backend_base_url(),
                         agent.active_backend_cfg()["base_url"])


class TestStrataModels(unittest.TestCase):
    def setUp(self):
        self._backend = agent._ACTIVE_BACKEND
        self._last = agent._LAST_ACTIVE_MODEL
        self._selected = agent._SELECTED_MODEL
        agent._ACTIVE_BACKEND = "strata"

    def tearDown(self):
        agent._ACTIVE_BACKEND = self._backend
        agent._LAST_ACTIVE_MODEL = self._last
        agent._SELECTED_MODEL = self._selected

    def _fake_response(self, payload):
        resp = mock.Mock()
        resp.raise_for_status.return_value = None
        resp.status_code = 200
        resp.json.return_value = payload
        return resp

    def test_lists_models_from_v1_models(self):
        payload = {
            "object": "list",
            "data": [{
                "id": "iq3_s",
                "object": "model",
                "owned_by": "strata",
                "meta": {"label": "Qwen3.8-Flash-Next IQ3_S"},
            }],
        }
        with mock.patch.object(
            agent.requests, "get", return_value=self._fake_response(payload)
        ):
            self.assertEqual(agent.get_lmstudio_models(), ["iq3_s"])

    def test_falls_back_when_server_down(self):
        with mock.patch.object(
            agent.requests, "get", side_effect=ConnectionError("down")
        ):
            self.assertEqual(
                agent.get_lmstudio_models(), [agent.STRATA_MODEL_FALLBACK]
            )

    def test_detailed_marks_models_as_served(self):
        with mock.patch.object(agent, "get_lmstudio_models",
                               return_value=["iq3_s"]):
            detailed = agent.get_lmstudio_models_detailed()
        self.assertEqual(detailed[0]["id"], "iq3_s")
        self.assertEqual(detailed[0]["state"], "served")

    def test_context_uses_strata_fallback(self):
        agent._MODEL_CONTEXT_CACHE.clear()
        self.assertEqual(
            agent.resolve_model_context_limit("iq3_s", "strata"),
            agent.STRATA_CONTEXT_TOKENS,
        )


class TestSwitchBackend(unittest.TestCase):
    def setUp(self):
        self._backend = agent._ACTIVE_BACKEND
        self._selected = agent._SELECTED_MODEL
        self._last = agent._LAST_ACTIVE_MODEL
        self._client = agent.client
        self._get_models = agent.get_lmstudio_models
        agent.get_lmstudio_models = lambda: ["iq3_s"]

    def tearDown(self):
        agent._ACTIVE_BACKEND = self._backend
        agent._SELECTED_MODEL = self._selected
        agent._LAST_ACTIVE_MODEL = self._last
        agent.client = self._client
        agent.get_lmstudio_models = self._get_models

    def test_switch_to_strata_and_alias(self):
        ok, msg = agent.switch_backend("lmstudio")
        self.assertTrue(ok, msg)
        ok, msg = agent.switch_backend("motor")
        self.assertTrue(ok, msg)
        self.assertEqual(agent._ACTIVE_BACKEND, "strata")
        self.assertEqual(agent.backend_base_url(), agent.STRATA_BASE_URL)
        self.assertIn("Strata", msg)

    def test_unknown_backend(self):
        ok, msg = agent.switch_backend("inexistente")
        self.assertFalse(ok)
        self.assertIn("Opciones", msg)


class TestReasoningMessages(unittest.TestCase):
    def test_content_none_does_not_break(self):
        message = SimpleNamespace(
            content=None, reasoning_content="We need to respond..."
        )
        self.assertEqual(agent._message_final_text(message), "")

    def test_content_is_returned(self):
        message = SimpleNamespace(content="ok", reasoning_content="thinking")
        self.assertEqual(agent._message_final_text(message), "ok")

    def test_missing_content_attribute(self):
        self.assertEqual(agent._message_final_text(SimpleNamespace()), "")


if __name__ == "__main__":
    unittest.main()
