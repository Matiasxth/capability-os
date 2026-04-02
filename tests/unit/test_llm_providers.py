"""Tests for LLM provider adapters: Anthropic, Gemini, DeepSeek."""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch, MagicMock

from system.core.interpretation.llm_client import (
    AnthropicAdapter,
    DeepSeekAdapter,
    GeminiAdapter,
    LLMClientError,
    OpenAIAPIAdapter,
    OllamaAdapter,
    _build_adapter_from_env,
    _build_adapter_from_settings,
    _extract_stream_content,
    _http_post_json,
)


# ---------------------------------------------------------------------------
# Response parsing tests
# ---------------------------------------------------------------------------

@patch("system.core.interpretation.llm_client._get_pool", return_value=None)
class TestHttpPostJsonParsing(unittest.TestCase):
    """Test _http_post_json parses each provider's response format."""

    def _mock_urlopen(self, response_body: dict):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_body).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("system.core.interpretation.llm_client.urlopen")
    def test_anthropic_parsing(self, mock_urlopen, _mock_pool):
        mock_urlopen.return_value = self._mock_urlopen({
            "content": [{"type": "text", "text": "Hello from Claude"}],
            "model": "claude-sonnet-4-20250514",
            "stop_reason": "end_turn",
        })
        result = _http_post_json("https://api.anthropic.com/v1/messages", {}, {}, 30.0, "anthropic")
        self.assertEqual(result, "Hello from Claude")

    @patch("system.core.interpretation.llm_client.urlopen")
    def test_anthropic_missing_content(self, mock_urlopen, _mock_pool):
        mock_urlopen.return_value = self._mock_urlopen({"content": []})
        with self.assertRaises(LLMClientError):
            _http_post_json("https://api.anthropic.com/v1/messages", {}, {}, 30.0, "anthropic")

    @patch("system.core.interpretation.llm_client.urlopen")
    def test_gemini_parsing(self, mock_urlopen, _mock_pool):
        mock_urlopen.return_value = self._mock_urlopen({
            "candidates": [{
                "content": {"parts": [{"text": "Hello from Gemini"}]},
                "finishReason": "STOP",
            }]
        })
        result = _http_post_json("https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent", {}, {}, 30.0, "gemini")
        self.assertEqual(result, "Hello from Gemini")

    @patch("system.core.interpretation.llm_client.urlopen")
    def test_gemini_missing_candidates(self, mock_urlopen, _mock_pool):
        mock_urlopen.return_value = self._mock_urlopen({"candidates": []})
        with self.assertRaises(LLMClientError):
            _http_post_json("https://url", {}, {}, 30.0, "gemini")

    @patch("system.core.interpretation.llm_client.urlopen")
    def test_deepseek_uses_openai_format(self, mock_urlopen, _mock_pool):
        mock_urlopen.return_value = self._mock_urlopen({
            "choices": [{"message": {"content": "Hello from DeepSeek"}}]
        })
        result = _http_post_json("https://api.deepseek.com/v1/chat/completions", {}, {}, 30.0, "openai")
        self.assertEqual(result, "Hello from DeepSeek")


# ---------------------------------------------------------------------------
# Stream content extraction tests
# ---------------------------------------------------------------------------

class TestExtractStreamContent(unittest.TestCase):

    def test_openai_format(self):
        data = {"choices": [{"delta": {"content": "hello"}}]}
        self.assertEqual(_extract_stream_content(data, "openai"), "hello")

    def test_openai_empty_delta(self):
        data = {"choices": [{"delta": {}}]}
        self.assertIsNone(_extract_stream_content(data, "openai"))

    def test_anthropic_text_delta(self):
        data = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "world"}}
        self.assertEqual(_extract_stream_content(data, "anthropic"), "world")

    def test_anthropic_non_delta_event(self):
        data = {"type": "message_start", "message": {}}
        self.assertIsNone(_extract_stream_content(data, "anthropic"))

    def test_gemini_format(self):
        data = {"candidates": [{"content": {"parts": [{"text": "gemini chunk"}]}}]}
        self.assertEqual(_extract_stream_content(data, "gemini"), "gemini chunk")

    def test_gemini_empty_candidates(self):
        data = {"candidates": []}
        self.assertIsNone(_extract_stream_content(data, "gemini"))

    def test_unknown_format(self):
        self.assertIsNone(_extract_stream_content({}, "unknown"))


# ---------------------------------------------------------------------------
# Adapter instantiation tests
# ---------------------------------------------------------------------------

class TestAdapterDataclasses(unittest.TestCase):

    def test_anthropic_adapter_fields(self):
        a = AnthropicAdapter(api_key="sk-ant-test", model="claude-sonnet-4-20250514")
        self.assertEqual(a.api_key, "sk-ant-test")
        self.assertEqual(a.base_url, "https://api.anthropic.com")

    def test_gemini_adapter_fields(self):
        a = GeminiAdapter(api_key="AIza-test", model="gemini-2.0-flash")
        self.assertEqual(a.base_url, "https://generativelanguage.googleapis.com")

    def test_deepseek_adapter_fields(self):
        a = DeepSeekAdapter(api_key="sk-deep-test", model="deepseek-chat")
        self.assertEqual(a.base_url, "https://api.deepseek.com/v1")


# ---------------------------------------------------------------------------
# Builder tests
# ---------------------------------------------------------------------------

class TestBuildAdapterFromEnv(unittest.TestCase):

    @patch.dict(os.environ, {"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-ant-test"})
    def test_anthropic_from_env(self):
        adapter = _build_adapter_from_env()
        self.assertIsInstance(adapter, AnthropicAdapter)
        self.assertEqual(adapter.api_key, "sk-ant-test")

    @patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "AIza-test"})
    def test_gemini_from_env(self):
        adapter = _build_adapter_from_env()
        self.assertIsInstance(adapter, GeminiAdapter)

    @patch.dict(os.environ, {"LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "sk-deep-test"})
    def test_deepseek_from_env(self):
        adapter = _build_adapter_from_env()
        self.assertIsInstance(adapter, DeepSeekAdapter)

    @patch.dict(os.environ, {"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": ""})
    def test_anthropic_missing_key_raises(self):
        with self.assertRaises(LLMClientError):
            _build_adapter_from_env()

    @patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": ""})
    def test_gemini_missing_key_raises(self):
        with self.assertRaises(LLMClientError):
            _build_adapter_from_env()

    @patch.dict(os.environ, {"LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": ""})
    def test_deepseek_missing_key_raises(self):
        with self.assertRaises(LLMClientError):
            _build_adapter_from_env()


class TestBuildAdapterFromSettings(unittest.TestCase):

    def test_anthropic_from_settings(self):
        settings = {"provider": "anthropic", "api_key": "sk-ant-123", "model": "claude-sonnet-4-20250514"}
        adapter = _build_adapter_from_settings(settings, fallback_to_env=False)
        self.assertIsInstance(adapter, AnthropicAdapter)

    def test_gemini_from_settings(self):
        settings = {"provider": "gemini", "api_key": "AIza-test", "model": "gemini-2.0-flash"}
        adapter = _build_adapter_from_settings(settings, fallback_to_env=False)
        self.assertIsInstance(adapter, GeminiAdapter)

    def test_deepseek_from_settings(self):
        settings = {"provider": "deepseek", "api_key": "sk-deep-test", "model": "deepseek-chat"}
        adapter = _build_adapter_from_settings(settings, fallback_to_env=False)
        self.assertIsInstance(adapter, DeepSeekAdapter)

    def test_anthropic_missing_key_in_settings(self):
        settings = {"provider": "anthropic", "model": "claude-sonnet-4-20250514"}
        with self.assertRaises(LLMClientError):
            _build_adapter_from_settings(settings, fallback_to_env=False)


# ---------------------------------------------------------------------------
# Settings validation
# ---------------------------------------------------------------------------

class TestSettingsValidation(unittest.TestCase):

    def test_all_five_providers_accepted(self):
        from system.core.settings.settings_service import VALID_LLM_PROVIDERS
        for p in ("openai", "ollama", "anthropic", "gemini", "deepseek"):
            self.assertIn(p, VALID_LLM_PROVIDERS)


if __name__ == "__main__":
    unittest.main()
