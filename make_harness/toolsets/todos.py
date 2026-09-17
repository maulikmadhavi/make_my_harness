"""The plan for a multi-step task.

The agent writes it with write_todos; it lives here rather than in the
transcript, and context.reminder shows it back inside <todos> on every
request. That block — not a tool result from several turns ago, which
history.strip will have shortened — is where the agent reads where it is.
"""

import json

from make_harness.tools import tool
from make_harness.ui import dim

MARKS = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]"}

TODOS = []  # [{"content": str, "status": str}], replaced whole by write_todos

PARAMETERS = {
    "type": "object",
    "properties": {
        "todos": {
            "type": "array",
            "description": "The whole list, in order. It replaces the previous one.",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The task, e.g. 'Fix the parser'"},
                    "status": {"type": "string", "enum": list(MARKS)},
                },
                "required": ["content", "status"],
            },
        }
    },
    "required": ["todos"],
}


def render():
    return "\n".join(f"{MARKS[t['status']]} {t['content']}" for t in TODOS)


def clear():
    TODOS.clear()


def _check(todos):
    """The list as clean dicts, or an error string to hand back."""
    if isinstance(todos, str):  # small models sometimes send the array JSON-encoded
        try:
            todos = json.loads(todos)
        except json.JSONDecodeError:
            return "Error: todos must be an array of {content, status} objects."
    if not isinstance(todos, list):
        return "Error: todos must be an array of {content, status} objects."
    clean = []
    for item in todos:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            return "Error: every todo needs a content string and a status."
        if item.get("status") not in MARKS:
            return f"Error: status must be one of {', '.join(MARKS)}; got {item.get('status')!r}."
        clean.append({"content": item["content"], "status": item["status"]})
    active = sum(1 for t in clean if t["status"] == "in_progress")
    if active > 1:
        return f"Error: {active} todos are in_progress. Keep exactly one in_progress at a time."
    return clean


@tool(parameters=PARAMETERS)
def write_todos(todos: list) -> str:
    """Record the plan for a task with several steps, and update it as you go. Send the whole list every time: it replaces the previous one. Keep exactly one todo in_progress, and mark each one done as soon as it is finished. Skip this for single-step tasks."""
    clean = _check(todos)
    if isinstance(clean, str):
        return clean
    TODOS[:] = clean
    plan = render()
    if plan:
        print(dim("  " + plan.replace("\n", "\n  ")))
    return plan or "Todo list cleared."
