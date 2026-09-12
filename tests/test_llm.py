"""Tests for the LLM layer: the backend factory and HTTP client
(llm_providers) and the LLMClient adapter over them (llm) — its return
dict, the retry ladder, and tool_use_failed salvage.

Everything is offline: requests is stubbed for the provider tests, and
the adapter tests replace client.backend.chat outright.
"""

import json
from types import SimpleNamespace

import pytest
from helpers import FakeResponse

from make_harness import llm_providers
from make_harness.llm import LLMClient, _salvage_tool_call
from make_harness.llm_providers import GroqChatModel, OpenAICompatibleModel, get_llm_client

ENV_KEYS = ("LLM_ENDPOINT", "LLM_MODEL", "LLM_API_KEY", "GROQ_API_KEY")
HI = [{"role": "user", "content": "hi"}]


@pytest.fixture
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def stub_backend(monkeypatch):
    """A configured backend so LLMClient() can be built without the
    developer's own keys — every test here replaces .chat anyway."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_ENDPOINT", "http://stub/v1")


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


class TestFactory:
    """get_llm_client() picks a backend from the environment."""

    def test_prefers_llm_endpoint_over_groq(self, clean_env, monkeypatch):
        monkeypatch.setenv("LLM_ENDPOINT", "http://localhost:11434/v1")
        monkeypatch.setenv("LLM_MODEL", "qwen")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_x")  # present but outranked
        client = get_llm_client()
        assert type(client) is OpenAICompatibleModel
        assert client.endpoint == "http://localhost:11434/v1"
        assert client.model == "qwen"

    def test_uses_groq_when_only_the_groq_key_is_set(self, clean_env, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_x")
        client = get_llm_client()
        assert isinstance(client, GroqChatModel)
        assert client.api_key == "gsk_x"
        assert client.endpoint == "https://api.groq.com/openai/v1"
        assert client.model == "openai/gpt-oss-120b"

    def test_raises_when_nothing_is_configured(self, clean_env):
        with pytest.raises(RuntimeError, match="LLM_ENDPOINT or GROQ_API_KEY"):
            get_llm_client()

    def test_explicit_constructor_args_beat_the_environment(self, clean_env, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "from-env")
        monkeypatch.setenv("GROQ_API_KEY", "env-key")
        m = OpenAICompatibleModel(model="explicit", endpoint="http://x/v1", api_key="k")
        assert (m.model, m.endpoint, m.api_key) == ("explicit", "http://x/v1", "k")
        assert GroqChatModel(api_key="arg-key").api_key == "arg-key"


class TestChatRequest:
    """The request OpenAICompatibleModel.chat() puts on the wire."""

    def test_posts_to_chat_completions(self, fake_post, clean_env):
        calls, _ = fake_post
        m = OpenAICompatibleModel(endpoint="http://host:8000/v1", model="m", api_key="dummy", timeout=7)
        out = m.chat([{"role": "user", "content": "hi"}])
        call = calls[0]
        assert call["url"] == "http://host:8000/v1/chat/completions"
        assert call["timeout"] == 7
        assert call["json"]["model"] == "m"
        assert call["json"]["messages"] == [{"role": "user", "content": "hi"}]
        assert call["json"]["temperature"] == 0.2
        # No "stream" key: the client only ever reads a whole JSON body, so it must
        # not advertise streaming. OpenAI-compatible servers default to non-streaming.
        assert "stream" not in call["json"]
        assert out == {"choices": [{"message": {"content": "ok"}}]}

    @pytest.mark.parametrize(
        "api_key,expected", [(None, None), ("sk-abc", "Bearer sk-abc")],
        ids=["keyless-local", "with-key"],
    )
    def test_authorization_header_tracks_the_key(self, fake_post, clean_env, api_key, expected):
        calls, _ = fake_post
        OpenAICompatibleModel(api_key=api_key, endpoint="http://x/v1").chat([])
        assert calls[0]["headers"].get("Authorization") == expected
        assert calls[0]["headers"]["Content-Type"] == "application/json"

    def test_tools_and_tool_choice_only_when_tools_are_given(self, fake_post, clean_env):
        calls, _ = fake_post
        m = OpenAICompatibleModel(endpoint="http://x/v1")
        m.chat([])
        assert "tools" not in calls[0]["json"]
        assert "tool_choice" not in calls[0]["json"]
        tools = [{"type": "function", "function": {"name": "t"}}]
        m.chat([], tools=tools, tool_choice="required")
        assert calls[1]["json"]["tools"] == tools
        assert calls[1]["json"]["tool_choice"] == "required"

    def test_max_tokens_only_when_set(self, fake_post, clean_env):
        calls, _ = fake_post
        m = OpenAICompatibleModel(endpoint="http://x/v1")
        m.chat([])
        m.chat([], max_tokens=42, temperature=0.9)
        assert "max_tokens" not in calls[0]["json"]
        assert calls[1]["json"]["max_tokens"] == 42
        assert calls[1]["json"]["temperature"] == 0.9

    def test_http_error_raises_with_a_capped_body(self, fake_post, clean_env):
        _, response = fake_post
        response["value"] = FakeResponse(status_code=400, text="x" * 600)
        with pytest.raises(RuntimeError) as exc:
            OpenAICompatibleModel(endpoint="http://x/v1").chat([])
        prefix = "LLM backend error 400: "
        assert str(exc.value).startswith(prefix)
        assert len(str(exc.value)) == len(prefix) + 500

    def test_groq_uses_its_own_endpoint_and_key(self, fake_post, clean_env):
        calls, _ = fake_post
        GroqChatModel(api_key="gsk").chat([])
        assert calls[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"
        assert calls[0]["headers"]["Authorization"] == "Bearer gsk"
        assert calls[0]["json"]["model"] == "openai/gpt-oss-120b"


def _client(stub_response):
    """An LLMClient whose backend returns `stub_response` for any call."""
    client = LLMClient(model="stub-model")
    client.backend.chat = lambda *a, **k: stub_response
    return client


_TOOL_CALL = {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}


class TestCompleteResult:
    """The dict LLMClient.complete() hands back."""

    def test_returns_content_reasoning_tool_calls_usage_and_raw(self, stub_backend):
        raw = {
            "choices": [{"message": {"role": "assistant", "content": "4", "reasoning": "because 2+2=4"}}],
            "usage": {"total_tokens": 10},
        }
        assert _client(raw).complete(HI) == {
            "content": "4",
            "reasoning": "because 2+2=4",
            "tool_calls": [],
            "usage": {"total_tokens": 10},
            "raw": raw,
        }

    @pytest.mark.parametrize(
        "message,expected",
        [
            ({"role": "assistant", "content": "4", "reasoning": "because 2+2=4"}, "because 2+2=4"),
            ({"role": "assistant", "content": "hi"}, None),
            ({"role": "assistant", "content": None, "tool_calls": [_TOOL_CALL]}, None),
        ],
        ids=["present", "absent", "absent-on-tool-call"],
    )
    def test_reasoning_key(self, stub_backend, message, expected):
        raw = {"choices": [{"message": message}], "usage": {}}
        assert _client(raw).complete(HI)["reasoning"] == expected

    def test_tool_calls_are_passed_through(self, stub_backend):
        raw = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [_TOOL_CALL]}}], "usage": {}}
        assert _client(raw).complete(HI)["tool_calls"][0]["function"]["name"] == "read_file"

    def test_model_override_reaches_the_backend(self, stub_backend):
        client = LLMClient(model="override-model")
        assert client.model == "override-model"
        assert client.backend.model == "override-model"


_UNSALVAGEABLE = (
    'LLM backend error 400: {"error": {"code": "tool_use_failed", '
    '"failed_generation": "no function tag in here"}}'
)
_GOOD = {"choices": [{"message": {"role": "assistant", "content": "ok"}}], "usage": {}}


def _client_failing_n_times(n, error=_UNSALVAGEABLE):
    """A client whose backend raises `error` for the first n calls, then
    succeeds; `seen` records the temperature of every attempt."""
    client = LLMClient(model="stub-model")
    seen = []

    def chat(messages, tools=None, temperature=None):
        seen.append(temperature)
        if len(seen) <= n:
            raise RuntimeError(error)
        return _GOOD

    client.backend.chat = chat
    return client, seen


class TestRetryLadder:
    """tool_use_failed with nothing salvageable retries at rising
    temperature; other backend errors do not retry at all."""

    def test_escalates_temperature_then_succeeds(self, stub_backend):
        client, seen = _client_failing_n_times(2)
        assert client.complete(HI)["content"] == "ok"
        assert seen == [0.2, 0.6, 1.0]

    @pytest.mark.parametrize(
        "retries,expected_temps",
        [(0, [0.2]), (1, [0.2, 0.6]), (2, [0.2, 0.6, 1.0]), (5, [0.2, 0.6, 1.0])],
        ids=["single-attempt", "one-retry", "full-ladder", "beyond-the-ladder"],
    )
    def test_gives_up_on_the_last_rung(self, stub_backend, retries, expected_temps):
        # The ladder has only three rungs, so retries > 2 buys no extra attempts.
        # Giving up on `retries` rather than on the last real rung let the loop
        # fall through with `raw` unbound — an UnboundLocalError masking the
        # backend error the caller needed to see.
        client, seen = _client_failing_n_times(99)
        with pytest.raises(RuntimeError, match="tool_use_failed"):
            client.complete(HI, retries=retries)
        assert seen == expected_temps

    def test_other_backend_errors_are_not_retried(self, stub_backend):
        client, seen = _client_failing_n_times(5, error="LLM backend error 500: upstream down")
        with pytest.raises(RuntimeError, match="500"):
            client.complete(HI)
        assert seen == [0.2]


def _groq_error(failed_generation, code="tool_use_failed"):
    """An error string shaped like GroqChatModel's RuntimeError text."""
    body = {"error": {"code": code, "message": "Failed to call a function.",
                      "failed_generation": failed_generation}}
    return "LLM backend error 400: " + json.dumps(body)


class TestSalvage:
    """_salvage_tool_call recovers the intended call from a Groq
    tool_use_failed body. These recreate the malformed <function=...>
    generations observed live during Stage 3 (llama-3.3)."""

    @pytest.mark.parametrize(
        "error,expected",
        [
            (_groq_error('<function=read_file{"path": "x.py"}</function>'), ("read_file", '{"path": "x.py"}')),
            (_groq_error('<function=web_search={"query": "python 3.13"}'), ("web_search", '{"query": "python 3.13"}')),
            (_groq_error("<function=read_file{path: x.py}</function>"), None),
            (_groq_error("I will now read the file for you."), None),
            ("LLM backend error 500: Internal Server Error", None),
            ('LLM backend error 400: {"error": {"code": "other"}}', None),
        ],
        ids=["valid", "equals-variant", "bad-argument-json", "no-function-tag",
             "body-not-json", "no-failed-generation"],
    )
    def test_salvage(self, error, expected):
        assert _salvage_tool_call(error) == expected

    def test_salvaged_response_is_marked_and_carries_a_synthetic_id(self, stub_backend):
        # The salvage path builds a synthetic raw dict by hand with no
        # "reasoning" key at all — confirm msg.get("reasoning") degrades
        # cleanly to None instead of raising KeyError.
        client = LLMClient(model="stub-model")
        error = _groq_error('<function=probe{"a": 1}</function>')

        def chat(*a, **k):
            raise RuntimeError(error)

        client.backend.chat = chat
        result = client.complete(HI, retries=0)
        assert result["raw"]["salvaged"] is True
        assert result["content"] is None
        assert result["reasoning"] is None
        assert result["tool_calls"][0]["id"] == "salvaged_0"
        assert result["tool_calls"][0]["function"] == {"name": "probe", "arguments": '{"a": 1}'}
