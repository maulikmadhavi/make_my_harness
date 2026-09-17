"""The agent loop: call the LLM, execute requested tools, feed results back.

One run_turn() call handles one user request end to end, up to max_steps
LLM round-trips. Every request, response, tool call and result is logged,
and a one-line trace of each tool call is printed for the REPL.
"""

import json

from make_harness import history
from make_harness.context import with_reminder
from make_harness.ui import dim, yellow


def _repair_args(arguments):
    """Best-effort repair of tool-call arguments that didn't parse as JSON:
    extract the outermost {...} (models sometimes wrap the object in prose
    or tags). Returns a dict or None.

    Distinct from llm.py's _salvage_tool_call, which recovers whole calls
    from Groq's tool_use_failed error body — this repairs arguments of a
    call that the API accepted.
    """
    start, end = arguments.find("{"), arguments.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(arguments[start:end + 1])
    except json.JSONDecodeError:
        return None


SHORT_CIRCUIT_RESULT = (
    "[not executed: identical to your previous call — the result would be "
    "unchanged; adjust your arguments or approach]"
)
DENIED_RESULT = "Denied by user."


def _usage_line(usage):
    """'1234 in · 56 out · 800 cached' — the parts the server reported."""
    parts = [
        f"{usage[key]} {label}"
        for key, label in (("prompt_tokens", "in"), ("completion_tokens", "out"), ("cached_tokens", "cached"))
        if usage.get(key)
    ]
    return "  tokens: " + " · ".join(parts) if parts else None


def run_turn(llm, registry, policy, log, messages, max_steps=15, reminder=None):
    """`reminder`, when given, is called before every request and returns
    the block context.with_reminder puts at the end of what is sent — it is
    never added to `messages` itself."""
    last_executed = None  # (name, canonical args) of the last call actually run
    for step in range(max_steps):
        if dropped := history.fit(messages):
            print(yellow(f"  dropped {dropped} old tool result(s) to fit the context window"))
            log.event("context_fit", step=step, dropped=dropped)
        request = with_reminder(messages, reminder()) if reminder else messages
        log.event("llm_request", step=step, messages=request)
        resp = llm.complete(request, tools=registry.schemas() or None)
        log.event("llm_response", step=step, raw=resp["raw"])
        if line := _usage_line(resp.get("usage") or {}):
            print(dim(line))

        if not resp["tool_calls"]:
            messages.append({"role": "assistant", "content": resp["content"] or ""})
            log.event("done", answer=resp["content"])
            return resp["content"]

        messages.append(
            {"role": "assistant", "content": resp["content"], "tool_calls": resp["tool_calls"]}
        )
        interrupted = False
        for tc in resp["tool_calls"]:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = _repair_args(tc["function"]["arguments"])
                if args is not None:
                    log.event(
                        "args_repaired",
                        step=step,
                        tool=name,
                        raw=tc["function"]["arguments"][:500],
                    )
            if args is None:
                result = f"Error: unparseable tool arguments: {tc['function']['arguments']!r}"
            else:
                print(dim(f"  → {name}({json.dumps(args, ensure_ascii=False)[:200]})"))
                log.event("tool_call", step=step, tool=name, args=args, id=tc["id"])
                signature = (name, json.dumps(args, sort_keys=True))
                if signature == last_executed:
                    # The model repeated its previous call verbatim — don't
                    # re-execute; nudge it instead. The nudge must BE the tool
                    # result (not a floating system message) so the
                    # tool_call/tool pairing the API requires stays intact.
                    result = SHORT_CIRCUIT_RESULT
                    print(yellow("  ← short-circuited (identical repeat)"))
                    log.event("short_circuit", step=step, tool=name, id=tc["id"])
                else:
                    verdict = "deny" if interrupted else policy.check(name, args)
                    log.event("permission", step=step, tool=name, verdict=verdict)
                    if verdict == "allow":
                        result = registry.execute(name, args)
                        last_executed = signature
                        print(dim(f"  ← {len(result)} chars"))
                    else:
                        result = DENIED_RESULT
                        print(yellow("  ← denied"))
                        interrupted = True
            log.event("tool_result", step=step, tool=name, id=tc["id"], result=result[:2000])
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        # A denial hands control back to the user instead of letting the
        # model retry variants of the rejected call.
        if interrupted:
            log.event("turn_interrupted", step=step)
            return "[tool call denied — tell me how to proceed]"

    log.event("max_steps", steps=max_steps)
    return f"[stopped: reached {max_steps} steps without a final answer]"
