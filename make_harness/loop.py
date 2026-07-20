"""The agent loop: call the LLM, execute requested tools, feed results back.

One run_turn() call handles one user request end to end, up to max_steps
LLM round-trips. Every request, response, tool call and result is logged.
"""

import json


SHORT_CIRCUIT_RESULT = (
    "[not executed: identical to your previous call — the result would be "
    "unchanged; adjust your arguments or approach]"
)


def run_turn(llm, registry, policy, log, messages, max_steps=15):
    last_executed = None  # (name, canonical args) of the last call actually run
    for step in range(max_steps):
        log.event("llm_request", step=step, messages=messages)
        resp = llm.complete(messages, tools=registry.schemas() or None)
        log.event("llm_response", step=step, raw=resp["raw"])

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
                args = None
            if args is None:
                result = f"Error: unparseable tool arguments: {tc['function']['arguments']!r}"
            else:
                print(f"  → {name}({json.dumps(args, ensure_ascii=False)[:200]})")
                log.event("tool_call", step=step, tool=name, args=args, id=tc["id"])
                signature = (name, json.dumps(args, sort_keys=True))
                if signature == last_executed:
                    # The model repeated its previous call verbatim — don't
                    # re-execute; nudge it instead. The nudge must BE the tool
                    # result (not a floating system message) so the
                    # tool_call/tool pairing the API requires stays intact.
                    result = SHORT_CIRCUIT_RESULT
                    print("  ← short-circuited (identical repeat)")
                    log.event("short_circuit", step=step, tool=name, id=tc["id"])
                else:
                    verdict = "deny" if interrupted else policy.check(name, args)
                    log.event("permission", step=step, tool=name, verdict=verdict)
                    if verdict == "allow":
                        result = registry.execute(name, args)
                        last_executed = signature
                        print(f"  ← {len(result)} chars")
                    else:
                        result = "Denied by user."
                        print("  ← denied")
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
