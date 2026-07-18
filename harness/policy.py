"""Permission gate: console approval before side-effecting tools run.

Read-only tools are auto-allowed. Everything else prompts:
y = allow once, n = deny, a = always allow this tool for the session.
A denial is returned to the model as the tool result so it can adapt
instead of crashing.
"""

import json


class Policy:
    AUTO_ALLOW = {"read_file"}

    def __init__(self):
        self.always = set()

    def check(self, name, args):
        if name in self.AUTO_ALLOW or name in self.always:
            return "allow"
        print(f"  [permission] {name}({json.dumps(args, ensure_ascii=False)[:200]})")
        while True:
            try:
                answer = input("  allow? y = once / n = deny / a = always: ").strip().lower()
            except EOFError:
                return "deny"
            if answer in ("y", "yes"):
                return "allow"
            if answer in ("n", "no"):
                return "deny"
            if answer in ("a", "always"):
                self.always.add(name)
                return "allow"
