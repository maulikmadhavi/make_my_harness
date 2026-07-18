# make_harness

A minimal agent harness built from scratch, bottom-up — to understand how
coding agents (Claude Code, Codex CLI, ...) actually work, without LangChain
or any agent framework.

The core idea: an agent is a loop around one function —
`complete(messages, tools) -> {content, tool_calls}`. Everything else
(tools, permissions, logging, memory, context management) is built around
that loop in small, verifiable stages. See [plan.md](plan.md) for the
stage-by-stage execution plan; each stage is one git commit.

## What it does

- **Custom LLM backend**: wraps `llm_providers.py` (OpenAI-compatible chat
  completion with native tool calling). Swapping backends touches only
  `harness/llm.py`.
- **Tools from plain functions**: decorate a Python function with `@tool`
  and its JSON schema is generated from the signature and docstring.
- **Full session logs**: every LLM request/response, tool call/result and
  permission verdict as JSONL in `logs/` — replayable for debugging.

## Quickstart

```
pixi install
$env:GROQ_API_KEY = "..."   # or your backend's key
pixi run start
```

Type into the REPL; `exit` or Ctrl+C to quit.
