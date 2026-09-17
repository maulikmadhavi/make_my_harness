"""Tests for toolsets.web — web_search's provider selection and result
formatting, and http_request's request shape, with the requests module
stubbed out (no network)."""

from types import SimpleNamespace

import pytest
from helpers import FakeResponse

from make_harness.tools import registry
from make_harness.toolsets import web


@pytest.fixture
def fake_requests(monkeypatch):
    """Swap web.requests for a recorder. .post/.get/.request each log
    (kind, args, kwargs) and return whatever responses[kind] holds. Both
    search keys start unset."""
    calls = []
    responses = {"post": FakeResponse(), "get": FakeResponse(), "request": FakeResponse()}

    def make(kind):
        def call(*args, **kwargs):
            calls.append((kind, args, kwargs))
            return responses[kind]
        return call

    monkeypatch.setattr(
        web, "requests",
        SimpleNamespace(post=make("post"), get=make("get"), request=make("request")),
    )
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    return calls, responses


class TestWebSearch:
    def test_without_a_key_is_a_clear_error_and_makes_no_request(self, fake_requests):
        calls, _ = fake_requests
        out = web.web_search("anything")
        assert out.startswith("Error: no search API key configured")
        assert "TAVILY_API_KEY" in out
        assert "BRAVE_API_KEY" in out
        assert calls == []

    def test_uses_tavily_when_its_key_is_set(self, fake_requests, monkeypatch):
        calls, responses = fake_requests
        monkeypatch.setenv("TAVILY_API_KEY", "tv-key")
        responses["post"] = FakeResponse({"results": [
            {"title": "Python 3.13", "url": "https://python.org", "content": "c" * 400},
        ]})
        out = web.web_search("latest python")
        kind, args, kwargs = calls[0]
        assert kind == "post"
        assert args[0] == "https://api.tavily.com/search"
        assert kwargs["json"] == {"api_key": "tv-key", "query": "latest python", "max_results": 5}
        assert out.startswith("- Python 3.13\n  https://python.org\n  ")
        assert len(out.splitlines()[2].strip()) == 300  # snippet capped

    def test_uses_brave_when_only_its_key_is_set(self, fake_requests, monkeypatch):
        calls, responses = fake_requests
        monkeypatch.setenv("BRAVE_API_KEY", "br-key")
        responses["get"] = FakeResponse({"web": {"results": [
            {"title": "T", "url": "https://u", "description": "d"},
        ]}})
        out = web.web_search("q")
        kind, args, kwargs = calls[0]
        assert kind == "get"
        assert args[0].startswith("https://api.search.brave.com/")
        assert kwargs["params"] == {"q": "q", "count": 5}
        assert kwargs["headers"]["X-Subscription-Token"] == "br-key"
        assert out == "- T\n  https://u\n  d"

    def test_prefers_tavily_when_both_keys_are_set(self, fake_requests, monkeypatch):
        calls, _ = fake_requests
        monkeypatch.setenv("TAVILY_API_KEY", "tv")
        monkeypatch.setenv("BRAVE_API_KEY", "br")
        web.web_search("q")
        assert [kind for kind, _, _ in calls] == ["post"]

    def test_reports_empty_results(self, fake_requests, monkeypatch):
        _, responses = fake_requests
        monkeypatch.setenv("TAVILY_API_KEY", "tv")
        responses["post"] = FakeResponse({"results": []})
        assert web.web_search("q") == "No results."

    def test_http_error_becomes_a_tool_error_string(self, fake_requests, monkeypatch):
        _, responses = fake_requests
        monkeypatch.setenv("TAVILY_API_KEY", "tv")
        responses["post"] = FakeResponse(status_code=500)
        assert registry.execute("web_search", {"query": "q"}).startswith("Error in web_search:")


class TestHttpRequest:
    def test_shape_and_output(self, fake_requests):
        calls, responses = fake_requests
        responses["request"] = FakeResponse(status_code=201, text='{"ok": true}')
        out = web.http_request(
            "post", "https://api.example/x", headers_json='{"A": "1"}', body_json='{"k": "v"}'
        )
        kind, args, kwargs = calls[0]
        assert kind == "request"
        assert args == ("POST", "https://api.example/x")  # method upper-cased
        assert kwargs == {"headers": {"A": "1"}, "json": {"k": "v"}, "timeout": 30}
        assert out == 'status: 201\n{"ok": true}'

    def test_defaults_to_no_headers_and_no_body(self, fake_requests):
        calls, _ = fake_requests
        web.http_request("get", "https://api.example/x")
        _, _, kwargs = calls[0]
        assert kwargs["headers"] == {}
        assert kwargs["json"] is None

    def test_truncates_long_bodies_head_and_tail(self, fake_requests):
        _, responses = fake_requests
        responses["request"] = FakeResponse(text="H" + "m" * 30_000 + "T")
        out = web.http_request("get", "https://x")
        assert "chars truncated" in out
        assert "T\n[full output (30002 chars) saved to " in out  # tail kept, whole body spilled
        assert len(out) < 11_000

    def test_bad_headers_json_is_a_tool_error_string(self, fake_requests):
        out = registry.execute(
            "http_request", {"method": "get", "url": "https://x", "headers_json": "{not json"}
        )
        assert out.startswith("Error in http_request: JSONDecodeError")
