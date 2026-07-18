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
- `make_harness/llm.py`: `LLMClient.complete()` normalizing the custom chat backend
  (`GroqChatModel`) to `{content, tool_calls, usage, raw}`.
- `make_harness/log.py`: `RunLog` — one JSONL file per session, one event per line.
- `main.py`: interactive REPL.
- Verified: live round-trip; request/response replayable from the log.

### [x] Stage 1 — Tool calling: read_file, write_file, run_command
- `make_harness/tools.py`: `@tool` decorator — OpenAI function schema from
  signature + docstring; `registry.schemas()` / `registry.execute()`.
- `make_harness/toolsets/fs.py`: `read_file` (line numbers, 2000-line cap),
  `write_file`.
- `make_harness/toolsets/shell.py`: `run_command` (60s timeout, 10k output cap).
- `make_harness/loop.py`: `run_turn()` — LLM → tool calls → results → repeat,
  `max_steps=15`.
- Verify: count files via command, summarize a file, create a file;
  full tool chain visible in the log.

### [x] Stage 2 — Permission gate
- `make_harness/policy.py`: `read_file` auto-allowed; `write_file` / `run_command`
  prompt on console (y/n/a = always for session).
- A denial ends the turn and returns control to the user (denial results are
  still appended so the tool_call/tool message pairing stays valid).
  Learned live: without this, the model retried denied calls with 10 variants.
- Verify: prompt appears, `y` executes, `n` ends the turn immediately.

### [x] Stage 3 — Web search + generic API calls
- `make_harness/toolsets/web.py`: `web_search` (Tavily/Brave key from env),
  `http_request(method, url, headers_json, body_json)`.
- Verified: http_request fetched the GitHub API live; web_search returns a
  clear no-key message until TAVILY_API_KEY or BRAVE_API_KEY is set.
- Learned live, hardening now in `make_harness/llm.py`:
  - backend errors surface the response body (a bare 400 is undebuggable);
  - system prompt tells the model to report tool errors, not invent results
    (it hallucinated an answer when search was unavailable);
  - Groq `tool_use_failed` 400s (llama emits malformed `<function=...>`
    syntax) are salvaged by parsing the intended call out of the error body,
    else retried at escalating temperature.

### [x] Stage 4 — Persistent memory
- `memory/MEMORY.md` index + one markdown file per fact.
- `make_harness/toolsets/memory.py`: `save_memory`, `read_memory`; index injected
  into the system prompt at REPL start (progressive disclosure).
- Verify: save a fact, restart the REPL, agent recalls it.

### [x] Stage 5 — Context compaction
- `make_harness/context.py`: token estimate (chars/4); over budget →
  1) stub tool results outside the recent window,
  2) summarize the older part via one LLM call,
  3) last resort: stub recent tool results too.
  System prompt is never touched; summaries never split a tool_call/result
  pair. Budget configurable via `HARNESS_TOKEN_BUDGET` (default 60k).
- Learned live: without step 3, a conversation shorter than the protected
  recent window could never be compacted — one huge file read would blow
  the budget with compaction logging "success" while doing nothing.
- Verified: offline unit tests (stub path, summarize path, pairing safety)
  + live session with an 800-token budget (1350 → 368 tokens, agent still
  answered the follow-up correctly).

### [x] Stage 6 — CLI packaging (pip-installable)
- Renamed the package `harness/` → `make_harness/` (avoids colliding with
  the generic `harness` name in a shared site-packages).
- Restored the adapter split that had drifted together during Stage 3
  hardening: `make_harness/llm_providers.py` is the swappable backend
  again (`GroqChatModel`), `make_harness/llm.py` is only the adapter +
  salvage logic. Was duplicated dead code before this stage.
- `make_harness/cli.py` (moved from root `main.py`): `argparse` with
  `--version`/`--help`; `main()` is the console-script target.
  `make_harness/__main__.py` enables `python -m make_harness`. Root
  `main.py` kept as a thin shim for `python main.py`.
- `pyproject.toml` (hatchling backend): build metadata + `make-harness`
  console-script entry point. Separate concern from `pixi.toml` — one is
  for building/distributing the package, the other for the dev environment.
- `pixi.toml`: `[pypi-dependencies]` now editable-installs the project
  itself, so `make-harness` is available inside `pixi run`; `start` task
  now runs `make-harness` instead of `python main.py`.
- Verified: `pixi run make-harness --version`/`--help`; live REPL via
  `pixi run start`, `pixi run python main.py`, and
  `pixi run python -m make_harness` (all three entry points equivalent);
  built `dist/make_harness-0.1.0.tar.gz` + `.whl` with `python -m build`;
  installed the sdist into a throwaway venv with no connection to this
  repo and ran `make-harness` live from an unrelated directory — full
  LLM round-trip succeeded, log file created relative to that directory.

### [ ] Stage 7 — Later (out of initial scope)
Markdown skill packages (`skills/<name>/SKILL.md` + `load_skill` tool),
subagents for context isolation, streaming, session resume from a log.

## Deliberately NOT built

Event bus, plugin system, middleware chain, state machine, workflow engine,
async. The JSONL logger and the policy gate are the seams where these can
bolt on later without a rewrite.
