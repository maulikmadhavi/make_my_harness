"""Adapter over the custom chat completion script (llm_providers.py).

The rest of the harness only ever calls LLMClient.complete(messages, tools)
and gets back a plain dict: {content, tool_calls, usage, raw}.
Swapping backends (Groq -> Ollama, vLLM, OpenAI, ...) means changing only this file.
"""

import json
import os
import re

import requests


class GroqChatModel:
    def __init__(
        self,
        api_key=None,
        model="llama-3.3-70b-versatile",
        endpoint="https://api.groq.com/openai/v1/chat/completions",
        timeout=300,
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout

    def chat(
        self,
        messages,
        tools=None,
        tool_choice="auto",
        temperature=0.2,
        max_tokens=None,
        stream=False,
    ):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        response = requests.post(
            self.endpoint,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            raise RuntimeError(
                f"LLM backend error {response.status_code}: {response.text[:500]}"
            )

        return response.json()


def _salvage_tool_call(error_text):
    """Recover the intended tool call from a Groq tool_use_failed error body.

    Returns (name, arguments_json_string) or None if unparseable.
    """
    try:
        body = json.loads(error_text[error_text.index("{"):])
        failed = body["error"]["failed_generation"]
    except (ValueError, KeyError):
        return None
    m = re.search(r"<function=(\w+)=?\s*(\{.*\})", failed, re.DOTALL)
    if not m:
        return None
    name, arguments = m.group(1), m.group(2)
    try:
        json.loads(arguments)
    except json.JSONDecodeError:
        return None
    return name, arguments


class LLMClient:
    def __init__(self, model=None):
        kwargs = {"model": model} if model else {}
        self.backend = GroqChatModel(**kwargs)
        self.model = self.backend.model

    def complete(self, messages, tools=None, retries=2):
        # Groq sometimes 400s with "tool_use_failed" when the model emits
        # malformed tool syntax (e.g. <function=name{...}</function>). The
        # error body contains the intended call, so first try to salvage it;
        # otherwise retry at a higher temperature to break the determinism.
        for attempt, temperature in enumerate([0.2, 0.6, 1.0][: retries + 1]):
            try:
                raw = self.backend.chat(messages, tools=tools, temperature=temperature)
                break
            except RuntimeError as e:
                if "tool_use_failed" not in str(e):
                    raise
                salvaged = _salvage_tool_call(str(e))
                if salvaged:
                    name, arguments = salvaged
                    raw = {
                        "choices": [{"message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": f"salvaged_{attempt}",
                                "type": "function",
                                "function": {"name": name, "arguments": arguments},
                            }],
                        }}],
                        "usage": {},
                        "salvaged": True,
                    }
                    break
                if attempt == retries:
                    raise
        msg = raw["choices"][0]["message"]
        return {
            "content": msg.get("content"),
            "tool_calls": msg.get("tool_calls") or [],
            "usage": raw.get("usage", {}),
            "raw": raw,
        }
