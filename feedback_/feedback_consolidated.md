# Consolidated External Feedback — Reflection

Four documents in this folder (`feedback_chatgpt.md`, `feedback_deepseek.md`,
`feedback_gemini.md`, `feedback_summary.md` from Nemotron) review
`make_harness`. All three AI reviewers responded to the **README
description** pasted into the chat, not the actual source — so this
consolidation fact-checks every claim against the real code in
`make_harness/` as of Stage 6, and separates "already done," "real gap,"
and "not worth it" accordingly.

## 1. Already shipped — the reviewers didn't have the code

- **Permission gate** (all four suggested this from scratch): already fully
  built. `policy.py`'s `Policy.check()` auto-allows read-only tools, prompts
  y/n/a for the rest, and `loop.py:36-52` ends the turn on denial instead of
  letting the model retry variants — a real failure mode hit and fixed live
  during Stage 2.
- **Repair/fallback parser for malformed tool calls** (ChatGPT "absolutely
  critical," DeepSeek "doubling down"): partially exists. `llm.py`'s
  `_salvage_tool_call()` recovers the intended call from Groq's
  `tool_use_failed` 400 error body, with a temperature-escalation retry as
  a second fallback. Narrower than what they describe (Groq-specific, not a
  generic brace-extraction repair) — see gap #4 below.
- **Memory "wastes an LLM turn to retrieve" concern** (Gemini): already
  solved differently. `toolsets/memory.py`'s `memory_index()` is injected
  straight into the system prompt at startup, so the model sees what it
  remembers without spending a tool call just to check. `read_memory` is
  only needed to fetch full content once something looks relevant.
- **Full audit trail** (all four): `log.py`'s `RunLog` writes one JSONL
  event per request/response/tool-call/tool-result/permission-verdict —
  already the "session.json / tool_calls.json / llm_requests.json" idea
  ChatGPT describes, just unified into one append-only file per session.
- **Token-budget context compaction**: built in Stage 5 (`context.py`),
  not mentioned as existing by any reviewer since it's not in the README's
  tool list.
- **Installable CLI / pip tarball**: built in Stage 6, likewise unknown to
  the reviewers.

## 2. Where the reviewers disagree, and my call

ChatGPT's top priority is an **Event Bus** ("everything emits events... now
tracing/logging/plugins/UI become independent"). DeepSeek and the Nemotron
summary explicitly reject this: *"An Event Bus introduces publish/subscribe
indirection that makes debugging a nightmare for beginners... do NOT add
an Event Bus."*

**I side with DeepSeek/Nemotron.** This project's own `plan.md` already
states the same reasoning for other subsystems ("Deliberately NOT built:
Event bus, plugin system, middleware chain... The JSONL logger and the
policy gate are the seams where these can bolt on later without a
rewrite"). The JSONL log already gives full after-the-fact observability
without needing pub/sub to produce it, and nothing in this codebase
currently *needs* to react to an event mid-flight — every consumer so far
(printing to console, writing to the log) is a direct call, not a
subscriber. Add an event bus when something concrete needs to subscribe,
not before.

## 3. Genuine, verified gaps

Checked directly against current source, not inferred from the reviews:

1. **No loop short-circuit for repeated identical tool calls** (Gemini).
   Distinct from the Stage 2 fix, which only stops *denied* calls from
   being retried. Nothing today stops the model from calling
   `read_file("x.py")` five times in a row within the same turn if it gets
   confused — it'll burn steps until `max_steps=15` hits. Real gap.
2. **Truncation drops the tail, not the head** (Gemini). Confirmed in
   `toolsets/shell.py:19-20`: `out[:MAX_OUTPUT] + "[truncated N chars]"` —
   keeps the *first* 10k chars, drops the rest. Same pattern in
   `toolsets/web.py`. This is backwards for shell/build output, where the
   actual error is usually at the very end. Head+tail truncation (keep
   both ends) is a concrete, low-risk improvement.
3. **No fallback for backends without native tool-calling** (Gemini).
   Real, and not new — the seven AI plan documents that designed this
   project originally (`plan_*.md`, since removed from the repo root) all
   proposed a hybrid adapter, and the build plan explicitly deferred it:
   *"native tool calling only — no text parsing... hybrid fallback
   deferred."* Still deferred, still a real limitation for anyone pointing
   this at a small local model without OpenAI-style tool calling.
4. **Tool-argument JSON repair, distinct from Groq salvage** (ChatGPT/
   DeepSeek). `loop.py:27-30` already catches `JSONDecodeError` and returns
   a clean error instead of crashing, but doesn't attempt to repair the
   string first (e.g. extract the outermost `{...}` before giving up). The
   existing salvage in `llm.py` only fires on Groq's specific 400 error
   shape — a different code path.
5. **No `Session`/context object** (ChatGPT/DeepSeek/Nemotron all raised
   this). Mild win today — `run_turn(llm, registry, policy, log, messages,
   max_steps=15)` is only 5 positional args, not yet unwieldy. Becomes a
   stronger case as soon as gap #1 needs a place to keep
   `last_action_signature` across the loop.

## 4. Explicitly not doing, and why

- **Event Bus** — see §2.
- **Full tool-metadata schema** (cost, parallel_safe, examples, tags —
  ChatGPT): no consumer exists for any of these fields; nothing in this
  harness runs tools in parallel or schedules by cost. Speculative.
- **Multi-agent / DAG / MCP / Tree-of-Thought / Reflection** — all four
  reviewers independently agree this is v3+ territory. No disagreement to
  adjudicate; not revisiting until the single-agent core has all of
  Stage 7–9 done.
- **YAML/TOML config file** (DeepSeek, Nemotron) — there is exactly one
  provider (`GroqChatModel`). A config file to *select between providers*
  has nothing to select between yet; building it now is the config
  equivalent of a premature abstraction. Revisit alongside Stage 8 (local
  model support), once there's a second real backend to choose from.
- **Slash commands as a plugin system** (ChatGPT/DeepSeek) — there are no
  slash commands in this REPL at all yet (only `exit`/`quit`). Nothing to
  refactor. Worth designing pluggably *if and when* the first slash command
  is added, not before.

## 5. Gaps none of the four reviewers could see

Found by reading the actual repo, since none of them had access to it:

- **No `LICENSE` file.** For a repo described as "open-source," this is a
  real, concrete gap — technically nobody can safely fork or reuse it
  without one.
- **No `tests/` directory anywhere.** Every verification claim in this
  project's `plan.md` ("Verified: ...") was a live, manual test run during
  development. There is zero automated regression coverage — a real risk
  now that the project is packaged and others might depend on it.
- **No CI.** No `.github/workflows`; nothing runs on push.
- **`stream` parameter is inert.** `GroqChatModel.chat(..., stream=False)`
  in `llm_providers.py` accepts a `stream` argument, but `LLMClient` always
  passes `False` and the response parsing assumes one JSON blob, not SSE
  chunks. It looks like streaming support exists; it doesn't. Worth noting
  explicitly so nobody assumes otherwise from reading the signature.

## Bottom line

The four reviews, taken together with fresh eyes on the actual code, split
cleanly into: things already built (ignore the advice, it's done), one real
architectural disagreement (event bus — reject it, for reasons this
project already committed to in writing), five concrete, verified gaps
worth closing, and a handful of suggestions that are correct in general but
premature for this codebase specifically. See `plan.md` (Stages 7–10) for
what that turns into as actual work.

## Revisit (second pass, 2026-07-19)

A second model pass over this document and the resulting roadmap confirmed
the big calls (event-bus rejection, trigger-gated deferrals, the five
gaps) and amended four things — all folded into `plan.md`:

1. **The short-circuit design as first written was a bug.** "Inject a
   system nudge instead of executing" would leave a `tool_call` id with no
   `role:"tool"` response, which fails the next API request. The nudge
   must *be* the synthetic tool result — the same pairing rule the
   Stage 2 deny path already honors. Gemini's floating system-message
   sketch has the same flaw.
2. **The default model changed under the docs.** `llm_providers.py` now
   defaults to `openai/gpt-oss-120b`; README banners, older plan notes,
   and the salvage-regex framing still reference `llama-3.3-70b-versatile`.
   Same "docs drifted from code" category as the inert `stream` param in
   §5. The llama-specific salvage stays (harmless — only fires on
   `tool_use_failed`), and live verifications that depend on llama's
   misbehavior may no longer reproduce.
3. **Hygiene reordered before hardening.** Per the repo's own
   karpathy-guidelines, the hardening changes should be built test-first —
   they're all deterministic with a stub LLM, unlike coaxing a live model
   into repeating itself. LICENSE is also a five-minute task blocking
   legal reuse of an already-published repo; it shouldn't sit behind two
   engineering stages. Stages renumbered: 7 = hygiene, 8 = hardening,
   9 = dual-path.
4. **The dual-path stage has an unstated scope dependency.** During
   Stage 0 the explicit decision was "Ollama is not in scope of this
   project"; the fallback path is unverifiable without a backend that
   lacks native tool calling, so starting that stage means consciously
   reversing that decision. Now stated in the stage itself.

One sharpening of the event-bus argument: the JSONL log already *is* an
event stream — append-only, typed, replayable. A future subscriber can
tail `logs/*.jsonl` without any runtime change, which makes the bus not
just rejected but redundant.
