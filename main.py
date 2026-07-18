"""Interactive REPL entry point for the harness."""

from harness.llm import LLMClient
from harness.log import RunLog

SYSTEM_PROMPT = "You are a helpful assistant running in a minimal local harness."


def main():
    llm = LLMClient()
    log = RunLog()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"harness REPL — {llm.model} — logging to {log.path}")
    print("type 'exit' or Ctrl+C to quit")

    while True:
        try:
            user = input("\nyou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user.lower() in ("exit", "quit"):
            break

        messages.append({"role": "user", "content": user})
        log.event("llm_request", messages=messages)
        try:
            resp = llm.complete(messages)
        except Exception as e:
            log.event("error", error=f"{type(e).__name__}: {e}")
            print(f"[error] {e}")
            messages.pop()
            continue
        log.event("llm_response", raw=resp["raw"])
        messages.append({"role": "assistant", "content": resp["content"]})
        print(f"\nagent > {resp['content']}")


if __name__ == "__main__":
    main()
