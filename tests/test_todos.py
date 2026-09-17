"""Tests for toolsets.todos — write_todos validation, the rendered plan
that goes into the <env> block, and its hand-written parameters schema."""

import pytest
from helpers import StubLog

from make_harness import commands, context
from make_harness.policy import Policy
from make_harness.tools import registry
from make_harness.toolsets import todos


@pytest.fixture(autouse=True)
def empty_plan():
    todos.clear()
    yield
    todos.clear()


PLAN = [
    {"content": "Read the parser", "status": "done"},
    {"content": "Fix the off-by-one", "status": "in_progress"},
    {"content": "Run the tests", "status": "pending"},
]


def test_write_replaces_the_list_and_returns_it_rendered():
    todos.write_todos([{"content": "old", "status": "pending"}])
    out = todos.write_todos(PLAN)
    assert out == "[x] Read the parser\n[~] Fix the off-by-one\n[ ] Run the tests"
    assert todos.render() == out
    assert [t["content"] for t in todos.TODOS] == ["Read the parser", "Fix the off-by-one", "Run the tests"]


def test_the_updated_plan_is_printed_for_the_user(capsys):
    todos.write_todos(PLAN)
    assert "[~] Fix the off-by-one" in capsys.readouterr().out


def test_an_empty_list_clears_the_plan():
    todos.write_todos(PLAN)
    assert todos.write_todos([]) == "Todo list cleared."
    assert todos.render() == ""


def test_a_json_encoded_array_is_accepted():
    # Small local models sometimes send the array as a string.
    assert todos.write_todos('[{"content": "a", "status": "pending"}]') == "[ ] a"


def test_extra_fields_are_dropped():
    todos.write_todos([{"content": "a", "status": "pending", "activeForm": "Doing a"}])
    assert todos.TODOS == [{"content": "a", "status": "pending"}]


@pytest.mark.parametrize(
    "bad,error",
    [
        ("not json", "Error: todos must be an array"),
        ({"content": "a", "status": "pending"}, "Error: todos must be an array"),
        (["just a string"], "Error: every todo needs a content string"),
        ([{"status": "pending"}], "Error: every todo needs a content string"),
        ([{"content": "a", "status": "blocked"}], "Error: status must be one of pending, in_progress, done; got 'blocked'"),
        ([{"content": "a", "status": "in_progress"}, {"content": "b", "status": "in_progress"}],
         "Error: 2 todos are in_progress"),
    ],
    ids=["unparseable-string", "object-not-array", "item-not-object", "no-content", "unknown-status", "two-in-progress"],
)
def test_invalid_lists_are_refused_and_the_plan_is_kept(bad, error):
    todos.write_todos(PLAN)
    assert todos.write_todos(bad).startswith(error)
    assert len(todos.TODOS) == 3


def test_schema_describes_an_array_of_objects():
    schema = next(s for s in registry.schemas() if s["function"]["name"] == "write_todos")
    parameters = schema["function"]["parameters"]
    assert parameters is todos.PARAMETERS
    assert parameters["properties"]["todos"]["type"] == "array"
    assert parameters["properties"]["todos"]["items"]["properties"]["status"]["enum"] == ["pending", "in_progress", "done"]


def test_plan_appears_in_the_env_block_before_the_change_reminder():
    todos.write_todos(PLAN)
    block = context.reminder("trunk", {"a.py": "modified"}, todos.render())
    assert "</env>\n<todos>\n[x] Read the parser\n[~] Fix the off-by-one\n[ ] Run the tests\n</todos>\n<system-reminder>" in block


def test_no_plan_means_no_todos_tag():
    assert "<todos>" not in context.reminder("trunk", None, todos.render())


def test_clear_command_also_clears_the_plan():
    todos.write_todos(PLAN)
    commands.run("/clear", [{"role": "system", "content": "s"}], commands.Context(log=StubLog()))
    assert todos.render() == ""


def test_write_todos_needs_no_permission():
    policy = Policy()
    policy._ask = lambda *a: pytest.fail("write_todos should not prompt")
    assert policy.check("write_todos", {"todos": []}) == "allow"
