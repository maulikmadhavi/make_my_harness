
@Web search 
I have developped simple harness and make it available open-source at: https://github.com/maulikmadhavi/make_my_harness.git

The interface is very simple and supports very limited tools/slash command. The harness comes with built-in toolsets:

#### File System Tools
- `read_file(path)` - Read text files with line numbers (truncated at 2000 lines)
- `write_file(path, content)` - Write content to files, creating directories as needed

#### Shell Tools
- `run_command(command)` - Execute shell commands with timeout (60s) and output limits

#### Web Tools
- `web_search(query)` - Search the web via Tavily or Brave API (requires API key)
- `http_request(method, url, headers_json, body_json)` - Make HTTP requests to APIs

#### Memory Tools
- `save_memory(name, content)` - Save facts to persistent memory
- `read_memory(name)` - Retrieve saved facts by name

### Core Capabilities

1. **Interactive REPL**: Run `make-harness` or `python main.py` to start an interactive agent session
2. **LLM Abstraction**: Swap backends (Groq, Ollama, vLLM, OpenAI) by modifying `llm_providers.py`
3. **Token Budget Management**: Automatic context compaction when conversations exceed token limits
4. **Error Recovery**: Handles malformed tool calls and API errors gracefully
5. **Audit Trail**: Complete logging of all agent actions to `logs/` directory

Please suggest your comments and improvement on it.



---
I like the direction a lot. Looking at your description, you're intentionally building **a minimal, hackable harness**, not "yet another LangGraph". That's a good niche because most current frameworks are either:

* **too abstract** (LangGraph, CrewAI, AutoGen),
* **too opinionated** (Claude Code, Codex CLI),
* or **too large to understand** (OpenHands/OpenHarness). ([GitHub][1])

I would keep the core small, but make the architecture extensible.

## Overall assessment

I'd rate it as follows:

| Area                 | Score | Comments                       |
| -------------------- | ----: | ------------------------------ |
| Simplicity           | ⭐⭐⭐⭐⭐ | Biggest strength               |
| Readability          | ⭐⭐⭐⭐⭐ | Easy to understand             |
| Extensibility        | ⭐⭐⭐⭐☆ | Good, but plugins would help   |
| Agent capability     | ⭐⭐⭐☆☆ | Basic ReAct agent              |
| Production readiness | ⭐⭐⭐☆☆ | Needs sandboxing & permissions |
| Research value       | ⭐⭐⭐⭐⭐ | Excellent educational project  |

---

# Things I would NOT change

These are already good decisions.

### 1. Small built-in toolset

Many frameworks ship with 100+ tools.

Yours ships with:

* filesystem
* shell
* web
* memory

That's already enough to build useful agents.

Don't add 50 more tools.

Instead make adding tools easy.

---

### 2. LLM abstraction

This is exactly right.

```text
Groq

Ollama

OpenAI

vLLM
```

All implementing the same interface.

I'd actually expand this into a provider registry.

```python
ProviderRegistry.register(GroqProvider)

ProviderRegistry.register(OpenAIProvider)

ProviderRegistry.register(OllamaProvider)
```

---

### 3. Audit logs

Excellent idea.

I'd even expose

```text
logs/

session.json

tool_calls.json

llm_requests.json

llm_responses.json
```

Debugging becomes trivial.

---

# Things I'd improve

## 1. Introduce an Event Bus (Highest Priority)

Currently your runtime probably looks like

```text
User

↓

LLM

↓

Tool

↓

LLM
```

Instead I'd make

```text
UserMessage

↓

BeforeLLM

↓

AfterLLM

↓

BeforeTool

↓

AfterTool

↓

MemoryUpdated

↓

AgentFinished
```

Everything emits events.

Now

* tracing
* UI
* plugins
* logging

all become independent.

---

## 2. Plugin System

Right now tools appear built-in.

Instead

```text
plugins/

git/

docker/

jira/

rag/

python/

filesystem/
```

Each plugin exposes

```python
register(app)
```

The runtime never changes.

---

## 3. Slash Commands should also be Plugins

Instead of

```text
/help

/reset

/history
```

hardcoded

allow

```python
class SlashCommand:

    name="/benchmark"

    def execute(...)
```

Now anyone can write

```text
/mycompany

/deploy

/pr-review

```

---

## 4. Tool Metadata

Current

```python
run_command(command)
```

I'd extend

```python
Tool(

name

description

permission

timeout

parallel

cost

examples

tags
)
```

This becomes useful later.

---

## 5. Permission Layer

Before

```text
run_command("rm -rf")
```

there should be

```text
PermissionManager

↓

Allow?

↓

Execute
```

This becomes essential once people start using the harness on real machines.

---

## 6. Context Builder

Instead of

```python
messages
```

I'd introduce

```python
ContextBuilder.build(session)
```

Internally

```text
System Prompt

+

Conversation

+

Relevant Memory

+

Scratchpad

+

Tool Results

↓

LLM
```

Now RAG becomes easy later.

---

## 7. Session Object

Instead of passing

```python
messages

memory

logs

cwd

token_budget
```

everywhere

I'd use

```python
Session

history

memory

cwd

config

scratchpad

token_budget

tool_registry
```

Much cleaner.

---

## 8. Separate Runtime from Planner

Instead of

```text
Agent
```

I'd split

```text
Runtime

Planner

Tool Executor

Provider

Memory
```

Now you can experiment with planners without touching anything else.

---

## 9. Streaming

I'd definitely add

```python
stream_chat()
```

Almost every modern harness streams tokens.

---

## 10. Tool Call Recovery

One thing Claude Code does very well.

Suppose LLM outputs

```json
{
"name":"read_file",
"arguments":"README.md"
}
```

instead of JSON.

Instead of failing

auto-repair

```python
RepairParser

↓

Retry

↓

Execute
```

This makes agents much more robust.

---

# Features I'd add in v2

Rather than adding more built-in tools, I'd add platform features:

* **MCP support** so users can connect external tool servers without modifying the harness.
* **Provider configuration** from YAML/TOML instead of editing Python files.
* **Middleware hooks** (`before_llm`, `after_tool`, etc.).
* **Conversation replay** to reproduce and debug sessions.
* **Session persistence** so interrupted work can resume.
* **Plugin discovery** (e.g., `plugins/` folder or entry points).
* **Rich terminal UI** with streaming, tool call visualization, and colored logs.

---

# Features I'd save for v3

Don't add these until the core is stable:

* multi-agent
* DAG execution
* CrewAI
* LangGraph
* Tree of Thoughts
* Reflection
* Self-debugging

These are exciting but add a lot of complexity.

---

# One thing I think can make your project stand out

Most open-source harnesses try to become **another agent framework**.

I think your project should become the **reference implementation of a clean, understandable agent runtime**.

Something like:

> **"A 1,000-line educational agent harness that you can fully understand in one afternoon."**

That's surprisingly rare. Projects like OpenHarness and other research-oriented frameworks are powerful, but they have already grown into much larger systems with plugins, workflows, and multi-agent orchestration. ([GitHub][1])

If you keep the core around 1–2k lines, well documented, and architecturally clean, it becomes valuable not only as a usable tool but also as a learning resource. That's a niche I think is underserved and where your repository could become a go-to reference for people who want to build their own AI harness from scratch.

[1]: https://github.com/HKUDS/OpenHarness?utm_source=chatgpt.com "GitHub - HKUDS/OpenHarness: \"OpenHarness: Open Agent Harness with a Built-in Personal Agent--Ohmo!\" · GitHub"


---
@Web search are we closer to this? https://www.eicta.iitk.ac.in/knowledge-hub/artificial-intelligence/how-to-build-ai-agent-from-scratch

----
Yes—I'd say you're **much closer than you probably realize**.

The IIT Kanpur/EICTA article is aimed at taking someone from "I know Python" to "I have a working agent." It identifies four core building blocks:

1. LLM (brain)
2. Tools
3. Memory
4. Agent loop (Think → Act → Observe) ([EICTA Consortium][1])

Based on your repository description, you've already implemented almost all of these.

| EICTA Architecture | Your Harness                              | Status   |
| ------------------ | ----------------------------------------- | -------- |
| LLM client         | Groq / Ollama / vLLM / OpenAI abstraction | ✅ Better |
| Agent Loop         | ReAct loop with tool calling              | ✅        |
| Tool Registry      | Filesystem, shell, web, HTTP, memory      | ✅ Better |
| Memory             | Persistent memory                         | ✅        |
| Context management | Token budget compaction                   | ✅ Better |
| Error handling     | Tool/API recovery                         | ✅ Better |
| Logging            | Audit trail                               | ✅ Better |

So I would say you're already **past the "build your first AI agent" stage**. ([EICTA Consortium][1])

---

## Where the article stops

The article intentionally keeps things simple:

```text
Goal

↓

LLM

↓

Tool

↓

LLM

↓

Answer
```

That's exactly what a beginner needs.

Your harness is already adding engineering concerns like:

* provider abstraction
* logging
* context compaction
* persistent memory

which aren't covered in the beginner guide. ([EICTA Consortium][1])

---

# Where your harness can evolve

This is the gap between a **working AI agent** and a **professional harness**.

I think the roadmap looks something like this:

```
Stage 1
---------
LLM
Loop
Tools
Memory

↑
You are here
```

↓

```
Stage 2
---------
Plugin system

Event bus

Permissions

Streaming

Configuration

Session management
```

↓

```
Stage 3
---------
Planner

Reflection

Retry

Middleware

Prompt library

Evaluation
```

↓

```
Stage 4
---------
Workflow engine

Multi-agent

MCP

Sub-agents

Distributed execution
```

---

# One thing the article doesn't emphasize enough

The article says:

> "The loop is what makes an agent an agent." ([EICTA Consortium][1])

I would modify that slightly:

> **The runtime is what makes an agent framework valuable.**

Many projects can implement:

```python
while True:
    response = llm(...)
```

in 50–100 lines.

The difficult part is everything surrounding that loop:

* permission handling
* retries
* streaming
* context building
* logging
* plugins
* configuration
* session persistence
* tool scheduling
* debugging

That's why Claude Code, Codex CLI, OpenHands, etc., have tens of thousands of lines of code even though the core loop itself is tiny.

---

# If I were maintaining your repository

I wouldn't try to compete with LangGraph or CrewAI.

Instead, I'd position it as:

> **A minimal, hackable AI agent harness built from first principles.**

That fills a gap that's surprisingly underserved.

I'd focus on three design principles:

1. **Understandable** — the entire runtime should be readable in a few hours.
2. **Extensible** — adding a new provider, tool, or plugin should require minimal code.
3. **Framework-agnostic** — no dependency on LangChain, LangGraph, CrewAI, etc.

---

## My suggested roadmap

If this were my project, I'd prioritize the next milestones in this order:

1. **Plugin architecture** (tools, slash commands, providers).
2. **Event bus + middleware hooks** (`before_llm`, `after_tool`, etc.).
3. **Streaming support** for both model output and tool progress.
4. **Permission/sandbox layer** for shell and file operations.
5. **YAML/TOML configuration** instead of editing Python to change providers.
6. **Session persistence and replay** for debugging.
7. **MCP compatibility** so external tool servers can plug in without modifying the harness.

Those additions would move the project from **"a simple educational agent"** to **"a lightweight, extensible agent runtime"**, while still preserving the simplicity that makes it appealing.

[1]: https://www.eicta.iitk.ac.in/knowledge-hub/artificial-intelligence/how-to-build-ai-agent-from-scratch?utm_source=chatgpt.com "How to Build an AI Agent From Scratch in 2026: Step-by-Step Guide | EICTA Consortium"
