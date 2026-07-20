"""Tests for tools.Registry — schema generation and the execute error
path (tool errors must come back as text results, never crash the loop)."""

from make_harness.tools import Registry


def _make_registry():
    reg = Registry()

    @reg.tool
    def greet(name: str, excited: bool = False) -> str:
        """Say hello."""
        return f"Hello {name}" + ("!" if excited else "")

    @reg.tool
    def boom() -> str:
        """Always fails."""
        raise ValueError("kaboom")

    return reg


def test_execute_success():
    reg = _make_registry()
    assert reg.execute("greet", {"name": "Maulik"}) == "Hello Maulik"


def test_execute_unknown_tool():
    reg = _make_registry()
    assert reg.execute("nope", {}) == "Error: unknown tool 'nope'"


def test_execute_tool_exception_becomes_error_string():
    reg = _make_registry()
    assert reg.execute("boom", {}) == "Error in boom: ValueError: kaboom"


def test_execute_wrong_arguments_do_not_crash():
    reg = _make_registry()
    assert reg.execute("greet", {"wrong_arg": 1}).startswith("Error in greet: TypeError")


def test_schema_from_signature_and_docstring():
    reg = _make_registry()
    schema = reg.schemas()[0]["function"]
    assert schema["name"] == "greet"
    assert schema["description"] == "Say hello."
    assert schema["parameters"]["properties"] == {
        "name": {"type": "string"},
        "excited": {"type": "boolean"},
    }
    assert schema["parameters"]["required"] == ["name"]
