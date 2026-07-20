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

- **A real CLI**: installs as the `make-harness` command (`pip install` or
  `pixi run`), plus `python -m make_harness` as a fallback.
- **Custom LLM backend**: `make_harness/llm_providers.py` holds the swappable
  backend (currently Groq); `make_harness/llm.py` is the adapter the rest of
  the harness talks to. Swapping backends touches only `llm_providers.py`.
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

There are two ways to run this: as a **developer**, working in this repo
via pixi; or as a **user**, with the tool `pip install`ed like any other CLI.
Both end up running the same `make-harness` command.

### Option A — developer setup (this repo, via pixi)

Works the same on Windows and Ubuntu/Linux — `pixi.toml` targets both
`win-64` and `linux-64`. On Ubuntu, install pixi first if you don't have it:
`curl -fsSL https://pixi.sh/install.sh | sh` (then open a new shell).

**Ubuntu / Linux (bash):**

```bash
pixi install
export GROQ_API_KEY="..."        # required
export TAVILY_API_KEY="..."      # optional, enables web_search (or BRAVE_API_KEY)
pixi run start
```

**Windows (PowerShell):**

```powershell
pixi install
$env:GROQ_API_KEY = "..."        # required
$env:TAVILY_API_KEY = "..."      # optional, enables web_search (or BRAVE_API_KEY)
pixi run start
```

`pixi install` does an **editable install** of the project itself (see
`pixi.toml`'s `[pypi-dependencies]`), which is what registers the
`make-harness` command inside the pixi environment — `pixi run start` and
`pixi run make-harness` are equivalent. `pixi run python main.py` and
`pixi run python -m make_harness` still work too, for whichever invocation
style you prefer.

### Option B — install as a standalone CLI tool (pip, no repo checkout needed)

Build a distributable tarball (sdist) and wheel from this repo:

```bash
pip install build
python -m build --outdir dist
```

This produces `dist/make_harness-0.1.0.tar.gz` (the source tarball) and
`dist/make_harness-0.1.0-py3-none-any.whl`. Either can be installed with
pip into any Python 3.10+ environment — this was verified end-to-end in a
throwaway venv with no connection to this repo:

```bash
python -m venv myenv
myenv/bin/pip install dist/make_harness-0.1.0.tar.gz   # or the .whl
myenv/bin/make-harness --version
```

On Windows, use `myenv\Scripts\pip.exe` / `myenv\Scripts\make-harness.exe`.
Once installed, `make-harness` runs from any directory — tools like
`read_file`/`run_command` operate relative to wherever you launch it from,
same as any other CLI. Share the `.tar.gz` with someone else and
`pip install make_harness-0.1.0.tar.gz` is all they need (plus `GROQ_API_KEY`).

> `pyproject.toml` (build metadata, used by `pip`/`build`) and `pixi.toml`
> (dev environment, used by `pixi`) are separate, complementary files —
> `pixi.toml` isn't being replaced.

### Running it

```
make-harness v0.1.0 — openai/gpt-oss-120b
log:   logs\20260718_...jsonl
tools: read_file, write_file, run_command, web_search, http_request, save_memory, read_memory
@path attaches a file or folder — e.g. @make_harness/llm.py
type 'exit' or Ctrl+C to quit

you >
```

- Type a request; the agent answers, calling tools as needed (shown as
  `→ tool(args)` / `← result size`).
- **`@path` mentions**: `Explain @make_harness/llm.py` attaches the file's
  content to your message (folders attach a listing), so the model reads it
  without spending a `read_file` call. Only existing paths expand —
  `@gmail.com` in prose stays plain text. Every real attachment is
  confirmed with an `@ attached ...` line; no line means the path didn't
  resolve. Attachments are capped at 20k chars (head+tail).
- **`@` pop-up picker**: in a real terminal, typing `@` opens a completion
  menu of the current directory (folders first, then files); keep typing to
  filter, `Tab`/arrow keys to select, `/` to descend into a folder. Falls
  back to plain typing automatically when stdin/stdout isn't a TTY (piped
  input, scripts, CI) — the attachment behavior above is identical either
  way, the picker is purely a typing aid.
- Output is ANSI-colored (dim tool traces, yellow permission prompts, red
  errors). Colors turn off automatically when output is piped, or set
  `NO_COLOR=1`.
- When a side-effecting tool is requested you'll see
  `allow? y = once / n = deny / a = always` — `n` cancels and hands control
  back to you.
- `exit`, `quit`, or Ctrl+C ends the session.
- Every session writes one JSONL file to `logs/` (created in the current
  working directory); each line is one event (`llm_request`,
  `llm_response`, `tool_call`, `tool_result`, `permission`, `compaction`,
  `error`, `done`).
- `make-harness --version` prints the installed version;
  `make-harness --help` shows CLI usage.

### Verifying each stage manually

Each stage of [plan.md](plan.md) can be re-verified with a short REPL
session. The expected behavior below is what the live tests produced.

#### Stage 0 — chat + logging

Type: `Reply with exactly: STAGE0-OK`

- Expect the reply `STAGE0-OK`.
- Check the newest file in `logs/`: it must contain one `llm_request` line
  (full message list) and one `llm_response` line (raw API response):

```bash
cat "$(ls -t logs/*.jsonl | head -1)"
```
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
   `cat hello.txt` (bash) / `Get-Content hello.txt` (PowerShell), then
   delete the file.

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
when a model emits malformed tool syntax (observed live with
llama-3.3-70b-versatile, the original default model). The adapter salvages
or retries these automatically; you should not see the error surface in
the REPL. The current default model is `openai/gpt-oss-120b`
(`make_harness/llm_providers.py`), which rarely triggers this path — the
salvage stays because it's harmless and only runs on that specific error.

#### Stage 4 — persistent memory

1. Session A: `Remember for future sessions that my favorite editor is VS Code.`
   → a `save_memory` call; `memory/MEMORY.md` gains an index line and
   `memory/favorite-editor...md` appears.
2. Exit, start a fresh session: `Which editor do I prefer? Check your memory.`
   → a `read_memory` call, answer `VS Code`.

#### Stage 5 — context compaction

Force a tiny budget so compaction triggers immediately:

```bash
export HARNESS_TOKEN_BUDGET=800
pixi run start
```
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

```bash
python -c "
import json, glob
p = max(glob.glob('logs/*.jsonl'))
for line in open(p):
    e = json.loads(line)
    if e['kind'] == 'compaction':
        print(e)
"
```
```powershell
Get-Content (Get-ChildItem logs | Sort-Object Name | Select-Object -Last 1).FullName |
  ForEach-Object { $_ | ConvertFrom-Json } | Where-Object kind -eq "compaction"
```

Unset the budget afterwards: `unset HARNESS_TOKEN_BUDGET` (bash) /
`Remove-Item Env:HARNESS_TOKEN_BUDGET` (PowerShell). Default is 60000.

### Running the tests

```bash
pixi run test        # or: pixi run pytest -q
```

The suite covers the pure-logic seams (tool-call salvage, context
compaction, the tool registry's error handling, memory slugs) with a stub
LLM — no API key or network needed. CI (`.github/workflows/test.yml`) runs
the same suite on every push.

### Configuration reference

| Env var | Purpose | Default |
|---|---|---|
| `GROQ_API_KEY` | LLM backend auth | required |
| `TAVILY_API_KEY` / `BRAVE_API_KEY` | enables `web_search` | unset → clear error |
| `HARNESS_TOKEN_BUDGET` | context compaction threshold (tokens) | `60000` |
| `NO_COLOR` | disables ANSI colors when set | unset → colors on TTY |

## Layout

```
make_harness/
  cli.py             argparse entry point + the REPL loop
  prompt.py          @ pop-up file/folder picker (prompt_toolkit)
  mentions.py        @path mention expansion (file/folder attachments)
  ui.py              ANSI styling helpers (stdlib, NO_COLOR-aware)
  llm.py             LLM adapter (normalization + tool_use_failed salvage)
  llm_providers.py    the swappable backend (currently GroqChatModel)
  log.py             JSONL run logger
  tools.py           @tool decorator + registry
  loop.py            the agent loop
  policy.py          permission gate
  context.py         token budget + compaction
  toolsets/          fs, shell, web, memory tool implementations
  __main__.py        enables `python -m make_harness`
tests/               pytest suite (offline — stub LLM, no API key needed)
.github/workflows/   CI: pytest on every push
main.py              thin shim so `python main.py` still works
pyproject.toml       build metadata + `make-harness` console-script entry point
pixi.toml            dev environment (editable-installs this project)
plan.md              staged build plan + lessons learned
dist/                built sdist/wheel tarballs (gitignored, `python -m build`)
logs/                one JSONL file per session (gitignored)
memory/              persistent agent memory (gitignored)
```

## License

MIT — see [LICENSE](LICENSE).
