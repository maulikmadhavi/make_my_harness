"""The agent loop: call the LLM, execute requested tools, feed results back.

One run_turn() call handles one user request end to end, up to max_steps
LLM round-trips. Every request, response, tool call and result is logged.
"""

import json


def run_turn(llm, registry, log, messages, max_steps=15):
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
                result = registry.execute(name, args)
                print(f"  ← {len(result)} chars")
            log.event("tool_result", step=step, tool=name, id=tc["id"], result=result[:2000])
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

    log.event("max_steps", steps=max_steps)
    return f"[stopped: reached {max_steps} steps without a final answer]"
