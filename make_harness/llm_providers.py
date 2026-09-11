"""Pluggable LLM backends: Groq, OpenAI, or local endpoints (vLLM, Ollama, etc).

This is the one file to swap out for a different backend. make_harness/llm.py
adapts whatever it returns to the rest of the harness. All backends implement
the same .chat() interface, so swapping is just changing which class is
instantiated in llm.py.
"""

import os
import requests


class OpenAICompatibleModel:
    """Generic OpenAI-compatible endpoint (local vLLM, Ollama, cloud, etc)."""

    def __init__(
        self,
        api_key=None,
        model=None,
        endpoint=None,
        timeout=300,
    ):
        """
        Args:
            api_key: API key (optional for local endpoints)
            model: Model name/ID
            endpoint: Base URL (e.g., http://localhost:8000/v1 or https://api.openai.com/v1)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.getenv("LLM_API_KEY") or None
        self.model = model or os.getenv("LLM_MODEL", "default")
        self.endpoint = endpoint or os.getenv("LLM_ENDPOINT", "http://localhost:8000/v1")
        self.timeout = timeout

    def chat(
        self,
        messages,
        tools=None,
        tool_choice="auto",
        temperature=0.2,
        max_tokens=None,
    ):
        headers = {
            "Content-Type": "application/json",
        }

        # Only add auth header if API key is provided
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        url = f"{self.endpoint}/chat/completions"
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            raise RuntimeError(f"LLM backend error {response.status_code}: {response.text[:500]}")

        return response.json()


class GroqChatModel(OpenAICompatibleModel):
    """Groq cloud API (backward compatible wrapper)."""

    def __init__(
        self,
        api_key=None,
        model="openai/gpt-oss-120b",
        endpoint="https://api.groq.com/openai/v1",
        timeout=300,
    ):
        super().__init__(api_key=api_key, model=model, endpoint=endpoint, timeout=timeout)
        # Groq reads its own key variable; everything else the base class set stands.
        self.api_key = api_key or os.getenv("GROQ_API_KEY")


def get_llm_client():
    """Factory: Choose backend based on environment variables.

    Priority:
    1. LLM_ENDPOINT (if set, use OpenAICompatibleModel)
    2. GROQ_API_KEY (if set, use GroqChatModel)
    3. If neither is set, raise an error
    """
    if os.getenv("LLM_ENDPOINT"):
        # Local endpoint (vLLM, Ollama, etc). The constructor reads
        # LLM_API_KEY / LLM_MODEL / LLM_ENDPOINT itself — don't restate them here.
        return OpenAICompatibleModel()
    elif os.getenv("GROQ_API_KEY"):
        # Groq cloud
        return GroqChatModel()
    else:
        # Trigger error as no LLM backend configured via environment variables
        raise RuntimeError("No LLM backend configured. Set LLM_ENDPOINT or GROQ_API_KEY.")
