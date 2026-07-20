# Execution Plan — Bottom-Up Agent Harness

Goal: a minimal, fully understood agent harness built stage by stage.
Each stage is small, working, and verified live before the next begins.
One commit per stage.

> Stages 7–10 below were re-prioritized on 2026-07-19 after external review
> by ChatGPT, DeepSeek, and Gemini (repo pasted as a README description, not
> the code) plus a Nemotron synthesis of all three. See
> `feedback_/feedback_consolidated.md` for the fact-checked reflection —
> what those reviews got right, where they were already out of date, and
> the reasoning behind what's kept vs. cut below.

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

### [x] Stage 7 — Project hygiene (before behavior changes, not after)
Ordered first deliberately: per this repo's own karpathy-guidelines
("define success criteria, write tests, then make them pass"), Stage 8's
behavior changes should land with regression coverage already in place —
and every one of them is trivially unit-testable with a stub LLM, exactly
like the Stage 5 compaction tests that were written, passed, and never
committed.
- `LICENSE` — required for a repo described as open-source; currently
  absent entirely. Five-minute task; blocks legal reuse today.
- `tests/` (pytest): `_salvage_tool_call` (valid/invalid/unmatched cases),
  `context.compact()` (stub/summarize/pairing-safety paths — recreate the
  Stage 5 scratch tests properly), `Registry.execute`'s error path,
  `toolsets/memory.py`'s `_slug()`.
- Minimal CI (`.github/workflows/test.yml`): run pytest on push. No lint
  step yet — not worth the config until the test suite itself exists.
- Update stale model references: the default backend is now
  `openai/gpt-oss-120b` (`llm_providers.py`), but README banners and
  older plan notes still show `llama-3.3-70b-versatile`.
- Verify: `pytest` passes locally; a pushed commit shows a green check.
- Done 2026-07-20 as four atomic commits (LICENSE, tests, CI, doc fixes);
  19 tests passing via `pixi run test`.

### [x] Stage 8 — Robustness hardening
Small, high-value fixes for gaps confirmed by reading the actual code
(see `feedback_/feedback_consolidated.md` §3), built test-first on the
Stage 7 suite:
- **Loop short-circuit**: track the last `(tool_name, args)` the loop
  executed; if the model calls the identical tool with identical args
  again immediately, don't re-execute — return a synthetic tool result
  ("[not executed: identical to your previous call — the result would be
  unchanged; adjust your arguments or approach]"). The nudge must BE the
  tool result, not replace it: every tool_call id requires a role:"tool"
  response or the next API request fails — the same pairing rule the
  Stage 2 deny path already honors. (A floating mid-conversation
  system-role message, as one reviewer sketched, breaks both the pairing
  and some backends.) Distinct from the Stage 2 deny-storm fix — this
  covers *allowed* calls the model repeats.
- **Head+tail truncation**: `toolsets/shell.py` and `toolsets/web.py`
  currently keep the first N chars and drop the rest — backwards for
  shell/build output, where the error is usually at the end. Keep both
  ends of the budget instead.
- **Tool-argument repair**: `loop.py`'s `json.loads()` on tool-call
  arguments currently fails clean (returns an error string) but doesn't
  try to repair first. Add an outermost-`{...}`-extraction attempt before
  giving up — distinct from `llm.py`'s existing Groq-specific
  `tool_use_failed` salvage, which is a different failure mode. (Note:
  that salvage regex targets llama-3.3's `<function=...>` malformation;
  now that the default model is gpt-oss-120b it may rarely fire — it
  stays because it's harmless, only running on `tool_use_failed` errors.)
- Verify: offline stub-LLM unit tests for all three (deterministic —
  coaxing a live 120B model into repeating itself is not), plus one live
  smoke session confirming nothing regressed.
- Done 2026-07-20 as three atomic commits (short-circuit, truncation,
  arg repair), each with its tests; 34 tests passing. Live smoke: full
  loop round-trip against Groq, read_file executed once, correct answer.
  Note: the short-circuit signature lives as a local in run_turn — the
  Stage 10 Session-dataclass trigger ("needs a place to keep
  last_action_signature") did NOT fire, since the signature only has to
  survive across steps within one turn, not across turns.

### [ ] Stage 9 — Local / non-tool-calling model support
Dual-path LLM adapter: native `tool_calls` when the backend supports them
(current behavior, unchanged), a prompt-injected-tools + text-parsed
fallback when it doesn't. Make the fork explicit and visible in
`llm_providers.py` / `llm.py` rather than hidden — this is exactly the
hybrid adapter the original seven AI plan documents proposed for this
project and that the Stage 0 plan explicitly deferred ("native tool
calling only... hybrid fallback deferred").
- **Scope dependency, decide before starting**: the fallback path is
  unverifiable without a backend that actually lacks native tool calling.
  During Stage 0 the explicit decision was "Ollama is not in scope of
  this project" — starting this stage means reversing that (WSL Ubuntu
  can host Ollama or a llama.cpp / vLLM server easily; any
  OpenAI-compatible endpoint without native tools qualifies).
- Verify: same REPL session works identically against Groq (native path)
  and a local model with no native tool-calling support (fallback path),
  including a tool call round-trip on each.

### [ ] Stage 10 — Deferred, opt-in (do not build speculatively)
Each item here has a concrete trigger condition; none is worth doing until
its trigger is real, per this project's own simplicity principle.
- **`Session` dataclass** (bundle `messages`/`memory`/`cwd`/`token_budget`
  instead of separate `run_turn()` args) — trigger: once Stage 8's loop
  short-circuit needs `last_action_signature` to live somewhere, bundling
  it with the rest of the loop's state stops being optional.
- **Real streaming** — `GroqChatModel.chat()` already accepts a `stream`
  param that's always `False` and never wired up. Trigger: perceived
  REPL latency actually becomes annoying, and only after Stage 9 exists
  (streaming a text-parsed fallback response is a different shape of work
  than streaming native `tool_calls` deltas).
- **Plugin auto-discovery folder** (`plugins/*.py` scanned via
  `importlib`) — trigger: adding a tool starts requiring more than the
  current one-line `import make_harness.toolsets.X` in `cli.py`. Not true
  today at 4 toolsets.
- **Declarative YAML/TOML config** — trigger: Stage 9 lands and there are
  2+ real providers to choose between. Building a config file to select
  between one provider is solving a problem that doesn't exist yet.
- Markdown skill packages (`skills/<name>/SKILL.md` + `load_skill` tool),
  subagents for context isolation, session resume from a JSONL log — no
  new trigger information since these were first deferred; still v2+.

### [x] Stage 11 — REPL UX: ANSI colors + @path mentions
User-requested 2026-07-20; done out of numeric order — independent of
Stages 9–10, which stay gated on their own conditions.
- `make_harness/ui.py`: stdlib-only ANSI helpers, auto-disabled for
  non-TTY output and `NO_COLOR` (no rich/colorama dependency). Cyan
  banner/prompt, green answers, dim tool traces, yellow for attention
  (permission prompts, denials, short-circuits), red errors.
- `make_harness/mentions.py`: `@path` in user input attaches the file
  content (folders: a listing) to the outgoing message — same
  "see it without spending a tool call" idea as the Stage 4 memory
  index. Only existing paths expand; each attachment is confirmed with
  an `@ attached` line; capped head+tail at 20k chars via the shared
  truncate(); recorded in the `user_message` log event.
- Learned live: checking the raw mention before the punctuation-stripped
  one made `@a.py.` resolve differently on Windows (ignores trailing
  dots) than Linux — stripped-first keeps platforms identical.
- Verified: 11 new offline tests (45 total); live smoke where the model
  answered from an attached `@pixi.toml` with zero tool calls.

## Deliberately NOT built

- **Event bus** — considered and explicitly rejected (not just deferred).
  ChatGPT's review flagged this as highest priority; DeepSeek and a
  Nemotron synthesis of all reviews independently argued against it —
  pub/sub indirection actively fights this project's "understandable in an
  afternoon" goal, and nothing in the codebase today needs to *react* to
  an event mid-flight (every current consumer of "things that happened" —
  console output, the JSONL log — is a direct call, not a subscriber).
  Revisit only if a concrete subscriber use case shows up, not as an
  architecture-first move.
- Plugin system, middleware chain, state machine, workflow engine, async —
  still deferred, not rejected. The JSONL logger and the policy gate are
  the seams where these can bolt on later without a rewrite.
- Full tool-metadata schema (cost, parallel_safe, examples, tags) — no
  consumer exists; nothing here runs tools in parallel or schedules by
  cost.
- Multi-agent / DAG / MCP / Tree-of-Thought / Reflection — v3+ territory,
  no disagreement among any reviewer on this one.
