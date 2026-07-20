"""Tests for policy.Policy — the four-way permission gate (yes/no/always/
deny), driven with a stubbed chooser so no terminal or stdin is touched."""

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


def test_yes_allows_once_and_asks_again_next_time():
    policy = _make_policy(["yes", "yes"])
    assert policy.check("write_file", {}) == "allow"
    assert policy.check("write_file", {}) == "allow"


def test_no_denies_once_and_asks_again_next_time():
    policy = _make_policy(["no", "yes"])
    assert policy.check("write_file", {}) == "deny"
    assert policy.check("write_file", {}) == "allow"


def test_always_allows_without_asking_again():
    policy = _make_policy(["always"])  # only one scripted answer
    assert policy.check("write_file", {}) == "allow"
    assert policy.check("write_file", {}) == "allow"


def test_deny_blocks_without_asking_again():
    policy = _make_policy(["deny"])  # only one scripted answer
    assert policy.check("run_command", {}) == "deny"
    assert policy.check("run_command", {}) == "deny"


def test_always_and_deny_are_tracked_independently_per_tool():
    policy = _make_policy(["always", "deny"])
    assert policy.check("write_file", {}) == "allow"
    assert policy.check("run_command", {}) == "deny"
    assert policy.check("write_file", {}) == "allow"  # still allowed
    assert policy.check("run_command", {}) == "deny"  # still denied


def test_eof_and_keyboard_interrupt_deny_safely():
    def _raise(exc):
        def ask(prompt_text, choices):
            raise exc

        return ask

    for exc in (EOFError, KeyboardInterrupt):
        policy = Policy()
        policy._ask = _raise(exc)
        assert policy.check("write_file", {}) == "deny"
