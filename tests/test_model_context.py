"""Tests de la ventana de contexto dinámica por modelo/backend."""

import unittest

import agent


class TestExtractContextLength(unittest.TestCase):
    def test_ollama_model_info(self):
        self.assertEqual(
            agent._extract_context_length({"kimi-k2.context_length": 262144}),
            262144,
        )
        self.assertEqual(
            agent._extract_context_length(
                {"general.context_length": 131072, "x.context_length": 999}
            ),
            131072,
        )
        self.assertEqual(
            agent._extract_context_length({"gptoss.context_length": 131072}),
            131072,
        )

    def test_missing_or_invalid(self):
        self.assertIsNone(agent._extract_context_length({}))
        self.assertIsNone(agent._extract_context_length(None))
        self.assertIsNone(
            agent._extract_context_length({"x.context_length": 0})
        )


class TestModelContextResolution(unittest.TestCase):
    def setUp(self):
        self._backend = agent._ACTIVE_BACKEND
        self._last = agent._LAST_ACTIVE_MODEL
        self._cache = dict(agent._MODEL_CONTEXT_CACHE)
        self._state = dict(agent._CTX_STATE)
        self._orig_fetch = agent.fetch_ollama_model_context
        agent._MODEL_CONTEXT_CACHE.clear()
        agent._CTX_STATE.update(backend=None, model=None, value=None)

    def tearDown(self):
        agent._ACTIVE_BACKEND = self._backend
        agent._LAST_ACTIVE_MODEL = self._last
        agent._MODEL_CONTEXT_CACHE.clear()
        agent._MODEL_CONTEXT_CACHE.update(self._cache)
        agent._CTX_STATE.update(self._state)
        agent.fetch_ollama_model_context = self._orig_fetch

    def test_ollama_resolves_and_caches(self):
        calls = []
        agent._ACTIVE_BACKEND = "ollama"
        agent._LAST_ACTIVE_MODEL = "kimi-k2.7-code"
        agent.fetch_ollama_model_context = lambda m: calls.append(m) or 262144

        self.assertEqual(agent.get_max_context_tokens(), 262144)
        self.assertEqual(agent.get_max_context_tokens(), 262144)
        self.assertEqual(calls, ["kimi-k2.7-code"])  # segunda vez: caché

    def test_ollama_falls_back(self):
        agent._ACTIVE_BACKEND = "ollama"
        agent._LAST_ACTIVE_MODEL = "modelo-sin-metadatos"
        agent.fetch_ollama_model_context = lambda m: None

        self.assertEqual(
            agent.get_max_context_tokens(),
            agent.BACKENDS["ollama"]["context_fallback"],
        )

    def test_model_change_triggers_new_resolution(self):
        values = {"a": 131072, "b": 262144}
        agent._ACTIVE_BACKEND = "ollama"
        agent._LAST_ACTIVE_MODEL = "a"
        agent.fetch_ollama_model_context = lambda m: values[m]

        self.assertEqual(agent.get_max_context_tokens(), 131072)
        agent._LAST_ACTIVE_MODEL = "b"
        self.assertEqual(agent.get_max_context_tokens(), 262144)


class TestDynamicCompactionThreshold(unittest.TestCase):
    def setUp(self):
        self._orig_get_max = agent.get_max_context_tokens
        self._orig_compaction = agent.PROMPT_COMPACTION
        agent.PROMPT_COMPACTION = True

    def tearDown(self):
        agent.get_max_context_tokens = self._orig_get_max
        agent.PROMPT_COMPACTION = self._orig_compaction

    def _messages(self):
        long_text = "A" * 6000
        return [
            {"role": "system", "content": "system prompt corto"},
            {"role": "user", "content": long_text},
            {"role": "assistant", "content": long_text},
            {"role": "user", "content": long_text},
            {"role": "assistant", "content": long_text},
            {"role": "user", "content": long_text},
            {"role": "assistant", "content": long_text},
            {"role": "user", "content": long_text},
            {"role": "assistant", "content": long_text},
        ]

    def test_small_window_compacts(self):
        agent.get_max_context_tokens = lambda: 1000
        out = agent._compact_messages_for_call(self._messages())
        # El primer user largo cae fuera de la ventana de recencia y se trunca.
        self.assertLess(len(out[1]["content"]), 6000)

    def test_large_window_keeps_recent_history_intact(self):
        agent.get_max_context_tokens = lambda: 10_000_000
        out = agent._compact_messages_for_call(self._messages())
        self.assertEqual(out[1]["content"], "A" * 6000)


if __name__ == "__main__":
    unittest.main()
