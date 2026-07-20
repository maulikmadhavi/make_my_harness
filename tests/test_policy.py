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


def test_ask_is_the_only_io_seam(capsys):
    # A stubbed _ask means check() must not print anything itself --
    # the permission description used to be a separate print() call
    # that a TUI override (Stage 20) couldn't have suppressed.
    policy = _make_policy(["yes"])
    policy.check("write_file", {"path": "x.py"})
    assert capsys.readouterr().out == ""


def test_ask_receives_the_full_prompt_context():
    captured = {}

    def ask(prompt_text, choices):
        captured["prompt_text"] = prompt_text
        captured["choices"] = choices
        return "yes"

    policy = Policy()
    policy._ask = ask
    policy.check("write_file", {"path": "x.py"})
    assert "write_file" in captured["prompt_text"]
    assert "x.py" in captured["prompt_text"]
    assert "allow?" in captured["prompt_text"]
    assert captured["choices"] == CHOICES
