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


def test_numeric_and_unannotated_parameters_map_to_json_types():
    reg = Registry()

    @reg.tool
    def calc(count: int, ratio: float, flag: bool, label: str, mystery, opt=None) -> str:
        """Typed."""
        return "ok"

    parameters = reg.schemas()[0]["function"]["parameters"]
    assert parameters["properties"] == {
        "count": {"type": "integer"},
        "ratio": {"type": "number"},
        "flag": {"type": "boolean"},
        "label": {"type": "string"},
        "mystery": {"type": "string"},  # no annotation -> string
        "opt": {"type": "string"},
    }
    assert parameters["required"] == ["count", "ratio", "flag", "label", "mystery"]


def test_missing_docstring_gives_an_empty_description():
    reg = Registry()

    @reg.tool
    def undocumented() -> str:
        return "x"

    assert reg.schemas()[0]["function"]["description"] == ""


def test_decorator_returns_the_original_function():
    reg = Registry()

    def raw(x: str) -> str:
        """Raw."""
        return x.upper()

    assert reg.tool(raw) is raw
    assert raw("a") == "A"


def test_schemas_preserve_registration_order():
    reg = _make_registry()
    assert [s["function"]["name"] for s in reg.schemas()] == ["greet", "boom"]


def test_execute_result_is_always_a_string():
    reg = Registry()

    @reg.tool
    def number() -> int:
        """Returns an int."""
        return 42

    assert reg.execute("number", {}) == "42"
