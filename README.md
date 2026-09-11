# make_harness

A minimal agent harness built from scratch, bottom-up — to understand how
coding agents (Claude Code, Codex CLI, ...) actually work, without LangChain
or any agent framework.

The core idea: an agent is a loop around one function —
`complete(messages, tools) -> {content, tool_calls}`. Everything else
(tools, permissions, logging, memory, context management, the UI) is built
around that loop in small, verifiable stages. See [plan.md](plan.md) for the
stage-by-stage execution plan; each stage is one git commit, so
`git log --oneline` reads as a tutorial.

## What it does

- **A real CLI**: installs as the `make-harness` command (`pip install` or
  `pixi run`), plus `python -m make_harness` as a fallback.
- **Pluggable LLM backend**: any OpenAI-compatible `/chat/completions`
  endpoint — a local vLLM / Ollama / LM Studio server, OpenAI itself, or
  Groq — selected purely by environment variables (or a `.env` file).
  `make_harness/llm_providers.py` is the one file that talks HTTP;
  `make_harness/llm.py` adapts its output for the rest of the harness.
- **Tools from plain functions**: decorate a Python function with `@tool`
  and its JSON schema is generated from the signature and docstring.
- **Permission gate**: side-effecting tools ask before running
  (`yes` / `no` / `always` / `deny`); a denial ends the turn and returns
  control to you.
- **Full session logs**: every LLM request/response, tool call/result and
  permission verdict as JSONL in `logs/` — replayable for debugging.
- **Persistent memory**: facts survive across sessions via `memory/`.
- **Skill packages**: markdown instructions in `skills/<name>/SKILL.md`
  the agent discovers and loads on demand.
- **Context compaction**: long conversations are squeezed back under a
  token budget automatically.
- **Two front ends**: a Rich-styled text REPL (default) and an experimental
  full-screen TUI (`--tui`) with collapsible reasoning blocks.
- **Robustness**: repeated identical tool calls are short-circuited,
  malformed tool arguments are repaired, and Groq's `tool_use_failed`
  errors are salvaged or retried — all visible in the log.

## Quick start

```bash
# 1. Install (developer setup — see "Installing" for the pip route)
pixi install

# 2. Point it at a model (any OpenAI-compatible endpoint, or Groq)
cp .env.example .env      # then edit: LLM_ENDPOINT + LLM_MODEL, or GROQ_API_KEY

# 3. Run
pixi run start            # same as: pixi run make-harness
```

The model you point at **must support native OpenAI-style tool calling**
(`tools` / `tool_calls` in the chat-completions API). There is no
text-parsed fallback for models that lack it (plan.md Stage 9, not built).

## Configuring the backend

### Selection order

`make_harness/llm_providers.py::get_llm_client()` picks a backend from the
environment, first match wins:

| If this is set | Backend | Model | Endpoint |
|---|---|---|---|
| `LLM_ENDPOINT` | OpenAI-compatible | `LLM_MODEL` (default `default`) | `LLM_ENDPOINT` |
| `GROQ_API_KEY` (and no `LLM_ENDPOINT`) | Groq | `openai/gpt-oss-120b` | `https://api.groq.com/openai/v1` |
| neither | OpenAI-compatible | `default` | `http://localhost:8000/v1` |

`LLM_API_KEY` is optional: when unset (or `dummy`) no `Authorization`
header is sent, which is what local servers expect. Set it for OpenAI or
any hosted endpoint.

### Examples

```bash
# Ollama
LLM_ENDPOINT=http://localhost:11434/v1
LLM_MODEL=qwen2.5-coder:7b

# vLLM
LLM_ENDPOINT=http://localhost:8000/v1
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct

# OpenAI
LLM_ENDPOINT=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...

# Groq (only used when LLM_ENDPOINT is unset)
GROQ_API_KEY=gsk_...
```

### The `.env` file

At startup the CLI loads the **first** `.env` it finds, in this order:

1. `./.env` — the directory you launch from
2. `~/.make_harness/.env` — per-user default
3. `<repo>/.env` — next to `pyproject.toml` (developer checkout)

Rules: `KEY=value` per line, `#` comments and blank lines ignored,
surrounding quotes stripped, split on the first `=` only. **A variable
already set in your shell is never overridden**, so `LLM_MODEL=other
make-harness` works for a one-off. `MAKE_HARNESS_NO_ENV=1` disables the
loader entirely. Keep `.env` out of version control — it holds keys.
[`.env.example`](.env.example) is the template.

### Every environment variable

| Env var | Purpose | Default |
|---|---|---|
| `LLM_ENDPOINT` | OpenAI-compatible base URL (include `/v1`) | unset → see selection order |
| `LLM_MODEL` | model name sent in every request | `default` |
| `LLM_API_KEY` | bearer token; omit for local servers | unset → no auth header |
| `GROQ_API_KEY` | selects the Groq backend when `LLM_ENDPOINT` is unset | unset |
| `TAVILY_API_KEY` / `BRAVE_API_KEY` | enables the `web_search` tool (Tavily wins if both) | unset → tool returns a clear error |
| `HARNESS_TOKEN_BUDGET` | context-compaction threshold, in ~tokens (chars ÷ 4) | `60000` |
| `HARNESS_REASONING_FOLD_CHARS` | TUI: reasoning longer than this starts collapsed | `400` |
| `NO_COLOR` | disables ANSI colors when set | unset → colors on a TTY |
| `MAKE_HARNESS_NO_ENV` | skip `.env` loading when set | unset |

## Installing

### Option A — developer setup (this repo, via pixi)

Works the same on Windows and Ubuntu/Linux — `pixi.toml` targets both
`win-64` and `linux-64`. On Ubuntu, install pixi first if you don't have it:
`curl -fsSL https://pixi.sh/install.sh | sh` (then open a new shell).

```bash
pixi install          # creates the env and editable-installs this project
pixi run start        # = make-harness
pixi run test         # = pytest
pixi run build        # = python -m build --outdir dist
```

`pixi install` does an **editable install** of the project itself (see
`pixi.toml`'s `[pypi-dependencies]`), which is what registers the
`make-harness` command inside the pixi environment. `pixi run python
main.py` and `pixi run python -m make_harness` work too.

### Option B — standalone CLI (pip, no repo checkout needed)

```bash
pixi run build                      # or: pip install build && python -m build --outdir dist
python -m venv myenv
myenv/bin/pip install dist/make_harness-0.1.0-py3-none-any.whl   # or the .tar.gz
myenv/bin/make-harness --version
```

On Windows use `myenv\Scripts\pip.exe` / `myenv\Scripts\make-harness.exe`.
Requires Python 3.10+; runtime dependencies are `requests`,
`prompt_toolkit` and `rich`. Once installed, `make-harness` runs from any
directory — tools like `read_file` / `run_command`, and the `logs/`,
`memory/` and `skills/` folders, are all relative to wherever you launch it.

## Using the text REPL (default)

```
╭─────────────────────────────────────╮
│ make-harness v0.1.0 • qwen2.5-coder │
╰─────────────────────────────────────╯
log:   logs\20260912_101500_3f9a1c2b.jsonl
tools: read_file, write_file, run_command, load_skill, web_search, http_request, save_memory, read_memory

Shortcuts:
  @path     Attach files/folders
  /clear    Reset conversation (memory kept)
  exit      Quit

you >
```

- **Ask for things.** The agent answers, calling tools as needed. Each call
  is traced as `→ tool(args)` / `← N chars`; the final answer appears in a
  green `agent` panel.
- **`@path` mentions** — `Explain @make_harness/llm.py` attaches the file's
  content to your message (folders attach a listing), so the model reads it
  without spending a `read_file` call. Only existing paths expand;
  `@gmail.com` in prose stays plain text. `~` expands to your home
  directory and trailing punctuation is ignored (`@llm.py.`). Every real
  attachment is confirmed with an `@ attached ...` line. Attachments are
  capped at 20 000 chars, keeping the head and the tail.
- **`@` pop-up picker** — in a real terminal, typing `@` opens a completion
  menu of the current directory (folders first, then files); keep typing to
  filter, `Tab`/arrows to select, `/` to descend. It falls back to plain
  typing when stdin/stdout isn't a TTY (piped input, scripts, CI).
- **Permission prompts** — when a gated tool is requested you get an
  `allow?` dropdown with four choices (arrow keys + Enter, or type to
  filter):
  - `yes` — allow this one call
  - `no` — deny this one call
  - `always` — allow this tool for the rest of the session
  - `deny` — block this tool for the rest of the session

  Any denial (`no` or `deny`) ends the turn immediately with
  `[tool call denied — tell me how to proceed]`; the model does not get to
  retry variants of the rejected call. Ctrl+C at the prompt counts as a
  denial.
- **`/clear`** resets the conversation to just the system prompt — the
  memory and skills indexes folded into it survive. An unknown `/command`
  prints the list of available commands instead of going to the model.
- **`exit`**, **`quit`**, Ctrl+C or Ctrl+D ends the session.
- Colors switch off automatically when output is piped, or with
  `NO_COLOR=1`.

## Using the TUI (`--tui`, experimental)

```bash
make-harness --tui
```

A full-screen layout: header, scrollable transcript, input box, footer.
The transcript shows `YOU`, `THINKING` (the model's reasoning, when the
backend returns one), `TOOL` (call + result with a ✓ / ✗ / ⊘ outcome
mark) and `AGENT` blocks. Reasoning longer than
`HARNESS_REASONING_FOLD_CHARS` (400) starts collapsed.

| Key | Action |
|---|---|
| Enter | submit the input line |
| ↑ / ↓ | move focus between transcript blocks (only when the input is empty) |
| Space | collapse / expand the focused reasoning block |
| PgUp / PgDn, Home / End | scroll the transcript |
| Esc | clear the input; on an empty input, quit |
| Ctrl+C / Ctrl+D | quit |
| `exit` or `quit`, then Enter | quit |

Caveats, all by design of "experimental":

- Requires a real terminal. Without a TTY (piped input, CI) `--tui`
  silently falls back to the text REPL.
- **Permission prompts are not wired into the TUI yet.** A gated tool
  (`write_file`, `run_command`, `http_request`) will try to open a console
  prompt underneath the full-screen app. Use the text REPL for anything
  that writes files or runs commands; the TUI is fine for read-only work.
- Slash-command output is not shown in the TUI; it is written to the log.
- Works best in Windows Terminal or a Linux terminal; the classic Windows
  console may not render the box characters.

## Tools

Registered at startup from `make_harness/toolsets/`. "Gate" is what the
permission policy does with the call.

| Tool | What it does | Gate | Limits |
|---|---|---|---|
| `read_file(path)` | file contents with line numbers | auto | first 2 000 lines |
| `write_file(path, content)` | create/overwrite; creates parent dirs | asks | — |
| `run_command(command)` | shell command; returns exit code + stdout/stderr | asks | 60 s timeout; 10 000 chars kept (head + tail) |
| `web_search(query)` | top 5 results via Tavily or Brave | auto | needs `TAVILY_API_KEY` or `BRAVE_API_KEY` |
| `http_request(method, url, headers_json, body_json)` | any HTTP call; returns status + body | asks | 30 s timeout; 10 000 chars |
| `save_memory(name, content)` / `read_memory(name)` | persistent facts in `memory/` | auto | — |
| `load_skill(name)` | full instructions of a `skills/<name>/SKILL.md` | auto | — |

Tool exceptions never crash the loop — they come back to the model as an
`Error in <tool>: ...` string, and the log records them.

### Memory

`save_memory` writes `memory/<slug>.md` and appends one line to
`memory/MEMORY.md`. Only the index is injected into the system prompt at
startup; the agent calls `read_memory` for details (progressive
disclosure). Both live in the current working directory.

### Skills

A skill is `skills/<name>/SKILL.md`:

```markdown
---
name: commit-messages
description: How to write commit messages for this repo.
---
Instructions the agent follows once it loads the skill...
```

Only `name: description` pairs go into the system prompt; `load_skill`
fetches the body on demand. Drop a new folder in and restart — no code
changes. `skills/commit-messages/` ships as the example.

## Extending it

**Add a tool** — one function, one import:

```python
# make_harness/toolsets/clock.py
from make_harness.tools import tool

@tool
def now(tz: str = "UTC") -> str:
    """Return the current time in the given IANA timezone."""
    ...
```

Then `import make_harness.toolsets.clock  # noqa: F401` next to the other
toolset imports in `make_harness/cli.py`. Type hints become the JSON
schema (`str`/`int`/`float`/`bool`; anything else is `string`), the
docstring becomes the description, parameters without defaults are
required. New tools are gated by default; add the name to
`Policy.AUTO_ALLOW` in `make_harness/policy.py` if it is read-only.

**Add a slash command** — in `make_harness/commands.py`:

```python
@command
def tokens(messages):
    """Show the estimated context size."""
    from make_harness.context import estimate_tokens
    return messages, f"~{estimate_tokens(messages)} tokens"
```

A command receives the message list and returns `(new_messages, output)`.

**Swap or add a backend** — subclass `OpenAICompatibleModel` in
`make_harness/llm_providers.py` (as `GroqChatModel` does) and branch on it
in `get_llm_client()`. Nothing else in the harness knows about HTTP.

## How a turn works

1. Your input is expanded (`@mentions`), logged, and appended to `messages`.
2. If the estimated size exceeds `HARNESS_TOKEN_BUDGET`, compaction runs:
   old tool results are stubbed to 200 chars; if still over, everything
   between the system prompt and the last 8 messages is summarized by the
   model into one message; as a last resort recent tool results are
   stubbed too. Tool-call/result pairs are never split.
3. `run_turn` calls the model with the tool schemas. Up to 15 round trips:
   - no `tool_calls` → that content is the answer.
   - each call: parse args (repairing prose-wrapped JSON), skip a verbatim
     repeat of the previous call, ask the permission policy, execute,
     append the result as a `role: tool` message.
   - a denial stops the batch and the turn.
4. Hitting 15 steps returns `[stopped: reached 15 steps without a final answer]`.

Every step is in the log. Event kinds: `user_message`, `mention`,
`command`, `compaction`, `llm_request`, `llm_response`, `tool_call`,
`args_repaired`, `permission`, `short_circuit`, `tool_result`,
`turn_interrupted`, `done`, `max_steps`, `error`. One file per session:
`logs/<YYYYMMDD_HHMMSS>_<run-id>.jsonl` in the current directory.

## Running the tests

```bash
pixi run test                 # or: pytest -q
pytest -q tests/test_loop.py  # one module
pytest -q -k "denial"         # by keyword
```

233 tests, all offline — a scripted stub LLM and stubbed `requests`; no
API key, no network, no real terminal. `tests/conftest.py` sets
`MAKE_HARNESS_NO_ENV` so the suite never reads your `.env`. Coverage by
module:

| Area | Files | What is checked |
|---|---|---|
| Agent loop | `test_loop.py` | short-circuit of repeats, argument repair, denial ends the turn, batch auto-deny, max-steps, unknown tool, log trail, `on_event` hook |
| LLM adapter | `test_llm.py`, `test_llm_salvage.py` | `reasoning` pass-through, `tool_use_failed` salvage, retry ladder 0.2 → 0.6 → 1.0, non-retryable errors |
| Backends | `test_llm_providers.py` | factory priority (`LLM_ENDPOINT` > `GROQ_API_KEY` > local), request payload, auth header only with a key, HTTP error surfacing |
| Context | `test_context.py` | three compaction steps, tool-pair safety, summary request shape |
| Tools | `test_tools.py`, `test_fs.py`, `test_shell.py`, `test_web.py`, `test_truncate.py` | schema generation, error wrapping, line caps, exit codes, timeout, Tavily/Brave selection, `http_request` shape |
| Memory & skills | `test_memory.py`, `test_skills.py` | slugging, save/read round trip, index de-dup, SKILL.md parsing (CRLF, extra fields) |
| Permission gate | `test_policy.py`, `test_prompt.py` | yes/no/always/deny semantics, `_ask` as the only I/O seam, the pickers |
| CLI | `test_cli.py`, `test_commands.py`, `test_mentions.py`, `test_repl_pipe.py`, `test_ui.py`, `test_log.py` | `.env` lookup order and no-override rule, `--version`/`--help`/`--tui` fallback, slash-command registry, `@path` expansion, piped-BOM exit, JSONL log format |
| TUI | `test_tui_blocks.py`, `test_tui_render.py`, `test_tui_app.py` | transcript model, fold state, rendering, headless key bindings |

Four tests spawn the CLI in a subprocess and one waits out a 1 s shell
timeout, so the whole suite takes about 5 s. CI
(`.github/workflows/test.yml`) runs it on every push.

## Manual smoke checks

Automated tests never call a real model. After changing anything on the
LLM path, run these in a live session:

1. **Chat + logging** — `Reply with exactly: STAGE0-OK` → that reply; the
   newest `logs/*.jsonl` has one `llm_request` and one `llm_response`.
2. **Tools** — `Read pixi.toml and tell me which python version it pins.`
   → a `read_file` call, answer `3.12`. Then
   `Create hello.txt containing exactly: Hello from the harness` → a
   `write_file` prompt; pick `yes`, check the file, delete it.
3. **Permission gate** — ask for a command, pick `no` → the turn ends with
   `[tool call denied — tell me how to proceed]` and no retry. Ask again,
   pick `deny` → every later `run_command` is refused without a prompt.
4. **Memory** — `Remember for future sessions that my favorite editor is
   VS Code.` → `memory/MEMORY.md` gains a line. New session:
   `Which editor do I prefer? Check your memory.` → `VS Code`.
5. **Compaction** — start with `HARNESS_TOKEN_BUDGET=800`, ask it to read
   `plan.md`, then ask a follow-up; the log shows a `compaction` event with
   `tokens_after` well below `tokens_before` and the follow-up still
   answers correctly.
6. **Skills** — `Load the relevant skill before I commit, then summarize
   its style in one sentence.` → a `load_skill({"name": "commit-messages"})`
   call found via the index, no path hints needed.
7. **`/clear`** — ask a math question, `/clear`, then
   `Did I ask you a math question earlier?` → `No`.

## Troubleshooting

- **`LLM backend error 404` / connection refused** — `LLM_ENDPOINT` must
  be the base URL *including* `/v1` (the harness appends
  `/chat/completions`); make sure the server is up and the model name in
  `LLM_MODEL` is one it serves.
- **The model answers in prose instead of calling tools** — it lacks
  native tool calling. Pick a tool-capable model; there is no text-parsed
  fallback.
- **`LLM backend error 400 ... tool_use_failed` (Groq)** — normally
  salvaged or retried automatically; if it reaches you, the model emitted
  unparseable tool syntax three times in a row. Try another model.
- **Wrong backend selected** — `LLM_ENDPOINT` outranks `GROQ_API_KEY`, and
  shell variables outrank `.env`. Run with `MAKE_HARNESS_NO_ENV=1` to rule
  the file out.
- **Garbled box characters** — use Windows Terminal, or set `NO_COLOR=1`
  for plain output.
- **`exit` didn't quit under PowerShell 5.1 piping** — handled: piped
  input is decoded as UTF-8 and a leading BOM is dropped.

## Layout

```
make_harness/
  cli.py             argparse entry point, .env loader, text REPL, TUI wiring
  commands.py        /clear and other slash commands (registry, not sent to the LLM)
  prompt.py          @ pop-up file picker + permission dropdown (prompt_toolkit)
  mentions.py        @path mention expansion (file/folder attachments)
  ui.py              ANSI styling helpers (stdlib, NO_COLOR-aware)
  llm.py             LLM adapter (normalization + tool_use_failed salvage/retry)
  llm_providers.py   backends: OpenAICompatibleModel, GroqChatModel, get_llm_client()
  log.py             JSONL run logger
  tools.py           @tool decorator + registry
  loop.py            the agent loop (run_turn)
  policy.py          permission gate
  context.py         token budget + compaction
  toolsets/          fs, shell, web, memory, skills tool implementations
  tui/               blocks.py (model) · render.py (formatting) · app.py (Application)
  architecture.md    runtime call graph + component table
  __main__.py        enables `python -m make_harness`
skills/              SKILL.md packages the agent discovers and can load
tests/               pytest suite (offline — stub LLM, no API key needed)
.github/workflows/   CI: pytest on every push
.env.example         configuration template (copy to .env)
main.py              thin shim so `python main.py` still works
pyproject.toml       build metadata + `make-harness` console-script entry point
pixi.toml            dev environment (editable-installs this project)
plan.md              staged build plan + lessons learned
dist/                built sdist/wheel (gitignored, `python -m build`)
logs/                one JSONL file per session (gitignored)
memory/              persistent agent memory (gitignored)
```

## License

MIT — see [LICENSE](LICENSE).
