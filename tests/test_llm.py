"""Tests for LLMClient.complete()'s return dict -- specifically the
Stage 14 addition of a `reasoning` key, stubbing the backend so no
network or API key is needed."""

import json

from make_harness.llm import LLMClient


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
