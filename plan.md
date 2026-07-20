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
>
> Stages 14–23 (2026-07-20) rebuild the REPL as a full-screen TUI with
> collapsible reasoning blocks and a scrollable transcript, user-requested
> and scoped via a dedicated architecture review (a Plan agent verified
> every prompt_toolkit API against the installed version rather than
> assuming). See design principle 5's note below for the one deliberate
> exception this introduces.

## Design principles

1. The harness is a loop around one function: `complete(messages, tools) -> {content, tool_calls}`.
2. Log everything as JSONL from day one — full session replay from `logs/*.jsonl`.
3. No module exists before the stage that needs it. Nothing speculative.
4. Messages stay plain OpenAI-format dicts. Native tool calling only — no text parsing.
5. Sync code only, except: one background worker thread bridges the
   full-screen TUI (Stage 20) to the synchronous `run_turn()` call — the
   first and only use of `threading` in this codebase, and a deliberate,
   narrated exception rather than a silent departure. `run_turn`,
   `compact`, and `Policy.check` all stay plain synchronous functions;
   only the *scheduling* around them is threaded, via a single direct
   `on_event` callback (Stage 15) — not a pub/sub bus with multiple
   subscribers. See the note on "Deliberately NOT built: event bus"
   below: that rejection's premise (nothing needs to react mid-flight)
   no longer holds for this one path, though the rejection of a general
   multi-subscriber bus still stands.

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
- 2026-07-20 addendum: added `setuptools` and `python-build` as pixi dev
  dependencies plus a `pixi run build` task (`python -m build --outdir
  dist`), so building the tarball/wheel no longer needs a `pip install
  build` outside pixi. `python -m build` still resolves the actual build
  backend from `pyproject.toml` (hatchling, isolated venv) regardless —
  `setuptools`/`python-build` just make the tool itself available inside
  `pixi run`. Verified: `pixi run build` produced both
  `make_harness-0.1.0.tar.gz` and `make_harness-0.1.0-py3-none-any.whl`.

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
- Subagents for context isolation, session resume from a JSONL log — no
  new trigger information since these were first deferred; still v2+.
  (Markdown skill packages, the other item originally listed here,
  shipped in Stage 12 — the trigger became real when the user asked for
  it directly.)

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
- Learned live: PowerShell 5.1 pipes stdin with a UTF-8 BOM; under
  cp1252 decoding, piped `exit` arrived as `ï»¿exit`, missed the exit
  check, and the model politely said goodbye instead of the REPL
  quitting. Piped (non-TTY) stdin is now reconfigured to `utf-8-sig`.
- Verified: 11 new offline tests (45 total); live smoke where the model
  answered from an attached `@pixi.toml` with zero tool calls.
- **`@` pop-up picker** (user-requested follow-up, same day): typing `@`
  in a real terminal now opens a completion menu of the current directory
  (folders first, filtered as you type, Tab/arrows to select) — the
  discoverability fancier harnesses (Claude Code, Codex CLI) have and
  plain `@path` typing didn't. `make_harness/prompt.py`, built on
  `prompt_toolkit` — the project's **first real UI dependency**, added
  deliberately: an interactive pop-up isn't feasible stdlib-only
  (`readline` doesn't exist on Windows). Falls back to plain `input()`
  for non-TTY stdin (piped input, tests, CI) with identical behavior to
  before — the picker is purely a typing aid, not part of the attachment
  logic in `mentions.py`. 8 new offline tests (54 total) drive the
  completer via `prompt_toolkit` `Document`s directly, no terminal
  needed. Verified live: `pixi run make-harness --version` and a piped
  `exit` both still work unchanged after adding the dependency.
- **Permission gate as a dropdown** (user-requested follow-up, same day):
  `policy.py`'s typed `y/n/a` prompt replaced with a four-way pop-up
  dropdown — `yes` (once) / `no` (deny once) / `always` (allow this tool
  for the rest of the session) / `deny` (new: permanently block this tool
  for the session — the symmetric counterpart to `always`, so a chatty
  tool can be silenced once instead of denied on every single call).
  Built by generalizing the `@path` picker mechanism:
  `make_harness/prompt.py` gained `ChoiceCompleter` (filters a fixed
  value/label list) and `make_chooser()`, returning an
  `ask(prompt_text, choices)` that opens the pop-up in a real terminal or
  falls back to a typed, re-prompting match otherwise — same TTY split
  as `make_input()`. `Policy` now tracks `always_allow` and `always_deny`
  per tool name; EOFError and KeyboardInterrupt during the prompt both
  deny safely, same as before.
  Verified: 19 new offline tests (73 total) — `ChoiceCompleter` filtering,
  `_match_choice`'s exact/prefix/ambiguous-prefix cases, the non-TTY
  fallback loop, and `Policy`'s four choices including that `always`/
  `deny` are remembered per-tool and never re-prompt. Live smoke: a real
  Groq session requesting two `write_file` calls, answering `always` on
  the first prompt — the second call executed with zero further prompts
  and `policy.always_allow == {"write_file"}`.

### [x] Stage 12 — Skill packages: `skills/<name>/SKILL.md`
User-requested 2026-07-20. Originally listed under Stage 10 as deferred
with "no new trigger information"; the trigger became real the moment
it was asked for directly.
- `make_harness/toolsets/skills.py`: `discover()` parses
  `skills/*/SKILL.md` files with `---\nname: ...\ndescription: ...\n---`
  frontmatter (regex-based — no YAML dependency for two key: value
  lines) plus a body; malformed files (no frontmatter block) are skipped
  rather than crashing startup. `skills_index()` formats `- name:
  description` lines. `load_skill(name)` is the `@tool`.
- Same progressive-disclosure shape as Stage 4 memory: `skills_index()`
  is injected into the system prompt at REPL startup (`cli.py`) so the
  agent knows what's available without spending a tool call to check;
  `load_skill` fetches one skill's full body on demand. `load_skill`
  added to `Policy.AUTO_ALLOW` — it only reads `skills/`, same
  read-only rationale as `read_memory`.
  `skills/commit-messages/SKILL.md` ships as the one bundled example —
  this repo's own atomic-commit and message-body conventions, genuinely
  useful rather than a placeholder, and doubles as the live-verified
  fixture.
- Verified: 8 new offline tests (81 total) — discovery, the folder-name
  fallback when `name:` is missing, malformed files skipped cleanly,
  index formatting, `load_skill` found/not-found, and a guard test that
  the bundled `commit-messages` skill itself stays discoverable. Live
  smoke: a real Groq session, given only the injected index (no skill
  name or path mentioned by the user), called
  `load_skill({"name": "commit-messages"})` unprompted and correctly
  summarized its message-body convention.

### [x] Stage 13 — Slash commands: `/clear`
User-requested 2026-07-20. `feedback_consolidated.md` §4 had explicitly
deferred a pluggable slash-command design with "worth designing
pluggably *if and when* the first slash command is added, not before" —
`/clear` is that first command, so the trigger is now real.
- `make_harness/commands.py`: a small registry mirroring `tools.py`'s
  `@tool` decorator — `@command` registers a function under its name;
  `run(text, messages, log)` dispatches, logs a single `command` event
  (`name`, `output`) for any recognized command, and returns a helpful
  `Unknown command: /x — available: ...` message (unlogged) otherwise.
  Adding a second command means writing one function, not another
  branch in `cli.py`.
- `clear(messages)` resets history to `[messages[0]]` — the system
  message already has the memory/skills index folded in (Stages 4/12),
  so nothing needs re-injecting, only the back-and-forth is dropped.
  Checked in `cli.py` before `@`-mention expansion, so `/clear` itself
  is never sent to the model or scanned for mentions.
- Verified: 6 new offline tests (87 total) — history reset, the
  `command` log event, trailing-argument tolerance (`/clear please`),
  unknown-command fallback (untouched messages, no log entry, lists
  what's available), and a bare `/` edge case. Live smoke: the real CLI
  as a subprocess — asked "what is 2+2", got `4`; `/clear`; asked
  whether it remembered the math question, got `No` (not just hidden,
  actually gone); confirmed exactly one `command` event with
  `name: clear` in the session's JSONL log.

### [x] Stage 14 — `llm.py` returns the model's `reasoning`
User-requested 2026-07-20, first piece of a 10-stage full-screen TUI
rewrite (Stages 14–23) adding collapsible reasoning blocks and a
scrollable transcript. Groq's `openai/gpt-oss-120b` already returns a
`reasoning` field in `message` alongside `content` — verified live in a
session log — but `LLMClient.complete()` discarded it entirely.
- `msg.get("reasoning")` added to `complete()`'s return dict, `None`
  when absent (model/backend-dependent — degrades gracefully). The
  salvage path's hand-built synthetic `raw` dict (Groq `tool_use_failed`
  recovery) has no `reasoning` key at all; `.get()` degrades to `None`
  there too rather than `KeyError`ing.
- Verified: 4 new offline tests (91 total, `tests/test_llm.py`) —
  reasoning present/absent, absent on a tool-call response, and the
  salvage-path degradation case (stubbing a `tool_use_failed` 400 end to
  end, not just `_salvage_tool_call()` in isolation like
  `test_llm_salvage.py` already does). Live smoke: real Groq call,
  `result["reasoning"]` populated with the actual chain-of-thought text.

### [x] Stage 15 — `loop.py` gains an `on_event` hook
`run_turn()` now takes an optional `on_event(kind, **fields)` kwarg. When
supplied, it's called at every point the function would otherwise
`print()` a live trace line (`tool_call`, `short_circuit`,
`tool_result` with `outcome="executed"|"denied"`), plus a `reasoning`
event once per step, unconditionally — even on steps with no reasoning
text (`text=None`) — so a consumer building a parallel `reasoning_events`
list gets exactly one entry per step, position-matchable against
assistant messages. When `on_event` is `None` (the default, and every
one of the 87 pre-existing call sites including `cli.py`'s), behavior is
byte-for-byte identical to before this stage: same prints, same return
contract, nothing new evaluated.
- This is the single, narrated exception to "Sync code only" and the
  event-bus rejection described in design principle 5 — one direct
  callback, not pub/sub.
- Verified: 7 new offline tests (98 total) — default path still prints
  (via `capsys`), supplying `on_event` suppresses those same prints
  entirely, the reasoning event fires once per step including the
  `text=None` case, exact event kinds/order/fields for a tool-call step
  (`reasoning` → `tool_call` → `tool_result` → `reasoning`), the
  short-circuit event, and a new `DenyAll` fake policy proving the
  denial path's event too (no prior test covered a denial). `ScriptedLLM`
  extended to pass through an optional `reasoning` fixture field,
  defaulting to `None` — the 91 tests already using it without that
  field are untouched. Live smoke: a real Groq call with a print-based
  `on_event`, confirming real reasoning text at both the tool-call step
  and the final-answer step, in the exact order
  `reasoning → tool_call → tool_result → reasoning`.

## Deliberately NOT built

- **Event bus** — considered and explicitly rejected (not just deferred).
  ChatGPT's review flagged this as highest priority; DeepSeek and a
  Nemotron synthesis of all reviews independently argued against it —
  pub/sub indirection actively fights this project's "understandable in an
  afternoon" goal, and nothing in the codebase today needs to *react* to
  an event mid-flight (every current consumer of "things that happened" —
  console output, the JSONL log — is a direct call, not a subscriber).
  Revisit only if a concrete subscriber use case shows up, not as an
  architecture-first move. (Update 2026-07-20: Stage 15 adds a single
  direct `on_event` callback from `run_turn()` so the TUI can react to
  tool calls/reasoning mid-turn instead of only after the fact via the
  JSONL log — this is one callback, not pub/sub with multiple
  subscribers, so the rejection of a *general* event bus still stands.
  See design principle 5.)
- Plugin system, middleware chain, state machine, workflow engine, async —
  still deferred, not rejected. The JSONL logger and the policy gate are
  the seams where these can bolt on later without a rewrite.
- Full tool-metadata schema (cost, parallel_safe, examples, tags) — no
  consumer exists; nothing here runs tools in parallel or schedules by
  cost.
- Multi-agent / DAG / MCP / Tree-of-Thought / Reflection — v3+ territory,
  no disagreement among any reviewer on this one.
