"""Adapter over the custom chat completion script (llm_providers.py).

The rest of the harness only ever calls LLMClient.complete(messages, tools)
and gets back a plain dict: {content, tool_calls, usage, raw}.
Swapping backends (Groq -> Ollama, vLLM, OpenAI, ...) means changing only this file.
"""

import os
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

        response.raise_for_status()

        return response.json()


class LLMClient:
    def __init__(self, model=None):
        kwargs = {"model": model} if model else {}
        self.backend = GroqChatModel(**kwargs)
        self.model = self.backend.model

    def complete(self, messages, tools=None):
        raw = self.backend.chat(messages, tools=tools)
        msg = raw["choices"][0]["message"]
        return {
            "content": msg.get("content"),
            "tool_calls": msg.get("tool_calls") or [],
            "usage": raw.get("usage", {}),
            "raw": raw,
        }
