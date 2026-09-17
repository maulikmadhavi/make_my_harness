"""Tests for subagent.task — a fresh transcript, the withheld tools, the
shared permission gate and tagged log, and what comes back to the lead
agent when the subagent finishes, is denied, or runs out of steps."""

import pytest
from helpers import StubLog

import make_harness.cli  # noqa: F401 — registers the full toolset, as the REPL does
from make_harness import subagent
from make_harness.tools import registry


class ScriptedLLM:
    """Replays scripted responses and records every request it is sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def complete(self, messages, tools=None):
        self.requests.append({"messages": [dict(m) for m in messages], "tools": tools})
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return {"content": r.get("content"), "reasoning": None, "tool_calls": r.get("tool_calls", []), "usage": {}, "raw": r}


class Policy:
    def __init__(self, verdict="allow"):
        self.verdict = verdict
        self.checked = []

    def check(self, name, args):
        self.checked.append(name)
        return self.verdict


def _call(call_id, name, arguments="{}"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


@pytest.fixture
def runtime(monkeypatch):
    """Configure task with fresh stubs; returns a function that installs an
    LLM script and hands back (llm, policy, log)."""
    monkeypatch.setattr(subagent, "_runtime", {})

    def install(responses, verdict="allow"):
        llm, policy, log = ScriptedLLM(responses), Policy(verdict), StubLog()
        subagent.configure(llm, policy, log)
        return llm, policy, log

    return install


def test_task_outside_the_repl_is_a_clean_error(monkeypatch):
    monkeypatch.setattr(subagent, "_runtime", {})
    assert subagent.task("anything") == "Error: subagents are only available inside the REPL."


def test_starts_from_an_empty_transcript_and_returns_only_the_answer(runtime):
    llm, _, _ = runtime([{"content": "run_turn is defined in make_harness/loop.py:51."}])
    report = subagent.task("Where is run_turn defined?")
    assert report == "run_turn is defined in make_harness/loop.py:51."
    sent = llm.requests[0]["messages"]
    assert [m["role"] for m in sent] == ["system", "user"]
    assert sent[0]["content"].startswith("You are an exploration subagent")
    assert sent[1]["content"] == "Where is run_turn defined?"


def test_withheld_tools_are_never_offered(runtime):
    llm, _, _ = runtime([{"content": "done"}])
    subagent.task("look around")
    offered = {t["function"]["name"] for t in llm.requests[0]["tools"]}
    assert offered.isdisjoint(subagent.WITHHELD)
    assert {"read_file", "run_command", "load_skill"} <= offered
    assert "task" in {s["function"]["name"] for s in registry.schemas()}  # the lead agent keeps it


def test_its_tool_calls_go_through_the_shared_gate_and_a_tagged_log(runtime, tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("the answer is 42", encoding="utf-8")
    arguments = '{"path": "' + str(target).replace("\\", "\\\\") + '"}'
    llm, policy, log = runtime([
        {"tool_calls": [_call("c1", "read_file", arguments)]},
        {"content": "notes.txt says 42"},
    ])
    assert subagent.task("What does notes.txt say?") == "notes.txt says 42"
    assert policy.checked == ["read_file"]
    assert "the answer is 42" in llm.requests[1]["messages"][-1]["content"]  # it saw the result
    assert log.kinds()[0] == "subagent_start"
    assert log.kinds()[-1] == "subagent_done"
    assert all(fields.get("agent") == "subagent" for _, fields in log.events)


def test_its_trace_lines_are_indented_under_the_call(runtime, capsys):
    runtime([{"tool_calls": [_call("c1", "load_skill", '{"name": "nope"}')]}, {"content": "done"}])
    subagent.task("check skills")
    out = capsys.readouterr().out
    assert "  ⤷ subagent: check skills" in out
    assert "\n      → load_skill(" in out  # indent + the loop's own two spaces
    assert "  ⤶ subagent done" in out


def test_a_denied_call_is_reported_back(runtime):
    runtime([{"tool_calls": [_call("c1", "run_command", '{"command": "dir"}')]}], verdict="deny")
    assert subagent.task("list files") == "(the subagent stopped: the user denied one of its tool calls)"


def test_running_out_of_steps_returns_partial_findings(runtime, monkeypatch):
    monkeypatch.setattr(subagent, "MAX_STEPS", 2)
    runtime([
        {"content": "Found loop.py so far.", "tool_calls": [_call("c1", "load_skill", '{"name": "a"}')]},
        {"tool_calls": [_call("c2", "load_skill", '{"name": "b"}')]},
    ])
    report = subagent.task("trace everything")
    assert report.startswith("(the subagent stopped after 2 steps without finishing; its partial findings follow")
    assert report.endswith("\n\nFound loop.py so far.")


def test_running_out_of_steps_with_nothing_said(runtime, monkeypatch):
    monkeypatch.setattr(subagent, "MAX_STEPS", 1)
    runtime([{"tool_calls": [_call("c1", "load_skill", '{"name": "a"}')]}])
    assert subagent.task("trace everything") == "(the subagent stopped after 1 steps without finishing)"
