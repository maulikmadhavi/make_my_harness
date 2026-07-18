Given your background (local-first, custom endpoints, no vendor lock-in, agentic workflows), I would **not** start from an existing coding agent like Claude Code or Codex CLI. Most of them assume a specific LLM API and their internal architecture is difficult to customize.

Instead, I'd build a **minimal agent harness** that treats the LLM as just another pluggable component.

---

# What is an Agent Harness?

Think of it as an operating system for LLMs.

```
                +----------------------+
                |      CLI / UI        |
                +----------+-----------+
                           |
                     User Request
                           |
                   +-------v--------+
                   | Agent Runtime  |
                   +-------+--------+
                           |
        +------------------+-----------------+
        |                  |                 |
        |                  |                 |
  Planner/Loop      Memory/Context      Skill Manager
        |                  |                 |
        +------------------+-----------------+
                           |
                     LLM Adapter
                           |
             Your ChatCompletion Script
```

Notice that the runtime never knows whether the model is

* OpenAI
* vLLM
* Ollama
* llama.cpp

Everything goes through your adapter.

---

# Layer 1 — LLM Adapter

This is the most important abstraction.

```python
class ChatModel:

    async def chat(
        self,
        messages,
        tools=None,
        temperature=0.2
    ):
        ...
```

Your custom_llm wrapper already fits here.

```
Agent
    ↓
ChatModel.chat()
    ↓
custom_llm.py
    ↓
requests.post(...)
```

Later you can add

```
OpenAIAdapter
OllamaAdapter
vLLMAdapter
GeminiAdapter
AnthropicAdapter
```

without changing the rest of the framework.

---

# Layer 2 — Skill Interface

Every skill should have exactly the same interface.

```python
class Skill:

    name = "shell"

    description = "Execute shell commands"

    parameters = {
        ...
    }

    async def run(self, **kwargs):
        ...
```

Example

```python
class ReadFile(Skill):

    name = "read_file"

    async def run(self, path):

        with open(path) as f:
            return f.read()
```

Another

```python
class SearchCode(Skill):

    async def run(self, keyword):

        ...
```

The agent never knows what the skill does.

---

# Layer 3 — Skill Registry

```
skills/

    filesystem.py

    terminal.py

    github.py

    python.py

    browser.py

    rag.py

    jira.py

    custom.py
```

Automatically load

```
skills/*.py
```

using

```
importlib
```

Each one registers itself.

```
registry.register(ReadFile())
registry.register(Grep())
registry.register(MyDatabase())
```

---

# Layer 4 — Planner

The planner decides

```
Should I call a tool?
```

Simplest implementation:

```
User
 ↓
LLM
 ↓

Tool Call?

YES
 ↓

Execute

↓

Append Result

↓

LLM Again

↓

Final Answer
```

Exactly how OpenAI function calling works.

Pseudo-code

```python
while True:

    response = model.chat(history, tools)

    if response.tool_call:

        result = execute(response.tool_call)

        history.append(result)

        continue

    break
```

This loop is the heart of every modern agent.

---

# Layer 5 — Tool Calling Format

Don't hardcode OpenAI's format.

Create your own.

Example

```json
{
    "tool":"read_file",
    "args":
    {
        "path":"README.md"
    }
}
```

or

```json
{
    "name":"shell",
    "arguments":
    {
        "command":"ls -l"
    }
}
```

Your parser converts this into

```
registry.execute(...)
```

---

# Layer 6 — Memory

Separate memory into three parts.

```
Conversation Memory

↓

Long-term Memory

↓

Scratchpad
```

Example

```
history/
```

```
messages.json
```

```
memory/
```

```
faiss/

sqlite/

chroma/
```

```
scratch/

plan.md

todo.md
```

---

# Layer 7 — Context Builder

Instead of

```
messages
```

pass

```
System Prompt

+

Conversation

+

Retrieved Docs

+

Current File

+

Tool Outputs

+

Scratchpad
```

The context builder assembles this every turn.

---

# Layer 8 — Event Bus

Every action emits an event.

```
UserMessage

AssistantMessage

ToolStarted

ToolFinished

TokenReceived

Error
```

Now you can plug in

* logging
* tracing
* LangSmith
* Traceloop
* OpenTelemetry

without modifying agent code.

---

# Layer 9 — Plugin System

A plugin can register

```
skills

hooks

commands

prompts

events
```

For example

```
plugins/

github/

docker/

slack/

git/

jira/

```

Each plugin exposes

```python
class Plugin:

    def register(self, app):

        app.add_skill(...)

        app.add_prompt(...)

        app.on(...)
```

---

# Layer 10 — CLI

```
myagent

chat

run

shell

eval

skill

memory

trace
```

Example

```
myagent chat
```

```
You > summarize this repo
```

---

# Internal Runtime

```
User

↓

CLI

↓

Runtime

↓

Planner

↓

LLM

↓

Tool?

↓

Skill Manager

↓

Tool

↓

Planner

↓

LLM

↓

Answer
```

---

# Suggested Project Structure

```
agent/

    runtime.py

    planner.py

    context.py

    parser.py

    events.py

models/

    base.py

    custom_llm.py

    openai.py

    ollama.py

skills/

    shell.py

    filesystem.py

    python.py

    rag.py

    git.py

plugins/

memory/

config/

tests/

examples/

main.py
```

---

# Advanced Features to Add Later

Once the core works, you can incrementally add:

* **Streaming token support** so the UI displays responses as they arrive.
* **Parallel tool execution** for independent tasks.
* **Sub-agents** where specialized agents (e.g., coding, research, planning) collaborate.
* **MCP-compatible skills** so external tools can be integrated without custom adapters.
* **Permission and approval policies** (e.g., require confirmation before destructive shell commands).
* **Session persistence and replay** for debugging.
* **Observability** with structured traces, latency metrics, and token accounting.
* **Prompt/version management** for reproducible experiments.
* **State machine or workflow engine** for long-running tasks instead of only a ReAct loop.

---

## If I were building this today

I would keep the architecture intentionally small:

```
                  CLI / Web UI
                        │
                ┌───────▼────────┐
                │  Agent Runtime  │
                └───┬─────────┬───┘
                    │         │
              Context     Event Bus
                    │         │
                    ▼         ▼
              Planner Loop   Plugins
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
     LLM Adapter         Skill Registry
         │                     │
  custom_llm/OpenAI/...    File, Shell, Git,
                          Python, RAG, MCP
```

This keeps each concern isolated: swapping your custom_llm ChatCompletion script only requires a new adapter; adding a custom skill only requires dropping a new module into the skills directory; the planner, memory, and CLI remain unchanged.

For someone with your experience building local AI systems, this is a realistic weekend MVP and a solid foundation that can evolve into a coding assistant comparable in architecture (though much simpler initially) to tools like Claude Code or OpenHands. From there, you can layer on planning, retrieval, code editing, and multi-agent capabilities without having to redesign the core.

