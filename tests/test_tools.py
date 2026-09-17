"""Tests for tools.Registry — schema generation and the execute error
path (tool errors must come back as text results, never crash the loop)."""

import pytest

from make_harness.tools import Registry


@pytest.fixture
def reg():
    """A registry holding one working tool and one that always raises."""
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


@pytest.mark.parametrize(
    "name,args,expected",
    [
        ("greet", {"name": "Maulik"}, "Hello Maulik"),
        ("nope", {}, "Error: unknown tool 'nope'"),
        ("boom", {}, "Error in boom: ValueError: kaboom"),
    ],
    ids=["success", "unknown-tool", "tool-raises"],
)
def test_execute(reg, name, args, expected):
    assert reg.execute(name, args) == expected


def test_execute_wrong_arguments_do_not_crash(reg):
    assert reg.execute("greet", {"wrong_arg": 1}).startswith("Error in greet: TypeError")


def test_execute_result_is_always_a_string():
    reg = Registry()

    @reg.tool
    def number() -> int:
        """Returns an int."""
        return 42

    assert reg.execute("number", {}) == "42"


def test_schema_from_signature_and_docstring(reg):
    schema = reg.schemas()[0]["function"]
    assert schema["name"] == "greet"
    assert schema["description"] == "Say hello."
    assert schema["parameters"]["properties"] == {
        "name": {"type": "string"},
        "excited": {"type": "boolean"},
    }
    assert schema["parameters"]["required"] == ["name"]


def test_schemas_preserve_registration_order(reg):
    assert [s["function"]["name"] for s in reg.schemas()] == ["greet", "boom"]


def test_annotations_map_to_json_types_and_defaults_drop_out_of_required():
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


def test_explicit_parameters_replace_the_generated_schema():
    reg = Registry()
    parameters = {
        "type": "object",
        "properties": {"items": {"type": "array", "items": {"type": "string"}}},
        "required": ["items"],
    }

    @reg.tool(parameters=parameters)
    def count(items: list) -> str:
        """Counts."""
        return str(len(items))

    schema = reg.schemas()[0]["function"]
    assert schema["parameters"] == parameters
    assert schema["description"] == "Counts."
    assert reg.execute("count", {"items": ["a", "b"]}) == "2"
    assert count(["x"]) == "1"  # the decorator still hands back the function


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
