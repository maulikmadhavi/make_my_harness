"""Permission gate: which tool calls run, which ask, which never run.

Rules decide first:
  - SHELL_RULES rate run_command per command. Read-only commands run without
    asking; destructive or network ones are blocked outright; everything
    else asks. A compound command (&&, ||, |, ;) is split outside quotes and
    its strictest part wins.
  - write_file / str_replace inside the project directory run without
    asking — except inside .git — and ask anywhere else.
  - AUTO_ALLOW tools run; every other tool asks.

A blocked call is never offered to the user: "always" can't unblock it.
Everything that asks prompts with four choices, selectable from a pop-up
dropdown in a real terminal (or typed in a plain fallback prompt otherwise):
  yes    — allow this one call
  no     — deny this one call
  always — allow this tool automatically for the rest of the session
  deny   — never allow this tool for the rest of the session (the
           permanent counterpart to "always")
A denial or a block is returned to the model as the tool result so it can
adapt instead of crashing.

_ask() is Policy's only I/O seam — everything printed or read lives
inside that one call, so a caller (or a test) can override it completely
by swapping self._ask, with no stray print() to worry about.
"""

import json
from fnmatch import fnmatchcase
from pathlib import Path

from make_harness.prompt import make_chooser
from make_harness.ui import yellow

CHOICES = [
    ("yes", "Yes — allow this call"),
    ("no", "No — deny this call"),
    ("always", "Always — allow this tool for the rest of the session"),
    ("deny", "Deny — never allow this tool for the rest of the session"),
]

# (pattern, verdict), matched against each lowercased part of a command. The
# last matching rule wins, so the catch-all comes first and exceptions after.
SHELL_RULES = [
    ("*", "ask"),
    # Read-only, in POSIX and Windows spellings.
    *((pattern, "allow") for pattern in (
        "ls", "ls *", "dir", "dir *", "pwd", "cd", "cd *", "echo *", "tree", "tree *",
        "cat *", "type *", "head *", "tail *", "more *", "wc *", "sort *", "uniq *",
        "grep *", "rg *", "findstr *", "find *", "where *", "which *", "date",
        "git status*", "git diff*", "git log*", "git show*", "git branch", "git ls-files*",
        "pytest*", "python -m pytest*", "pixi run test*",
    )),
    # find is read-only until it acts on what it finds.
    ("find * -delete*", "ask"),
    ("find * -exec*", "ask"),
    # Never, even if the user would say yes: destroys files or history, or
    # reaches the network.
    *((pattern, "deny") for pattern in (
        "rm *", "rmdir *", "del *", "erase *", "rd *", "remove-item*", "format *",
        "sudo *", "chmod *", "chown *",
        "curl *", "wget *", "invoke-webrequest*",
        "git push*", "git reset --hard*", "git clean*",
    )),
]

# Output redirection can write files, and $, % and backticks expand variables
# or run commands — `echo %API_KEY%` would send a secret to the model — so a
# part containing any of these is never allowed without asking.
_NOT_READ_ONLY = (">", "$", "%", "`")

WRITE_TOOLS = {"write_file", "str_replace"}


def split_command(command):
    """Split on &&, ||, |, ; and newlines — but not inside quotes, where
    `grep "a|b"` keeps its pattern whole."""
    parts, current, quote = [], [], None
    i = 0
    while i < len(command):
        char = command[i]
        if quote:
            current.append(char)
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            current.append(char)
        elif char in "&|;\n":
            parts.append("".join(current))
            current = []
            while i + 1 < len(command) and command[i + 1] in "&|":
                i += 1
        else:
            current.append(char)
        i += 1
    parts.append("".join(current))
    return [" ".join(part.split()) for part in parts if part.strip()]


def rate_command(command):
    """allow, ask or deny for a whole shell command: the strictest of its parts."""
    verdicts = set()
    for part in split_command(command or ""):
        verdict = "ask"
        for pattern, rule in SHELL_RULES:
            if fnmatchcase(part.lower(), pattern):
                verdict = rule
        if verdict == "allow" and any(c in part for c in _NOT_READ_ONLY):
            verdict = "ask"
        verdicts.add(verdict)
    for strictest in ("deny", "ask"):
        if strictest in verdicts:
            return strictest
    return "allow" if verdicts else "ask"


def rate_write(path):
    """allow for a path inside the project (the launch directory) but outside
    .git, ask for anything else."""
    if not path:
        return "ask"
    project = Path.cwd().resolve()
    target = Path(path).resolve()
    if not target.is_relative_to(project):
        return "ask"
    return "ask" if ".git" in target.relative_to(project).parts else "allow"


class Policy:
    # save_memory/read_memory only touch the memory/ directory; load_skill
    # only reads skill files; write_todos only changes the in-memory plan;
    # task only starts a subagent, whose own tool calls come through here.
    AUTO_ALLOW = {"read_file", "web_search", "save_memory", "read_memory", "load_skill", "write_todos", "task"}

    def __init__(self):
        self.always_allow = set()
        self.always_deny = set()
        self._ask = make_chooser()

    def rule(self, name, args):
        """What the rules say before anyone is asked: allow, ask or deny."""
        if name == "run_command":
            return rate_command(args.get("command"))
        if name in WRITE_TOOLS:
            return rate_write(args.get("path"))
        return "allow" if name in self.AUTO_ALLOW else "ask"

    def check(self, name, args):
        """allow, deny (the user said no), or block (a rule said never)."""
        verdict = self.rule(name, args)
        if verdict == "deny":
            return "block"
        if verdict == "allow" or name in self.always_allow:
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
