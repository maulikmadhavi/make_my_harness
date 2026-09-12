"""Tests for policy.Policy — the four-way permission gate (yes/no/always/
deny), driven with a stubbed chooser so no terminal or stdin is touched."""

import pytest

from make_harness.policy import CHOICES, Policy


def _make_policy(responses):
    """A Policy whose chooser returns pre-scripted answers in order; a
    StopIteration means _ask was called more times than scripted."""
    policy = Policy()
    responses = iter(responses)
    policy._ask = lambda prompt_text, choices: next(responses)
    return policy


def test_choices_are_the_four_documented_options():
    assert [v for v, _ in CHOICES] == ["yes", "no", "always", "deny"]


def test_auto_allow_tools_skip_the_prompt():
    policy = _make_policy([])  # StopIteration if _ask is ever called
    assert policy.check("read_file", {}) == "allow"


@pytest.mark.parametrize(
    "scripted,expected",
    [
        (["yes", "yes"], ["allow", "allow"]),  # one-shot: asked again next time
        (["no", "yes"], ["deny", "allow"]),
        (["always"], ["allow", "allow"]),  # sticky: one answer covers both calls
        (["deny"], ["deny", "deny"]),
    ],
    ids=["yes-asks-again", "no-asks-again", "always-sticks", "deny-sticks"],
)
def test_verdicts_and_stickiness(scripted, expected):
    policy = _make_policy(scripted)
    assert [policy.check("write_file", {}) for _ in range(2)] == expected


def test_always_and_deny_are_tracked_independently_per_tool():
    policy = _make_policy(["always", "deny"])
    assert policy.check("write_file", {}) == "allow"
    assert policy.check("run_command", {}) == "deny"
    assert policy.check("write_file", {}) == "allow"  # still allowed
    assert policy.check("run_command", {}) == "deny"  # still denied


@pytest.mark.parametrize("exc", [EOFError, KeyboardInterrupt])
def test_interrupting_the_prompt_denies_safely(exc):
    policy = Policy()

    def ask(prompt_text, choices):
        raise exc

    policy._ask = ask
    assert policy.check("write_file", {}) == "deny"


def test_ask_is_the_only_io_seam(capsys):
    # A stubbed _ask means check() must not print anything itself --
    # the permission description used to be a separate print() call
    # that an _ask override couldn't have suppressed.
    policy = _make_policy(["yes"])
    policy.check("write_file", {"path": "x.py"})
    assert capsys.readouterr().out == ""


def test_ask_receives_the_full_prompt_context():
    captured = {}

    def ask(prompt_text, choices):
        captured.update(prompt_text=prompt_text, choices=choices)
        return "yes"

    policy = Policy()
    policy._ask = ask
    policy.check("write_file", {"path": "x.py"})
    assert "write_file" in captured["prompt_text"]
    assert "x.py" in captured["prompt_text"]
    assert "allow?" in captured["prompt_text"]
    assert captured["choices"] == CHOICES
