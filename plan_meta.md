Building your own harness from scratch is the right move if you want control. Don't use LangChain. You only need 4 pieces.

Here is the minimal architecture that scales to production:

What you're building
Code
[ User Input ] -> [ Agent Loop ] -> [ Your ChatCompletion Script ] -> [ Tool Registry <- Skills ] -> loop
                     |
                     -> State / Memory
Core contracts:

ChatCompletion: messages + tools -> assistant message (with tool_calls)
Skill: A package that contributes system prompt + tools
Harness: The loop that calls LLM, executes tools, manages context
1. Project structure
Code
agent-harness/
├── core/
│   ├── llm.py              # abstraction over your script
│   ├── skill.py            # Skill base class
│   ├── registry.py         # tool + skill loader
│   ├── state.py            # conversation state
│   └── agent.py            # the loop
├── chatcompletion/
│   └── my_chatcompletion.py # YOUR script, wrapped
├── skills/
│   ├── __init__.py
│   ├── builtin/
│   │   └── calculator.py
│   └── custom/             # auto-discovered
│       └── web_search/
│           ├── skill.py
│           └── manifest.yaml
└── main.py

13 lines hidden
2. Step 1: Wrap your custom chatcompletion script
Your script can be anything, local vLLM, OpenAI compatible, Ollama. You just need to normalize it to one interface.

In core/llm.py:

Python
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]

@dataclass
class LLMResponse:
    content: Optional[str]
    tool_calls: List[ToolCall]
    raw: Any = None

class ChatCompletionClient:
    def complete(self, messages: List[Dict], tools: List[Dict] = None) -> LLMResponse:
        raise NotImplementedError

# Now wrap YOUR script
class MyCustomClient(ChatCompletionClient):
    def __init__(self):
        from chatcompletion.my_chatcompletion import my_chat_fn
        self.my_chat_fn = my_chat_fn

    def complete(self, messages, tools=None) -> LLMResponse:
        # Adapt to your function's signature
        # Example: your fn expects openai-style messages and returns a dict
        result = self.my_chat_fn(
            messages=messages,
            tools=tools, # pass through
            temperature=0.2
        )
        # Normalize result to LLMResponse
        # result = {"content": "...", "tool_calls": [{"id": "...", "function": {"name": "...", "arguments": "{...}"}}]}
        tool_calls = []
        for tc in result.get("tool_calls", []):
            args = tc["function"]["arguments"]
            if isinstance(args, str):
                args = json.loads(args)
            tool_calls.append(ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=args
            ))
        return LLMResponse(
            content=result.get("content"),
            tool_calls=tool_calls,
            raw=result
        )

46 lines hidden
Requirement for your script: it MUST support tool calling. If it does not, add a parser in this wrapper that forces JSON output and extracts {"tool": "name", "args": {...}}.

3. Step 2: Skill system
This is the key to custom skills. A skill is not just a tool. It is instructions + tools + hooks.

core/skill.py:

Python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Callable, Dict, Any

@dataclass
class ToolDef:
    name: str
    description: str
    parameters: Dict[str, Any] # JSON Schema
    function: Callable
    skill_origin: str = ""

class Skill(ABC):
    @property
    @abstractmethod
    def name(self) -> str:...

    @property
    @abstractmethod
    def description(self) -> str:...

    @property
    def system_prompt(self) -> str:
        return "" # extra instructions injected when skill is active

    @abstractmethod
    def get_tools(self) -> List[ToolDef]:...

    def on_load(self): pass
    def on_tool_call(self, tool_name, args): pass # middleware hook

25 lines hidden
Example custom skill: skills/custom/web_search/skill.py

Python
from core.skill import Skill, ToolDef

def search_web(query: str, num_results: int = 5):
    # your implementation, e.g. tavily, serper
    return f"Results for {query}:..."

class WebSearchSkill(Skill):
    @property
    def name(self): return "web_search"
    @property
    def description(self): return "Search the web for current info"
    @property
    def system_prompt(self):
        return "When user asks about recent events, use web_search."

    def get_tools(self):
        return [ToolDef(
            name="web_search",
            description="Search the web",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "num_results": {"type": "integer"}
                },
                "required": ["query

21 lines hidden
