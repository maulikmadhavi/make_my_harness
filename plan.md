# Execution Plan — Bottom-Up Agent Harness

Goal: a minimal, fully understood agent harness built stage by stage.
Each stage is small, working, and verified live before the next begins.
One commit per stage.

## Design principles

1. The harness is a loop around one function: `complete(messages, tools) -> {content, tool_calls}`.
2. Log everything as JSONL from day one — full session replay from `logs/*.jsonl`.
3. No module exists before the stage that needs it. Nothing speculative.
4. Messages stay plain OpenAI-format dicts. Native tool calling only — no text parsing.
5. Sync code only.

## Stages

### [x] Stage 0 — Bare chat + full logging
- `harness/llm.py`: `LLMClient.complete()` normalizing the custom chat backend
  (`GroqChatModel`) to `{content, tool_calls, usage, raw}`.
- `harness/log.py`: `RunLog` — one JSONL file per session, one event per line.
- `main.py`: interactive REPL.
- Verified: live round-trip; request/response replayable from the log.

### [x] Stage 1 — Tool calling: read_file, write_file, run_command
- `harness/tools.py`: `@tool` decorator — OpenAI function schema from
  signature + docstring; `registry.schemas()` / `registry.execute()`.
- `harness/toolsets/fs.py`: `read_file` (line numbers, 2000-line cap),
  `write_file`.
- `harness/toolsets/shell.py`: `run_command` (60s timeout, 10k output cap).
- `harness/loop.py`: `run_turn()` — LLM → tool calls → results → repeat,
  `max_steps=15`.
- Verify: count files via command, summarize a file, create a file;
  full tool chain visible in the log.

### [ ] Stage 2 — Permission gate
- `harness/policy.py`: `read_file` auto-allowed; `write_file` / `run_command`
  prompt on console (y/n/a = always for session). Denial goes back to the
  model as the tool result.
- Verify: prompt appears, `n` is handled gracefully, `a` stops re-prompting.

### [ ] Stage 3 — Web search + generic API calls
- `harness/toolsets/web.py`: `web_search` (Tavily/Brave key from env),
  `http_request(method, url, headers, body)`.
- Verify: answer a current-events question; call a public JSON API.

### [ ] Stage 4 — Persistent memory
- `memory/MEMORY.md` index + one markdown file per fact.
- `harness/toolsets/memory.py`: `save_memory`, `read_memory`; index injected
  into the system prompt at REPL start (progressive disclosure).
- Verify: save a fact, restart the REPL, agent recalls it.

### [ ] Stage 5 — Context compaction
- `harness/context.py`: token estimate (chars/4); over budget →
  1) stub old tool results, 2) summarize the older half via one LLM call.
  Keep system prompt + recent turns intact. Log a `compaction` event.
- Verify: long session triggers compaction; agent still answers from summary.

### [ ] Stage 6 — Later (out of initial scope)
Markdown skill packages (`skills/<name>/SKILL.md` + `load_skill` tool),
subagents for context isolation, streaming, session resume from a log.

## Deliberately NOT built

Event bus, plugin system, middleware chain, state machine, workflow engine,
async. The JSONL logger and the policy gate are the seams where these can
bolt on later without a rewrite.
