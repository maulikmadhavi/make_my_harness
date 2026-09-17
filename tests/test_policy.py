"""Tests for policy — the command and path rules, and the four-way
permission gate (yes/no/always/deny), driven with a stubbed chooser so no
terminal or stdin is touched."""

import pytest

from make_harness.policy import CHOICES, Policy, rate_command, rate_write, split_command


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
    policy.check("run_command", {"command": "make build"})
    assert capsys.readouterr().out == ""


def test_ask_receives_the_full_prompt_context():
    captured = {}

    def ask(prompt_text, choices):
        captured.update(prompt_text=prompt_text, choices=choices)
        return "yes"

    policy = Policy()
    policy._ask = ask
    policy.check("run_command", {"command": "make build"})
    assert "run_command" in captured["prompt_text"]
    assert "make build" in captured["prompt_text"]
    assert "allow?" in captured["prompt_text"]
    assert captured["choices"] == CHOICES


# --- rules -------------------------------------------------------------------

@pytest.mark.parametrize(
    "command,expected",
    [
        ('grep -rn "a|b" src', ['grep -rn "a|b" src']),
        ("git status && git diff", ["git status", "git diff"]),
        ("dir | findstr py; echo done", ["dir", "findstr py", "echo done"]),
        ("ls\npwd", ["ls", "pwd"]),
        ("echo 'x;y'  ||  rm   -rf  z", ["echo 'x;y'", "rm -rf z"]),
        ("", []),
    ],
    ids=["pipe-inside-quotes", "and", "pipe-and-semicolon", "newline", "or-and-spacing", "empty"],
)
def test_split_command(command, expected):
    assert split_command(command) == expected


@pytest.mark.parametrize(
    "command,expected",
    [
        ("ls -la", "allow"),
        ("dir /s *.py", "allow"),
        ("type pixi.toml", "allow"),
        ("git log --oneline -5", "allow"),
        ('grep -rn "def run_turn" make_harness', "allow"),
        ("GIT STATUS", "allow"),  # Windows commands are case-insensitive
        ("git status && git diff", "allow"),
        ("python gen.py", "ask"),
        ("pip install requests", "ask"),
        ("git status && make build", "ask"),
        ("find . -name '*.pyc' -delete", "ask"),
        ("echo hello > notes.txt", "ask"),
        ("echo %API_KEY%", "ask"),
        ("echo $HOME", "ask"),
        ("cat `which python`", "ask"),
        ("rm -rf build", "deny"),
        ("del /q *.log", "deny"),
        ("curl https://example.com", "deny"),
        ("git push origin master", "deny"),
        ("git reset --hard HEAD~1", "deny"),
        ("ls && rm -rf /", "deny"),  # the strictest part wins
        ("", "ask"),
    ],
)
def test_rate_command(command, expected):
    assert rate_command(command) == expected


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.mark.parametrize(
    "path,expected",
    [
        ("notes.txt", "allow"),
        ("src/deep/new.py", "allow"),
        ("./src/../README.md", "allow"),
        ("../outside.txt", "ask"),
        (".git/config", "ask"),
        ("", "ask"),
    ],
)
def test_rate_write(project, path, expected):
    assert rate_write(path) == expected


def test_rate_write_absolute_paths(project, tmp_path):
    assert rate_write(str(project / "a.py")) == "allow"
    assert rate_write(str(tmp_path.parent / "elsewhere.py")) == "ask"


def test_writes_inside_the_project_skip_the_prompt(project):
    policy = _make_policy([])  # StopIteration if _ask is ever called
    assert policy.check("write_file", {"path": "a.py", "content": "x"}) == "allow"
    assert policy.check("str_replace", {"path": "a.py", "old_str": "x", "new_str": "y"}) == "allow"


def test_writes_outside_the_project_ask(project):
    policy = _make_policy(["no"])
    assert policy.check("write_file", {"path": "../a.py", "content": "x"}) == "deny"


def test_read_only_commands_skip_the_prompt():
    policy = _make_policy([])
    assert policy.check("run_command", {"command": "git diff --stat"}) == "allow"


def test_a_blocked_command_is_never_offered_to_the_user_even_after_always():
    policy = _make_policy(["always"])
    assert policy.check("run_command", {"command": "make build"}) == "allow"
    assert policy.check("run_command", {"command": "python other.py"}) == "allow"  # always sticks
    assert policy.check("run_command", {"command": "rm -rf build"}) == "block"
