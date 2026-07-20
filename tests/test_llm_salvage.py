"""Tests for llm._salvage_tool_call — recovering the intended tool call
from a Groq tool_use_failed 400 error body.

These recreate the malformed <function=...> generations observed live
during Stage 3 (llama-3.3 emitting broken tool syntax).
"""

import json

from make_harness.llm import _salvage_tool_call


def _groq_error(failed_generation):
    """Build an error string shaped like GroqChatModel's RuntimeError text."""
    body = {
        "error": {
            "code": "tool_use_failed",
            "message": "Failed to call a function.",
            "failed_generation": failed_generation,
        }
    }
    return "LLM backend error 400: " + json.dumps(body)


def test_salvages_valid_call():
    err = _groq_error('<function=read_file{"path": "x.py"}</function>')
    assert _salvage_tool_call(err) == ("read_file", '{"path": "x.py"}')


def test_salvages_equals_sign_variant():
    err = _groq_error('<function=web_search={"query": "python 3.13"}')
    assert _salvage_tool_call(err) == ("web_search", '{"query": "python 3.13"}')


def test_rejects_invalid_argument_json():
    err = _groq_error("<function=read_file{path: x.py}</function>")
    assert _salvage_tool_call(err) is None


def test_no_function_tag_in_generation():
    err = _groq_error("I will now read the file for you.")
    assert _salvage_tool_call(err) is None


def test_error_body_is_not_json():
    assert _salvage_tool_call("LLM backend error 500: Internal Server Error") is None


def test_error_body_missing_failed_generation():
    assert _salvage_tool_call('LLM backend error 400: {"error": {"code": "other"}}') is None
