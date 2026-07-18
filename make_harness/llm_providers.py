"""Your custom chat completion script.

This is the one file to swap out for a different backend (OpenAI, Ollama,
vLLM, ...); make_harness/llm.py adapts whatever it returns to the rest of
the harness.
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

        if response.status_code >= 400:
            raise RuntimeError(
                f"LLM backend error {response.status_code}: {response.text[:500]}"
            )

        return response.json()


if __name__ == "__main__":
    llm = GroqChatModel()

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain transformers in one paragraph."},
    ]

    response = llm.chat(messages)

    print(response["choices"][0]["message"]["content"])
