"""Tests for llm_providers — the backend factory and the OpenAI-compatible
HTTP client, with the requests module stubbed out (no network)."""

from types import SimpleNamespace

import pytest

from make_harness import llm_providers
from make_harness.llm_providers import GroqChatModel, OpenAICompatibleModel, get_llm_client

ENV_KEYS = ("LLM_ENDPOINT", "LLM_MODEL", "LLM_API_KEY", "GROQ_API_KEY")


@pytest.fixture
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


@pytest.fixture
def fake_post(monkeypatch):
    """Replace requests.post inside llm_providers with a recorder.
    Returns (calls, response) — set response["value"] to change what the
    next post() returns."""
    calls = []
    response = {"value": FakeResponse({"choices": [{"message": {"content": "ok"}}]})}

    def post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return response["value"]

    monkeypatch.setattr(llm_providers, "requests", SimpleNamespace(post=post))
    return calls, response


# --- factory ---------------------------------------------------------------

def test_factory_prefers_llm_endpoint_over_groq(clean_env, monkeypatch):
    monkeypatch.setenv("LLM_ENDPOINT", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")  # present but outranked
    client = get_llm_client()
    assert type(client) is OpenAICompatibleModel
    assert client.endpoint == "http://localhost:11434/v1"
    assert client.model == "qwen"


def test_factory_uses_groq_when_only_the_groq_key_is_set(clean_env, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")
    client = get_llm_client()
    assert isinstance(client, GroqChatModel)
    assert client.api_key == "gsk_x"
    assert client.endpoint == "https://api.groq.com/openai/v1"
    assert client.model == "openai/gpt-oss-120b"


def test_factory_raises_when_nothing_is_configured(clean_env):
    with pytest.raises(RuntimeError, match="LLM_ENDPOINT or GROQ_API_KEY"):
        get_llm_client()


def test_explicit_constructor_args_beat_the_environment(clean_env, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "from-env")
    m = OpenAICompatibleModel(model="explicit", endpoint="http://x/v1", api_key="k")
    assert (m.model, m.endpoint, m.api_key) == ("explicit", "http://x/v1", "k")


def test_groq_explicit_key_beats_the_environment(clean_env, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "env-key")
    assert GroqChatModel(api_key="arg-key").api_key == "arg-key"


# --- chat() request shape --------------------------------------------------

def test_chat_posts_to_chat_completions(fake_post, clean_env):
    calls, _ = fake_post
    m = OpenAICompatibleModel(endpoint="http://host:8000/v1", model="m", api_key="dummy", timeout=7)
    out = m.chat([{"role": "user", "content": "hi"}])
    call = calls[0]
    assert call["url"] == "http://host:8000/v1/chat/completions"
    assert call["timeout"] == 7
    assert call["json"]["model"] == "m"
    assert call["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert call["json"]["temperature"] == 0.2
    assert call["json"]["stream"] is False
    assert out == {"choices": [{"message": {"content": "ok"}}]}


def test_chat_omits_the_auth_header_for_keyless_local_endpoints(fake_post, clean_env):
    calls, _ = fake_post
    OpenAICompatibleModel(api_key=None, endpoint="http://x/v1").chat([])
    assert "Authorization" not in calls[0]["headers"]
    assert calls[0]["headers"]["Content-Type"] == "application/json"


def test_chat_sends_a_bearer_token_when_a_key_is_given(fake_post, clean_env):
    calls, _ = fake_post
    OpenAICompatibleModel(api_key="sk-abc", endpoint="http://x/v1").chat([])
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-abc"


def test_chat_includes_tools_and_tool_choice_only_when_tools_are_given(fake_post, clean_env):
    calls, _ = fake_post
    m = OpenAICompatibleModel(endpoint="http://x/v1")
    m.chat([])
    assert "tools" not in calls[0]["json"]
    assert "tool_choice" not in calls[0]["json"]
    tools = [{"type": "function", "function": {"name": "t"}}]
    m.chat([], tools=tools, tool_choice="required")
    assert calls[1]["json"]["tools"] == tools
    assert calls[1]["json"]["tool_choice"] == "required"


def test_chat_includes_max_tokens_only_when_set(fake_post, clean_env):
    calls, _ = fake_post
    m = OpenAICompatibleModel(endpoint="http://x/v1")
    m.chat([])
    m.chat([], max_tokens=42, temperature=0.9)
    assert "max_tokens" not in calls[0]["json"]
    assert calls[1]["json"]["max_tokens"] == 42
    assert calls[1]["json"]["temperature"] == 0.9


def test_chat_raises_runtime_error_with_a_capped_body_on_http_error(fake_post, clean_env):
    _, response = fake_post
    response["value"] = FakeResponse(status_code=400, text="x" * 600)
    with pytest.raises(RuntimeError) as exc:
        OpenAICompatibleModel(endpoint="http://x/v1").chat([])
    prefix = "LLM backend error 400: "
    assert str(exc.value).startswith(prefix)
    assert len(str(exc.value)) == len(prefix) + 500


def test_groq_chat_uses_the_groq_endpoint_and_key(fake_post, clean_env):
    calls, _ = fake_post
    GroqChatModel(api_key="gsk").chat([])
    assert calls[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer gsk"
    assert calls[0]["json"]["model"] == "openai/gpt-oss-120b"
