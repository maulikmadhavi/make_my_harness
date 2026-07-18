# make_harness

A minimal agent harness built from scratch, bottom-up — to understand how
coding agents (Claude Code, Codex CLI, ...) actually work, without LangChain
or any agent framework.

The core idea: an agent is a loop around one function —
`complete(messages, tools) -> {content, tool_calls}`. Everything else
(tools, permissions, logging, memory, context management) is built around
that loop in small, verifiable stages. See [plan.md](plan.md) for the
stage-by-stage execution plan; each stage is one git commit, so
`git log --oneline` reads as a tutorial.

## What it does

- **Custom LLM backend**: `harness/llm.py` wraps an OpenAI-compatible chat
  completion class (currently Groq). Swapping backends touches only this file.
- **Tools from plain functions**: decorate a Python function with `@tool`
  and its JSON schema is generated from the signature and docstring.
- **Permission gate**: side-effecting tools ask before running; a denial
  ends the turn and returns control to you.
- **Full session logs**: every LLM request/response, tool call/result and
  permission verdict as JSONL in `logs/` — replayable for debugging.
- **Persistent memory**: facts survive across sessions via `memory/`.
- **Context compaction**: long conversations are squeezed back under a
  token budget automatically.

## User guide

### Setup and start

```powershell
pixi install
$env:GROQ_API_KEY = "..."        # required
$env:TAVILY_API_KEY = "..."      # optional, enables web_search (or BRAVE_API_KEY)
pixi run start
```

You get a REPL:

```
harness REPL — llama-3.3-70b-versatile — logging to logs\20260718_...jsonl
tools: read_file, write_file, run_command, web_search, http_request, save_memory, read_memory
you >
```

- Type a request; the agent answers, calling tools as needed (shown as
  `→ tool(args)` / `← result size`).
- When a side-effecting tool is requested you'll see
  `allow? y = once / n = deny / a = always` — `n` cancels and hands control
  back to you.
- `exit`, `quit`, or Ctrl+C ends the session.
- Every session writes one JSONL file to `logs/`; each line is one event
  (`llm_request`, `llm_response`, `tool_call`, `tool_result`, `permission`,
  `compaction`, `error`, `done`).

### Verifying each stage manually

Each stage of [plan.md](plan.md) can be re-verified with a short REPL
session. The expected behavior below is what the live tests produced.

#### Stage 0 — chat + logging

Type: `Reply with exactly: STAGE0-OK`

- Expect the reply `STAGE0-OK`.
- Check the newest file in `logs/`: it must contain one `llm_request` line
  (full message list) and one `llm_response` line (raw API response):

```powershell
Get-Content (Get-ChildItem logs | Sort-Object Name | Select-Object -Last 1).FullName
```

#### Stage 1 — file and shell tools

Type, one per line:

1. `How many .md files are in the current directory? Use a command to count.`
   → a `run_command` call, then the correct count.
2. `Read pixi.toml and tell me which python version it pins.`
   → a `read_file` call, answer `3.12`.
3. `Create hello.txt containing exactly: Hello from the harness`
   → a `write_file` call (approve with `y`); verify with
   `Get-Content hello.txt`, then delete the file.

The log must show the full `tool_call` → `tool_result` chain.

#### Stage 2 — permission gate

1. Ask for any file write → the `allow?` prompt appears; answer `y` → the
   write happens.
2. Ask it to run a command → answer `n` → the turn ends immediately with
   `[tool call denied — tell me how to proceed]`. It must NOT retry the
   command with different variants.
3. Ask for another write → answer `a` → this and later writes in the same
   session run without prompting.

The log gets a `permission` event with the verdict for every gated call.

#### Stage 3 — web tools

1. `Use http_request to GET https://api.github.com/repos/python/cpython and tell me the star count.`
   → approve with `y`; expect a plausible star count read from the API.
2. `Search the web for the latest stable Python version.`
   - With `TAVILY_API_KEY`/`BRAVE_API_KEY` set: results with titles + URLs.
   - Without a key: the agent must honestly say search is unavailable —
     not invent an answer.

Note: Groq occasionally rejects tool calls with a `tool_use_failed` 400
(llama emits malformed syntax). The adapter salvages or retries these
automatically; you should not see the error surface in the REPL.

#### Stage 4 — persistent memory

1. Session A: `Remember for future sessions that my favorite editor is VS Code.`
   → a `save_memory` call; `memory/MEMORY.md` gains an index line and
   `memory/favorite-editor...md` appears.
2. Exit, start a fresh session: `Which editor do I prefer? Check your memory.`
   → a `read_memory` call, answer `VS Code`.

#### Stage 5 — context compaction

Force a tiny budget so compaction triggers immediately:

```powershell
$env:HARNESS_TOKEN_BUDGET = "800"
pixi run start
```

1. `Read plan.md and list only the stage titles.` → big tool result enters
   the context.
2. `Based on what you read, which stage adds the permission gate?`
   → before this turn runs, compaction fires; the agent still answers
   `Stage 2` correctly.
3. Check the log for the `compaction` event — `tokens_after` must be
   meaningfully smaller than `tokens_before`:

```powershell
Get-Content (Get-ChildItem logs | Sort-Object Name | Select-Object -Last 1).FullName |
  ForEach-Object { $_ | ConvertFrom-Json } | Where-Object kind -eq "compaction"
```

Unset the budget afterwards: `Remove-Item Env:HARNESS_TOKEN_BUDGET`
(default is 60000).

### Configuration reference

| Env var | Purpose | Default |
|---|---|---|
| `GROQ_API_KEY` | LLM backend auth | required |
| `TAVILY_API_KEY` / `BRAVE_API_KEY` | enables `web_search` | unset → clear error |
| `HARNESS_TOKEN_BUDGET` | context compaction threshold (tokens) | `60000` |

## Layout

```
harness/
  llm.py        LLM adapter (backend + normalization + error salvage)
  log.py        JSONL run logger
  tools.py      @tool decorator + registry
  loop.py       the agent loop
  policy.py     permission gate
  context.py    token budget + compaction
  toolsets/     fs, shell, web, memory tool implementations
main.py         REPL entry point
plan.md         staged build plan + lessons learned
logs/           one JSONL file per session (gitignored)
memory/         persistent agent memory (gitignored)
```
