"""Permission gate: console approval before side-effecting tools run.

Read-only tools are auto-allowed. Everything else prompts with four
choices, selectable from a pop-up dropdown in a real terminal (or typed
in a plain fallback prompt otherwise):
  yes    — allow this one call
  no     — deny this one call
  always — allow this tool automatically for the rest of the session
  deny   — never allow this tool for the rest of the session (the
           permanent counterpart to "always")
A denial — one-off or permanent — is returned to the model as the tool
result so it can adapt instead of crashing.

_ask() is Policy's only I/O seam — everything printed or read lives
inside that one call, so a caller (the TUI, Stage 20) can override it
completely by swapping self._ask, with no risk of a stray print()
corrupting a full-screen render.
"""

import json

from make_harness.prompt import make_chooser
from make_harness.ui import yellow

CHOICES = [
    ("yes", "Yes — allow this call"),
    ("no", "No — deny this call"),
    ("always", "Always — allow this tool for the rest of the session"),
    ("deny", "Deny — never allow this tool for the rest of the session"),
]


class Policy:
    # save_memory/read_memory only touch the memory/ directory; load_skill
    # only reads from skills/.
    AUTO_ALLOW = {"read_file", "web_search", "save_memory", "read_memory", "load_skill"}

    def __init__(self):
        self.always_allow = set()
        self.always_deny = set()
        self._ask = make_chooser()

    def check(self, name, args):
        if name in self.AUTO_ALLOW or name in self.always_allow:
            return "allow"
        if name in self.always_deny:
            return "deny"
        prompt_text = yellow(
            f"  [permission] {name}({json.dumps(args, ensure_ascii=False)[:200]})\n  allow? "
        )
        try:
            choice = self._ask(prompt_text, CHOICES)
        except (EOFError, KeyboardInterrupt):
            return "deny"
        if choice == "always":
            self.always_allow.add(name)
            return "allow"
        if choice == "deny":
            self.always_deny.add(name)
            return "deny"
        return "allow" if choice == "yes" else "deny"
