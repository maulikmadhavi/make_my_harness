"""Tests for llm.LLMClient — the request it sends through the OpenAI SDK,
the dict complete() hands back, the retry ladder, and tool_use_failed
salvage.

Everything is offline but goes through the real SDK: the client is built
over an httpx2 MockTransport (httpx2 is the SDK's own HTTP library), so
request serialization, response parsing and error mapping are all the
SDK's actual behavior.
"""

import json

import httpx2
import pytest
from openai import OpenAI

from make_harness import config
from make_harness.llm import KEYLESS, LLMClient, _salvage_tool_call

HI = [{"role": "user", "content": "hi"}]
_TOOL_CALL = {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}


def _completion(message, usage=None):
    body = {
        "id": "x", "object": "chat.completion", "created": 0, "model": "stub-model",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", **message}}],
    }
    if usage is not None:
        body["usage"] = usage
    return body


class Server:
    """A scripted OpenAI-compatible endpoint. Each reply is (status, body);
    the last one repeats. Every request body is recorded."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request):
        self.requests.append({"url": str(request.url), "headers": request.headers, "json": json.loads(request.content)})
        status, body = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return httpx2.Response(status, json=body)

    def client(self, api_key="sk-test"):
        http = httpx2.Client(transport=httpx2.MockTransport(self))
        sdk = OpenAI(base_url="http://stub/v1", api_key=api_key, http_client=http, max_retries=0)
        return LLMClient(client=sdk, model="stub-model")


def _ok(message=None, usage=None):
    return 200, _completion(message or {"content": "ok"}, usage)


class TestConstruction:
    @pytest.fixture
    def backend_env(self, monkeypatch):
        for key in ("BASE_URL", "API_KEY", "MODEL", *config.RENAMED):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("BASE_URL", "http://localhost:11434/v1")
        monkeypatch.setenv("MODEL", "qwen")

    def test_builds_an_sdk_client_from_the_environment(self, backend_env, monkeypatch):
        monkeypatch.setenv("API_KEY", "sk-env")
        llm = LLMClient()
        assert llm.model == "qwen"
        assert str(llm.client.base_url) == "http://localhost:11434/v1/"
        assert llm.client.api_key == "sk-env"

    def test_keyless_local_servers_get_a_placeholder_key(self, backend_env):
        # The SDK raises "Missing credentials" for an empty key.
        assert LLMClient().client.api_key == KEYLESS

    def test_explicit_model_beats_the_environment(self, backend_env):
        assert LLMClient(model="override").model == "override"

    def test_unconfigured_backend_raises(self, monkeypatch):
        for key in ("BASE_URL", "MODEL"):
            monkeypatch.delenv(key, raising=False)
        with pytest.raises(RuntimeError, match="Set BASE_URL and MODEL"):
            LLMClient()


class TestRequest:
    """What goes on the wire."""

    def test_posts_model_and_messages_to_chat_completions(self):
        server = Server(_ok())
        server.client().complete(HI)
        request = server.requests[0]
        assert request["url"] == "http://stub/v1/chat/completions"
        assert request["headers"]["authorization"] == "Bearer sk-test"
        assert request["json"] == {"model": "stub-model", "messages": HI}

    def test_first_attempt_sends_no_temperature(self):
        # Some models reject any explicit temperature; the first attempt must
        # run at the model's own default.
        server = Server(_ok())
        server.client().complete(HI)
        assert "temperature" not in server.requests[0]["json"]

    def test_tools_are_sent_only_when_given(self):
        server = Server(_ok())
        tools = [{"type": "function", "function": {"name": "t", "parameters": {"type": "object", "properties": {}}}}]
        llm = server.client()
        llm.complete(HI)
        llm.complete(HI, tools=tools)
        assert "tools" not in server.requests[0]["json"]
        assert server.requests[1]["json"]["tools"] == tools


class TestCompleteResult:
    """The dict LLMClient.complete() hands back."""

    def test_returns_content_reasoning_tool_calls_usage_and_raw(self):
        usage = {
            "prompt_tokens": 50, "completion_tokens": 7, "total_tokens": 57,
            "completion_tokens_details": {"reasoning_tokens": 4},
            "prompt_tokens_details": {"cached_tokens": 32},
        }
        result = Server(_ok({"content": "4", "reasoning": "because 2+2=4"}, usage)).client().complete(HI)
        assert result["content"] == "4"
        assert result["reasoning"] == "because 2+2=4"
        assert result["tool_calls"] == []
        assert result["usage"] == {
            "prompt_tokens": 50, "completion_tokens": 7, "reasoning_tokens": 4, "cached_tokens": 32,
        }
        assert result["raw"]["choices"][0]["message"]["content"] == "4"

    @pytest.mark.parametrize(
        "message,expected",
        [
            ({"content": "4", "reasoning": "groq style"}, "groq style"),
            ({"content": "4", "reasoning_content": "vllm style"}, "vllm style"),
            ({"content": "hi"}, None),
            ({"content": None, "tool_calls": [_TOOL_CALL]}, None),
        ],
        ids=["reasoning", "reasoning_content", "absent", "absent-on-tool-call"],
    )
    def test_reasoning_key(self, message, expected):
        assert Server(_ok(message)).client().complete(HI)["reasoning"] == expected

    def test_tool_calls_come_back_as_plain_dicts(self):
        result = Server(_ok({"content": None, "tool_calls": [_TOOL_CALL]})).client().complete(HI)
        assert result["tool_calls"] == [_TOOL_CALL]
        assert result["content"] is None

    def test_usage_is_empty_when_the_server_reports_none(self):
        assert Server(_ok()).client().complete(HI)["usage"] == {}

    def test_last_usage_tracks_the_latest_request(self):
        usage = {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}
        server = Server(_ok(usage=usage), _ok())
        llm = server.client()
        assert llm.last_usage == {}
        llm.complete(HI)
        assert llm.last_usage["prompt_tokens"] == 5
        llm.complete(HI)
        assert llm.last_usage == {}  # a response without usage doesn't keep the stale count

    def test_missing_detail_blocks_leave_those_counts_none(self):
        usage = {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}
        assert Server(_ok(usage=usage)).client().complete(HI)["usage"] == {
            "prompt_tokens": 5, "completion_tokens": 2, "reasoning_tokens": None, "cached_tokens": None,
        }


def _tool_use_failed(failed_generation="no function tag in here"):
    return 400, {"error": {"code": "tool_use_failed", "message": "Failed to call a function.",
                           "failed_generation": failed_generation}}


class TestRetryLadder:
    """tool_use_failed with nothing salvageable retries at another
    temperature; other backend errors do not retry at all."""

    @staticmethod
    def _temperatures(server):
        return [r["json"].get("temperature") for r in server.requests]

    def test_changes_temperature_then_succeeds(self):
        server = Server(_tool_use_failed(), _tool_use_failed(), _ok())
        assert server.client().complete(HI)["content"] == "ok"
        assert self._temperatures(server) == [None, 0.6, 1.0]

    @pytest.mark.parametrize(
        "retries,expected",
        [(0, [None]), (1, [None, 0.6]), (2, [None, 0.6, 1.0]), (5, [None, 0.6, 1.0])],
        ids=["single-attempt", "one-retry", "full-ladder", "beyond-the-ladder"],
    )
    def test_gives_up_on_the_last_rung(self, retries, expected):
        # Giving up on `retries` rather than on the last real rung let the loop
        # fall through with `response` unbound, masking the backend error.
        server = Server(_tool_use_failed())
        with pytest.raises(Exception, match="tool_use_failed"):
            server.client().complete(HI, retries=retries)
        assert self._temperatures(server) == expected

    @pytest.mark.parametrize(
        "reply",
        [(400, {"error": {"code": "context_length_exceeded", "message": "too long"}}),
         (500, {"error": {"message": "upstream down"}})],
        ids=["other-400", "server-error"],
    )
    def test_other_backend_errors_are_not_retried(self, reply):
        server = Server(reply)
        with pytest.raises(Exception):
            server.client().complete(HI)
        assert len(server.requests) == 1


class TestSalvage:
    """_salvage_tool_call recovers the intended call from a tool_use_failed
    body. These recreate the malformed <function=...> generations observed
    live during Stage 3 (llama-3.3 on Groq)."""

    @pytest.mark.parametrize(
        "body,expected",
        [
            ({"failed_generation": '<function=read_file{"path": "x.py"}</function>'}, ("read_file", '{"path": "x.py"}')),
            ({"failed_generation": '<function=web_search={"query": "python 3.13"}'}, ("web_search", '{"query": "python 3.13"}')),
            ({"failed_generation": "<function=read_file{path: x.py}</function>"}, None),
            ({"failed_generation": "I will now read the file for you."}, None),
            ({"code": "tool_use_failed"}, None),
            ("Internal Server Error", None),
            (None, None),
        ],
        ids=["valid", "equals-variant", "bad-argument-json", "no-function-tag",
             "no-failed-generation", "body-not-a-dict", "no-body"],
    )
    def test_salvage(self, body, expected):
        assert _salvage_tool_call(body) == expected

    def test_salvaged_call_is_returned_without_a_retry(self):
        server = Server(_tool_use_failed('<function=probe{"a": 1}</function>'))
        result = server.client().complete(HI)
        assert len(server.requests) == 1
        assert result["raw"]["salvaged"] is True
        assert result["content"] is None
        assert result["reasoning"] is None
        assert result["tool_calls"] == [
            {"id": "salvaged_0", "type": "function", "function": {"name": "probe", "arguments": '{"a": 1}'}},
        ]
