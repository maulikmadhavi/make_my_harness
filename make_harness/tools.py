"""Tool registry: @tool turns a plain function into an LLM-callable tool.

The OpenAI function schema is generated from the function signature
(type hints -> JSON schema types) and the docstring (-> description).
Tool errors are returned as text results so the loop never crashes.
"""

import inspect

_PY_TO_JSON = {str: "string", int: "integer", float: "number", bool: "boolean"}


class Registry:
    def __init__(self):
        self._tools = {}

    def tool(self, func):
        sig = inspect.signature(func)
        props = {}
        required = []
        for name, param in sig.parameters.items():
            props[name] = {"type": _PY_TO_JSON.get(param.annotation, "string")}
            if param.default is inspect.Parameter.empty:
                required.append(name)
        self._tools[func.__name__] = {
            "func": func,
            "schema": {
                "type": "function",
                "function": {
                    "name": func.__name__,
                    "description": inspect.getdoc(func) or "",
                    "parameters": {"type": "object", "properties": props, "required": required},
                },
            },
        }
        return func

    def schemas(self):
        return [t["schema"] for t in self._tools.values()]

    def execute(self, name, args):
        if name not in self._tools:
            return f"Error: unknown tool '{name}'"
        try:
            return str(self._tools[name]["func"](**args))
        except Exception as e:
            return f"Error in {name}: {type(e).__name__}: {e}"


registry = Registry()
tool = registry.tool
