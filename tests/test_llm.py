"""Tests for LLMClient.complete()'s return dict -- specifically the
Stage 14 addition of a `reasoning` key, stubbing the backend so no
network or API key is needed."""

import json

import pytest

from make_harness.llm import LLMClient

ENV_KEYS = ("LLM_ENDPOINT", "LLM_MODEL", "LLM_API_KEY", "GROQ_API_KEY")


@pytest.fixture(autouse=True)
def stub_backend(monkeypatch):
    """Name a backend for get_llm_client(), which LLMClient() calls in
    __init__ and which raises when the environment configures none. Every
    test below replaces .chat afterwards, so the endpoint has to exist,
    not work. Without this the file passes only on a machine that happens
    to have real credentials exported."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_ENDPOINT", "http://stub/v1")


def _client_with_stub_response(raw):
    client = LLMClient(model="stub-model")
    client.backend.chat = lambda *a, **k: raw
    return client


def test_reasoning_present_is_passed_through():
    raw = {
        "choices": [{"message": {"role": "assistant", "content": "4", "reasoning": "because 2+2=4"}}],
        "usage": {"total_tokens": 10},
    }
    client = _client_with_stub_response(raw)
    result = client.complete([{"role": "user", "content": "hi"}])
    assert result == {
        "content": "4",
        "reasoning": "because 2+2=4",
        "tool_calls": [],
        "usage": {"total_tokens": 10},
        "raw": raw,
    }


def test_reasoning_absent_is_none():
    raw = {"choices": [{"message": {"role": "assistant", "content": "hi"}}], "usage": {}}
    client = _client_with_stub_response(raw)
    assert client.complete([{"role": "user", "content": "hi"}])["reasoning"] is None


def test_reasoning_absent_on_tool_call_response():
    raw = {
        "choices": [{"message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}],
        }}],
        "usage": {},
    }
    client = _client_with_stub_response(raw)
    result = client.complete([{"role": "user", "content": "hi"}])
    assert result["reasoning"] is None
    assert result["tool_calls"][0]["function"]["name"] == "read_file"


def test_salvaged_response_reasoning_degrades_to_none():
    # The salvage path (llm.py's own tool_use_failed recovery) builds a
    # synthetic raw dict by hand with no "reasoning" key at all -- confirm
    # msg.get("reasoning") degrades cleanly instead of a KeyError.
    client = LLMClient(model="stub-model")
    error_body = json.dumps({
        "error": {
            "code": "tool_use_failed",
            "failed_generation": '<function=read_file{"path": "x.py"}</function>',
        }
    })

    def raise_tool_use_failed(*a, **k):
        raise RuntimeError(f"LLM backend error 400: {error_body}")

    client.backend.chat = raise_tool_use_failed
    result = client.complete([{"role": "user", "content": "hi"}], retries=0)
    assert result["reasoning"] is None
    assert result["tool_calls"][0]["function"]["name"] == "read_file"


# --- retry ladder: tool_use_failed with nothing salvageable -----------------

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


def test_retries_escalate_temperature_then_succeed():
    client, seen = _client_failing_n_times(2)
    result = client.complete([{"role": "user", "content": "hi"}])
    assert seen == [0.2, 0.6, 1.0]
    assert result["content"] == "ok"


def test_gives_up_after_retries_are_exhausted():
    client, seen = _client_failing_n_times(5)
    with pytest.raises(RuntimeError):
        client.complete([{"role": "user", "content": "hi"}], retries=1)
    assert seen == [0.2, 0.6]


def test_retries_zero_means_a_single_attempt():
    client, seen = _client_failing_n_times(5)
    with pytest.raises(RuntimeError):
        client.complete([{"role": "user", "content": "hi"}], retries=0)
    assert seen == [0.2]


def test_other_backend_errors_are_not_retried():
    client, seen = _client_failing_n_times(5, error="LLM backend error 500: upstream down")
    with pytest.raises(RuntimeError, match="500"):
        client.complete([{"role": "user", "content": "hi"}])
    assert seen == [0.2]


def test_model_override_is_applied_to_the_backend():
    client = LLMClient(model="override-model")
    assert client.model == "override-model"
    assert client.backend.model == "override-model"


def test_salvaged_response_is_marked_and_carries_a_synthetic_id():
    client = LLMClient(model="stub-model")
    error_body = json.dumps({"error": {
        "code": "tool_use_failed",
        "failed_generation": '<function=probe{"a": 1}</function>',
    }})

    def chat(*a, **k):
        raise RuntimeError(f"LLM backend error 400: {error_body}")

    client.backend.chat = chat
    result = client.complete([{"role": "user", "content": "hi"}], retries=0)
    assert result["raw"]["salvaged"] is True
    assert result["content"] is None
    assert result["tool_calls"][0]["id"] == "salvaged_0"
    assert result["tool_calls"][0]["function"] == {"name": "probe", "arguments": '{"a": 1}'}


def test_retries_beyond_the_temperature_ladder_raise_the_backend_error():
    # The ladder has only three rungs, so retries > 2 buys no extra attempts.
    # Giving up on `retries` rather than on the last real rung let the loop
    # fall through with `raw` unbound — an UnboundLocalError masking the
    # backend error the caller needed to see.
    client, seen = _client_failing_n_times(99)
    with pytest.raises(RuntimeError, match="tool_use_failed"):
        client.complete([{"role": "user", "content": "hi"}], retries=5)
    assert seen == [0.2, 0.6, 1.0]
