# make_harness

A minimal coding-agent harness built from scratch, bottom-up — to understand
how coding agents (Claude Code, Codex CLI, ...) actually work, without
LangChain or any agent framework.

The core idea: an agent is a loop around one function —
`complete(messages, tools) -> {content, tool_calls}`. Everything else
(tools, permissions, logging, context management, sessions, subagents, the
UI) is built around that loop in small, verifiable stages. See
[plan.md](plan.md) for the stage-by-stage plan; each stage is one git
commit, so `git log --oneline` reads as a tutorial.

Stages 24–34 align the harness with
[neuralcode](https://github.com/avbiswas/neural-code), a minimal Python
coding-agent harness built the same way: the OpenAI SDK, the `.agents/`
directory layout, and its feature set. They are re-implemented in this
codebase's own shape, with Windows support, rather than copied.

## What it does

- **A real CLI**: installs as the `make-harness` command, plus
  `python -m make_harness` as a fallback.
- **Any OpenAI-compatible endpoint**: OpenAI, Groq, OpenRouter, or a local
  vLLM / Ollama / LM Studio server, selected by `BASE_URL`, `MODEL` and
  `API_KEY` alone. `make_harness/llm.py` is the only file that talks to the
  model, through the `openai` SDK.
- **Tools from plain functions**: decorate a Python function with `@tool`
  and its JSON schema is generated from the signature and docstring.
- **File editing**: `read_file` pages through long files, and `str_replace`
  makes exact edits that keep each file's line endings.
- **Permission rules**: read-only shell commands run, destructive or network
  commands (`rm`, `del`, `curl`, `git push`, ...) are blocked, and everything
  else asks `yes` / `no` / `always` / `deny`. Writes inside the project run;
  writes outside it ask.
- **Sandbox on Linux**: with bubblewrap installed, shell commands can write
  only inside the project and have no network.
- **Planning**: `write_todos` keeps a plan outside the transcript and shows
  it back to the model on every request.
- **Subagents**: `task` explores the codebase in its own context window and
  returns only its findings.
- **Context management**: long tool output is cut and saved to a temp file,
  finished turns' tool output shrinks, and the conversation is compacted into
  a handoff note when a request nears `CONTEXT_WINDOW`.
- **Per-request context**: the date, git branch, current plan and files
  changed since the agent's last turn are added to the end of every request.
- **Sessions**: every chat is saved; `--resume`, `/sessions` and `/rewind`.
- **Memory and skills**: facts in `memory/`, and `SKILL.md` packages in
  `.agents/skills/` that the agent loads on demand.
- **Full run logs**: every LLM request/response, tool call/result and
  permission verdict as JSONL in `logs/`.
- **Robustness**: repeated identical tool calls are short-circuited,
  malformed tool arguments are repaired, and Groq's `tool_use_failed`
  errors are salvaged or retried.

## Quick start

```bash
# 1. Install (developer setup — see "Installing" for the pip route)
pixi install

# 2. Point it at a model: any OpenAI-compatible endpoint
cp .env.example .env      # then edit BASE_URL and MODEL (and API_KEY for hosted endpoints)

# 3. Run
pixi run start            # same as: pixi run make-harness
```

The model you point at **must support native OpenAI-style tool calling**
(`tools` / `tool_calls` in the chat-completions API). There is no
text-parsed fallback for models that lack it.

## Configuring the backend

Three settings pick the backend:

| Env var | Purpose | Default |
|---|---|---|
| `BASE_URL` | OpenAI-compatible base URL, including `/v1` | required |
| `MODEL` | model name sent in every request | required |
| `API_KEY` | bearer token; leave unset for local servers | a placeholder the SDK accepts |

```bash
# Ollama
BASE_URL=http://localhost:11434/v1
MODEL=qwen2.5-coder:7b

# LM Studio
BASE_URL=http://localhost:1234/v1
MODEL=qwen/qwen3-4b
CONTEXT_WINDOW=8192

# OpenAI
BASE_URL=https://api.openai.com/v1
MODEL=gpt-4o-mini
API_KEY=sk-...

# Groq
BASE_URL=https://api.groq.com/openai/v1
MODEL=openai/gpt-oss-120b
API_KEY=gsk_...
```

Upgrading from an older checkout? `LLM_ENDPOINT`, `LLM_MODEL`,
`LLM_API_KEY` and `GROQ_API_KEY` are no longer read. If they are set and
`BASE_URL` / `MODEL` are not, startup stops with an error naming what each
was renamed to.

### The env file

At startup the CLI loads the **first** file it finds:

1. `./.env` — the directory you launch from
2. `~/.agents/env` — your per-user default

Rules: `KEY=value` per line, `#` comments and blank lines ignored,
surrounding quotes stripped, split on the first `=` only. **A variable
already set in your shell is never overridden**, so `MODEL=other
make-harness` works for a one-off. `MAKE_HARNESS_NO_ENV=1` disables the
loader entirely. Keep `.env` out of version control — it holds keys.
[`.env.example`](.env.example) is the template.

### Every environment variable

| Env var | Purpose | Default |
|---|---|---|
| `BASE_URL` / `MODEL` / `API_KEY` | the backend, see above | — |
| `CONTEXT_WINDOW` | the context length the server loads the model with, in tokens; compaction runs at 85% of it | `128000` |
| `TAVILY_API_KEY` / `BRAVE_API_KEY` | enables `web_search` (Tavily wins if both are set) | unset → the tool returns a clear error |
| `NO_COLOR` | disables ANSI colors | unset → colors on a TTY |
| `MAKE_HARNESS_NO_ENV` | skip the env file | unset |

Set `CONTEXT_WINDOW` for small local models: the context they are *loaded*
with is often far below what they advertise.

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
`pixi.toml`'s `[pypi-dependencies]`), which registers the `make-harness`
command inside the pixi environment and pulls in the runtime dependencies
declared in `pyproject.toml`.

### Option B — standalone CLI (pip, no repo checkout needed)

```bash
pixi run build                      # or: pip install build && python -m build --outdir dist
python -m venv myenv
myenv/bin/pip install dist/make_harness-0.1.0-py3-none-any.whl   # or the .tar.gz
myenv/bin/make-harness --version
```

On Windows use `myenv\Scripts\pip.exe` / `myenv\Scripts\make-harness.exe`.
Requires Python 3.10+; runtime dependencies are `openai`, `prompt_toolkit`,
`pyyaml`, `requests` and `rich`. Once installed, `make-harness` runs from any
directory. File tools, the permission rules' "project", `logs/`, `memory/`
and `.agents/skills/` are all relative to wherever you launch it.

### Sandbox (Linux, optional)

Install bubblewrap (`sudo apt install bubblewrap`) and shell commands run
with the filesystem read-only except the project directory and a throwaway
`/tmp`, and with no network. The banner shows `sandbox: bubblewrap` or
`sandbox: none`. Windows has no equivalent, so there the permission rules
are the only fence.

## Using the REPL

```
╭─────────────────────────────────────╮
│ make-harness v0.1.0 • qwen/qwen3-4b │
╰─────────────────────────────────────╯
log:   logs\20260917_101500_3f9a1c2b.jsonl
tools: read_file, write_file, str_replace, run_command, load_skill, write_todos, web_search, http_request, task, save_memory, read_memory
sandbox: none

Shortcuts:
  @path      Attach files/folders
  /clear     Reset conversation (memory kept)
  /compact   Summarize history to free context
  /rewind    Go back to before an earlier message
  /sessions  Open a saved chat
  /exit      Quit (exit and quit work too)

you >
```

- **Ask for things.** The agent answers, calling tools as needed. Each call
  is traced as `→ tool(args)` / `← N chars`, each request as
  `tokens: N in · N out · N cached`, and the final answer appears in a green
  `agent` panel. A subagent's steps are indented under its `task` call.
- **`@path` mentions** — `Explain @make_harness/llm.py` attaches the file's
  content to your message (folders attach a listing), so the model reads it
  without spending a `read_file` call. Only existing paths expand;
  `@gmail.com` in prose stays plain text. Attachments are capped at 20 000
  chars, keeping the head and the tail.
- **`@` pop-up picker** — in a real terminal, typing `@` opens a completion
  menu of the current directory. Input history is kept in
  `~/.agents/history`, so the up arrow reaches earlier sessions.
- **Permission prompts** — when a call needs approval you get an `allow?`
  dropdown:
  - `yes` — allow this one call
  - `no` — deny this one call
  - `always` — allow this tool for the rest of the session
  - `deny` — block this tool for the rest of the session

  A denial ends the turn with `[tool call denied — tell me how to proceed]`;
  the model does not get to retry variants. A command blocked by a rule is
  never offered to you — the model is told it's blocked, and the turn goes on.
- **`/clear`** resets the conversation and the todo list to just the system
  prompt. The cleared chat stays saved; what follows goes to a new session.
- **`/compact`** summarizes the older part of the conversation now. It says
  whether it compacted, found nothing old enough, or kept the original
  because the summary wasn't smaller.
- **`/rewind`** lists your recent messages; pick one to drop it and
  everything after it.
- **`/sessions`** lists this project's other saved chats and opens the one
  you pick. **`make-harness --resume`** opens the most recent one at startup.
- An unknown `/command` prints the list of available commands.
- **`/exit`**, **`exit`**, **`quit`**, Ctrl+C or Ctrl+D ends the session.

## Tools

Registered at startup from `make_harness/toolsets/` and
`make_harness/subagent.py`. "Gate" is what the permission policy does.

| Tool | What it does | Gate | Limits |
|---|---|---|---|
| `read_file(path, offset, limit)` | file contents with line numbers, paged | runs | 2 000 lines or 10 000 chars per page |
| `write_file(path, content)` | create/overwrite; creates parent dirs | runs inside the project, asks outside or in `.git` | — |
| `str_replace(path, old_str, new_str, allow_multi_edit)` | exact edit; must match once unless `allow_multi_edit` | same as `write_file` | keeps CRLF/LF endings |
| `run_command(command)` | shell command; exit code + stdout/stderr | per command, see below | 60 s timeout; 10 000 chars inline |
| `web_search(query)` | top 5 results via Tavily or Brave | runs | needs a search API key |
| `http_request(method, url, headers_json, body_json)` | any HTTP call; status + body | asks | 30 s timeout; 10 000 chars inline |
| `save_memory(name, content)` / `read_memory(name)` | persistent facts in `memory/` | runs | — |
| `load_skill(name)` | full instructions of a skill | runs | — |
| `write_todos(todos)` | replaces the plan: `[{content, status}]` | runs | one `in_progress` at a time |
| `task(description)` | exploration subagent; returns its report | runs (its own calls are gated) | 12 steps |

Tool exceptions never crash the loop — they come back to the model as an
error string, and the log records them.

### Shell command rules

`policy.SHELL_RULES` rates each part of a command; a compound command
(`&&`, `||`, `|`, `;`) is split outside quotes and its strictest part wins.

- **Runs:** read-only commands in POSIX and Windows spellings — `ls`/`dir`,
  `cat`/`type`, `grep`/`rg`/`findstr`, `find`, `which`/`where`, `head`,
  `tail`, `wc`, `git status/diff/log/show`, `pytest`, `pixi run test`, ...
- **Blocked:** `rm`, `rmdir`, `del`, `rd`, `Remove-Item`, `format`, `sudo`,
  `chmod`, `chown`, `curl`, `wget`, `Invoke-WebRequest`, `git push`,
  `git reset --hard`, `git clean`.
- **Asks:** everything else — and any part containing `>`, `$`, `%` or a
  backtick, since redirection writes files and expansion can run commands or
  read secrets (`echo %API_KEY%`).

### Memory

`save_memory` writes `memory/<slug>.md` and appends one line to
`memory/MEMORY.md`. Only the index is injected into the system prompt at
startup; the agent calls `read_memory` for details.

### Skills

A skill is `<dir>/<name>/SKILL.md`, found in `./.agents/skills/` (the
project's) and `~/.agents/skills/` (your own); the project's copy wins a
name clash:

```markdown
---
name: commit-messages
description: How to write commit messages for this repo.
---
Instructions the agent follows once it loads the skill...
```

Frontmatter is YAML. Only `name: description` pairs go into the system
prompt; `load_skill` fetches the body on demand. Drop a new folder in and
restart. `.agents/skills/commit-messages/` ships as the example.

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
toolset imports in `make_harness/cli.py`. Type hints become the JSON schema
(`str`/`int`/`float`/`bool`; anything else is `string`), the docstring
becomes the description, and parameters without defaults are required. For
richer arguments pass the schema yourself: `@tool(parameters={...})`, as
`write_todos` does. New tools ask by default; add the name to
`Policy.AUTO_ALLOW` in `make_harness/policy.py` if it is read-only.

**Add a slash command** — in `make_harness/commands.py`:

```python
@command
def tokens(messages, ctx):
    """Show the estimated context size."""
    return messages, f"~{history.estimate(messages)} tokens"
```

A command receives the message list and a `Context` (log, LLM, session,
chooser, system prompt) and returns `(new_messages, output)`; `None` for
`new_messages` ends the session. A command that changes history must record
it in `ctx.session` (`rewind_to`, `replace` or `start_new`).

**Use a non-OpenAI-compatible provider** — keep the contract of
`LLMClient.complete()` in `make_harness/llm.py` (plain dicts in, a dict with
`content`, `reasoning`, `tool_calls`, `usage`, `raw` out). Nothing else in
the harness knows about the backend.

## How a turn works

1. Your input is expanded (`@mentions`), logged, and appended to `messages`.
   The REPL notes the git branch and which files changed since the agent's
   last turn.
2. `run_turn` loops, up to 15 requests:
   - `history.fit` drops old tool results if the transcript is still over
     85% of `CONTEXT_WINDOW`.
   - The request is sent with an `<env>` block at the end — date, git
     branch, `<todos>`, and a `<system-reminder>` naming changed files. The
     block is rebuilt every request and never stored.
   - No `tool_calls` → that content is the answer.
   - Each call: parse arguments (repairing prose-wrapped JSON), skip a
     verbatim repeat of the previous call, ask the permission policy,
     execute, and append the result as a `role: tool` message. Output over
     10 000 chars keeps its head and tail inline, and the whole text goes
     to a temp file the agent can page with `read_file`.
   - A user's denial stops the batch and the turn; a rule's block doesn't.
3. When the turn ends, it is saved to the session, its temp files are
   deleted, and its tool results shrink to 300 chars.
4. If the last request's `prompt_tokens` crossed 85% of `CONTEXT_WINDOW`,
   compaction runs: one LLM call writes a handoff note (Goal / Decisions /
   Files / State / Next step), and the transcript becomes the system prompt,
   that note, and a recent tail of about 35% of the window. No tool result
   is separated from its call.

Every step is in the log — one file per session,
`logs/<YYYYMMDD_HHMMSS>_<run-id>.jsonl` in the current directory. Event
kinds: `user_message`, `command`, `compaction`, `context_fit`,
`llm_request`, `llm_response`, `tool_call`, `args_repaired`, `permission`,
`short_circuit`, `tool_result`, `turn_interrupted`, `done`, `max_steps`,
`error`, and `subagent_start` / `subagent_done` (with the subagent's own
events tagged `agent: "subagent"`).

## Files on disk

| Path | What | Written by |
|---|---|---|
| `logs/*.jsonl` | every event of a run, for debugging | `log.py` |
| `~/.agents/sessions/<project>/<id>.jsonl` | saved chats: messages, plus `rewind_to` / `replace` entries | `session.py` |
| `memory/` | persistent facts and their index | `save_memory` |
| `.agents/skills/`, `~/.agents/skills/` | skill packages | you |
| `~/.agents/history` | REPL input history | `prompt.py` |
| `.env`, `~/.agents/env` | settings | you |
| `make-harness-*.txt` in the temp dir | full output of a cut tool result, deleted when the turn ends | `history.py` |

## Running the tests

```bash
pixi run test                 # or: pytest -q
pytest -q tests/test_loop.py  # one module
pytest -q -k "rewind"         # by keyword
```

About 360 tests, all offline: a scripted stub LLM, the real OpenAI SDK over
a mock HTTP transport, and temp directories. No API key, no network, no real
terminal. `tests/conftest.py` sets `MAKE_HARNESS_NO_ENV` so the suite never
reads your `.env`.

| Area | Files |
|---|---|
| Agent loop | `test_loop.py` |
| LLM and settings | `test_llm.py`, `test_config.py` |
| Context | `test_history.py`, `test_compact.py`, `test_context.py` |
| Tools | `test_tools.py`, `test_toolsets.py`, `test_web.py`, `test_memory.py`, `test_skills.py`, `test_todos.py`, `test_subagent.py` |
| Safety | `test_policy.py`, `test_sandbox.py` |
| Sessions and commands | `test_session.py`, `test_commands.py` |
| CLI and I/O | `test_cli.py`, `test_prompt.py`, `test_mentions.py`, `test_log.py` |

Four tests in `test_sandbox.py` need Linux with bubblewrap and are skipped
elsewhere. A few tests start the CLI in a subprocess against an unreachable
endpoint, so the suite takes about 25 s. CI (`.github/workflows/test.yml`)
builds the package on every push.

## Manual smoke checks

Automated tests never call a real model. After changing anything on the
LLM path, run these in a live session:

1. **Tools** — `Read pixi.toml and tell me which python version it pins.`
   → a `read_file` call, answer `3.12`.
2. **Editing** — `In settings.ini change the port to 9090 using str_replace.`
   → one call, no prompt inside the project, line endings unchanged.
3. **Rules** — `Delete old.log with run_command.` → `← blocked by policy`,
   and the model asks you to do it instead.
4. **Planning** — ask for a three-file task and to plan it → `write_todos`
   first, and `<todos>` in the logged requests.
5. **Subagent** — `Use the task tool to find where run_turn is defined.` →
   indented subagent steps and a short report.
6. **Compaction** — start with `CONTEXT_WINDOW=1800`, tell it a codeword,
   then ask several long questions → `Compacted: ...` lines, and the codeword
   is still recalled.
7. **Sessions** — say something, `exit`, run `make-harness --resume` → the
   preview shows it and the model remembers. `/rewind` → `1` drops the last
   message.
8. **Changed files** — edit a tracked file between two turns → `changed
   since the last turn: <file>`.

## Troubleshooting

- **`error: No LLM backend configured`** — set `BASE_URL` and `MODEL`. The
  message names any old `LLM_*` / `GROQ_API_KEY` setting it found.
- **404 / connection refused** — `BASE_URL` must include `/v1`; make sure
  the server is up and serves the model named in `MODEL`.
- **The model answers in prose instead of calling tools** — it lacks
  native tool calling. Pick a tool-capable model.
- **Context-length errors from a local server** — set `CONTEXT_WINDOW` to
  the context the model is actually loaded with.
- **`tool_use_failed` (Groq)** — normally salvaged or retried automatically;
  if it reaches you, the model emitted unparseable tool syntax three times.
- **A command you need is blocked** — run it yourself, or change
  `SHELL_RULES` in `make_harness/policy.py`.
- **Garbled box characters** — use Windows Terminal, or set `NO_COLOR=1`.

## Layout

```
make_harness/
  cli.py          argparse entry point (--version, --resume) and the REPL
  config.py       env-file loader, backend settings, CONTEXT_WINDOW
  llm.py          LLMClient over the openai SDK (usage, salvage, retry)
  loop.py         the agent loop (run_turn)
  tools.py        @tool decorator + registry
  policy.py       permission rules and the yes/no/always/deny gate
  sandbox.py      bubblewrap wrapper for shell commands (Linux)
  history.py      cap/spill, strip and fit for tool output
  compact.py      handoff-note compaction
  context.py      the per-request <env> block and ChangeTracker
  session.py      saved chats (append-only JSONL)
  subagent.py     the task tool
  commands.py     slash commands and their Context
  prompt.py       @ picker, choice dropdown, input history (prompt_toolkit)
  mentions.py     @path attachments
  ui.py           ANSI styling helpers
  log.py          JSONL run log
  toolsets/       fs, shell, web, memory, skills, todos
  __main__.py     enables `python -m make_harness`
.agents/skills/   skill packages shipped with the project
doc/              architecture.md: call graph + component table
tests/            pytest suite (offline)
.env.example      configuration template
main.py           thin shim so `python main.py` still works
pyproject.toml    build metadata + `make-harness` entry point
pixi.toml         dev environment (editable-installs this project)
plan.md           staged build plan + lessons learned
```

## License

MIT — see [LICENSE](LICENSE).
