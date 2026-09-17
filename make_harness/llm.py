"""Adapter over the OpenAI SDK, pointed at any OpenAI-compatible endpoint.

The rest of the harness only ever calls LLMClient.complete(messages, tools)
and gets back a plain dict: {content, reasoning, tool_calls, usage, raw}.
Which backend answers — OpenAI, Groq, OpenRouter, or a local vLLM / Ollama /
LM Studio server — is decided by BASE_URL, API_KEY and MODEL alone
(see config.py).
"""

import json
import re

from openai import BadRequestError, OpenAI

from make_harness import config

# Local servers ignore the key, but the SDK refuses to build a client without one.
KEYLESS = "not-needed"
TIMEOUT = 300

# None sends no temperature at all, so the first attempt runs at the model's
# own default — some models reject any explicit value. The later rungs only
# exist to break a repeated malformed generation.
TEMPERATURES = [None, 0.6, 1.0]


def _salvage_tool_call(error_body):
    """Recover the intended tool call from a tool_use_failed error body.

    Groq answers 400 tool_use_failed when the model emits malformed tool
    syntax (llama's <function=name{...}</function>), and puts that text in
    failed_generation. Returns (name, arguments_json_string) or None.
    """
    failed = error_body.get("failed_generation") if isinstance(error_body, dict) else None
    if not isinstance(failed, str):
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


def _usage(usage):
    """Token counts from a response, or {} when the server reports none."""
    if usage is None:
        return {}
    completion = usage.completion_tokens_details
    prompt = usage.prompt_tokens_details
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "reasoning_tokens": getattr(completion, "reasoning_tokens", None),
        "cached_tokens": getattr(prompt, "cached_tokens", None),
    }


class LLMClient:
    def __init__(self, client=None, model=None):
        """Built from the environment by default; tests pass both a client
        and a model instead."""
        if client is None:
            base_url, api_key, env_model = config.backend()
            client = OpenAI(base_url=base_url, api_key=api_key or KEYLESS, timeout=TIMEOUT)
            model = model or env_model
        self.client = client
        self.model = model
        self.last_usage = {}  # of the latest request, for compact.needed()

    def complete(self, messages, tools=None, retries=2):
        # tool_use_failed: first try to salvage the intended call from the
        # error body; otherwise retry at a different temperature. The ladder
        # has three rungs, so `retries` above 2 buys no extra attempts.
        temperatures = TEMPERATURES[: retries + 1]
        for attempt, temperature in enumerate(temperatures):
            request = {"model": self.model, "messages": messages}
            if tools:
                request["tools"] = tools
            if temperature is not None:
                request["temperature"] = temperature
            try:
                response = self.client.chat.completions.create(**request)
                break
            except BadRequestError as e:
                if e.code != "tool_use_failed":
                    raise
                if salvaged := _salvage_tool_call(e.body):
                    name, arguments = salvaged
                    call = {
                        "id": f"salvaged_{attempt}",
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                    self.last_usage = {}
                    return {
                        "content": None,
                        "reasoning": None,
                        "tool_calls": [call],
                        "usage": {},
                        "raw": {"salvaged": True, "error": e.body},
                    }
                if attempt == len(temperatures) - 1:
                    raise
        message = response.choices[0].message.model_dump(exclude_none=True)
        self.last_usage = _usage(response.usage)
        return {
            "content": message.get("content"),
            # Groq names it reasoning; vLLM and LM Studio reasoning_content.
            "reasoning": message.get("reasoning") or message.get("reasoning_content"),
            "tool_calls": message.get("tool_calls") or [],
            "usage": self.last_usage,
            "raw": response.model_dump(exclude_none=True),
        }
