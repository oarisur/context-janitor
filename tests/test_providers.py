import json
import os
import urllib.error
import unittest
from unittest.mock import patch

from context_janitor.models import Tool
from context_janitor.providers import MAX_PROVIDER_ERROR_BODY_CHARS, ProviderError, select_with_provider


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class _FakeTextResponse(_FakeResponse):
    def __init__(self, text):
        self.text = text

    def read(self):
        return self.text.encode("utf-8")

    def close(self):
        pass


class ProviderTest(unittest.TestCase):
    def test_openai_provider_selects_returned_names(self):
        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 0.25)
            self.assertEqual(request.headers["Authorization"], "Bearer test-key")
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(body["model"], "gpt-test")
            return _FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"selected": ["github_search_issues"]}',
                            }
                        }
                    ]
                }
            )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            selected = select_with_provider("openai", "Search GitHub issues", _tools(), 1, "gpt-test", 0.25)

        self.assertEqual([tool.name for tool in selected], ["github_search_issues"])

    def test_anthropic_provider_selects_returned_names(self):
        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 0.5)
            self.assertEqual(request.headers["X-api-key"], "test-key")
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(body["model"], "claude-test")
            return _FakeResponse({"content": [{"text": '{"selected": ["calendar_create_event"]}'}]})

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            selected = select_with_provider("anthropic", "Schedule a meeting", _tools(), 1, "claude-test", 0.5)

        self.assertEqual([tool.name for tool in selected], ["calendar_create_event"])

    def test_gemini_provider_selects_returned_names(self):
        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 0.75)
            self.assertIn("key=test-key", request.full_url)
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(body["generationConfig"]["temperature"], 0)
            return _FakeResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": '{"selected": ["web_search"]}',
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            selected = select_with_provider("gemini", "Search the web", _tools(), 1, "gemini-test", 0.75)

        self.assertEqual([tool.name for tool in selected], ["web_search"])

    def test_provider_rejects_non_positive_limit(self):
        with self.assertRaisesRegex(ValueError, "limit"):
            select_with_provider("heuristic", "Search", _tools(), 0)

    def test_provider_wraps_malformed_response(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen",
            return_value=_FakeResponse({"unexpected": []}),
        ):
            with self.assertRaisesRegex(ProviderError, "malformed"):
                select_with_provider("openai", "Search GitHub issues", _tools(), 1, "gpt-test")

    def test_provider_wraps_invalid_json_response(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen",
            return_value=_FakeTextResponse("not json"),
        ):
            with self.assertRaisesRegex(ProviderError, "invalid JSON"):
                select_with_provider("openai", "Search GitHub issues", _tools(), 1, "gpt-test")

    def test_provider_truncates_large_http_error_body(self):
        error = urllib.error.HTTPError(
            url="https://example.test",
            code=500,
            msg="Server Error",
            hdrs=None,
            fp=_FakeTextResponse("x" * (MAX_PROVIDER_ERROR_BODY_CHARS + 100)),
        )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(ProviderError) as raised:
                select_with_provider("openai", "Search GitHub issues", _tools(), 1, "gpt-test")

        self.assertIn("[truncated]", str(raised.exception))
        self.assertLess(len(str(raised.exception)), MAX_PROVIDER_ERROR_BODY_CHARS + 200)


def _tools():
    return [
        Tool("github_search_issues", "Search GitHub issues."),
        Tool("calendar_create_event", "Create calendar events."),
        Tool("web_search", "Search the public web."),
    ]


if __name__ == "__main__":
    unittest.main()
