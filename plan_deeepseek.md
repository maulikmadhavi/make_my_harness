从头构建一个自定义的 Agent Harness 工具是一个绝佳的学习项目，它能让你深入理解 AI Agent 的核心机制。

其本质是：**一个围绕大语言模型（LLM）的循环（Loop）**。这个循环不断地将用户的请求和工具执行的结果传递给模型，直到模型认为任务完成并给出最终答案。

下面是一份从零开始的构建指南，涵盖了你关心的自定义聊天补全脚本和技能系统。

### 🧱 第一步：理解核心架构

一个基础的 Agent Harness 由以下几个核心部分组成：

1.  **模型客户端 (Model Client)**：负责与你的 LLM 通信。这是你自定义聊天补全脚本的切入点。
2.  **代理循环 (Agent Loop)**：整个系统的“大脑”，负责管理对话历史、调用模型、解析模型响应并决定下一步行动。
3.  **工具/技能系统 (Tool/Skill System)**：赋予 Agent 能力的“手脚”。你需要定义 Agent 可以使用的工具（如搜索、计算、文件操作），并实现其执行逻辑。
4.  **上下文管理 (Context Management)**：管理传递给模型的消息列表（`messages`），这是模型唯一的“记忆”。

### ⚙️ 第二步：实现核心代理循环

代理循环是整个 Harness 的引擎。一个极简的实现如下（伪代码）：

```python
def run_agent(user_input):
    # 1. 初始化消息列表，包含系统提示词
    messages = [{"role": "system", "content": "You are a helpful assistant..."}]
    messages.append({"role": "user", "content": user_input})

    # 2. 进入循环
    while True:
        # 3. 调用你的自定义模型客户端，获取响应
        response = my_chat_completion_script(messages, tools=my_tools_definition)
        
        # 4. 将模型的响应添加到消息历史中
        messages.append({"role": "assistant", "content": response})
        
        # 5. 检查模型是否要求调用工具
        if response.has_tool_calls():
            for tool_call in response.tool_calls:
                # 6. 执行工具
                tool_result = execute_skill(tool_call.name, tool_call.arguments)
                # 7. 将工具执行结果添加到消息历史
                messages.append({
                    "role": "tool", 
                    "tool_call_id": tool_call.id, 
                    "content": tool_result
                })
            # 8. 继续循环，将工具结果传给模型
            continue
        else:
            # 9. 模型未要求调用工具，说明任务完成，返回最终答案
            return response.content
```

**核心洞察**：整个复杂的 Agent 框架，其本质都是这个循环。

### 🧠 第三步：接入自定义聊天补全脚本

这是实现你“使用自己的自定义 chatcompletion Script”需求的关键。你需要将你的脚本封装成一个标准的模型客户端。

*   **定义统一接口**：创建一个函数（如 `my_chat_completion_script`），它接收消息历史 (`messages`) 和工具定义 (`tools`) 作为输入，并返回模型的响应。
*   **支持工具调用**：你的脚本需要能够理解并返回符合特定格式的工具调用请求。大多数主流 API（如 OpenAI、Anthropic）都支持标准的 `tool_calls` 格式。
*   **示例**：你可以参考 `basic-agent-harness` 项目，它展示了如何构建一个支持工具调用的 Agent。或者，像 `LocalHarness` 项目那样，通过 YAML 配置来定义 Agent 并连接到任何与 OpenAI 兼容的端点。

### 🛠️ 第四步：设计灵活的技能（工具）系统

这是实现“支持 custom skill”需求的核心。一个好的技能系统应该具备以下特点：

*   **技能注册表 (Registry)**：维护一个所有可用技能的字典，方便按名称查找和调用。
*   **标准化接口**：每个技能都是一个独立的函数或类，遵循相同的输入（参数）和输出（结果）规范。
*   **动态加载**：支持从文件系统或数据库中动态加载技能，方便扩展。
*   **技能描述 (Skill Description)**：为每个技能提供清晰的文本描述，这样 LLM 才能理解何时以及如何使用它。
*   **渐进式披露 (Progressive Disclosure)**：先向模型注入技能的元数据（如名称和简短描述），当模型决定调用时，再加载完整的指令。

### 🔒 第五步：安全与沙箱（重要）

让 Agent 执行代码或操作文件系统存在风险。因此，**沙箱环境至关重要**。

*   **限制文件系统访问**：将 Agent 的所有文件操作限制在一个特定的工作目录内。
*   **命令执行批准**：对于执行 Shell 命令等高风险操作，引入“人工审批（Human-in-the-loop）”流程，即 Agent 提出请求，等待用户确认后再执行。
*   **使用隔离环境**：考虑使用 Docker 容器或专门的沙箱服务（如 Modal Sandboxes）来运行 Agent 的代码，实现完全隔离。

### 🚀 第六步：进阶功能（可选）

在基础版本之上，你可以逐步添加更复杂的功能：

*   **记忆 (Memory)**：实现短期记忆（在当前会话中保持上下文）和长期记忆（跨会话存储信息）。
*   **规划 (Planning)**：让 Agent 在执行前先制定一个多步骤计划，提高处理复杂任务的效率。
*   **可观测性 (Observability)**：记录 Agent 的每一步思考、工具调用和耗时，方便调试和优化。
*   **中间件 (Middleware)**：通过中间件机制，可以在代理循环的不同阶段（如模型调用前后、工具执行前后）插入自定义逻辑，实现更精细的控制。

### 📚 学习资源

为了让你更好地实践，这里有一些优秀的参考项目：

*   **[agent-zero-to-hero](https://github.com/KeWang0622/agent-zero-to-hero)**：一个 7 周课程，用约 5000 行 Python 代码从零构建一个类似 Claude Code 的 Agent，**强烈推荐**。
*   **[your-first-harness.md](https://github.com/nexu-io/harness-engineering-guide/blob/main/guide/your-first-harness.md)**：一个在 50 行 Python 代码内实现完整 Harness 的精简示例。
*   **[basic-agent-harness](https://github.com/rogiia/basic-agent-harness)**：一个包含基础 Agent 和带工具 Agent 的示例项目，结构清晰。
*   **[LocalHarness](https://github.com/ahwurm/localharness)**：一个模型无关的 Agent Harness，支持通过 YAML 定义 Agent 并连接到任何 OpenAI 兼容的端点。

从最核心的循环开始，逐步迭代，你就能打造出一个功能强大且完全符合自己需求的 Agent Harness。如果在某个环节需要更具体的代码示例，随时可以再问我。


Here is the full guide translated into English.

---

Building a custom Agent Harness tool from scratch is an excellent learning project that allows you to deeply understand the core mechanisms of an AI Agent.

**Its essence is a loop around the Large Language Model (LLM).** This loop continuously passes the user's request and the results of tool executions to the model until the model determines the task is complete and provides a final answer.

Below is a step-by-step guide to building it from scratch, covering your requirements for a custom chat completion script and a custom skill system.

### 🧱 Step 1: Understand the Core Architecture

A basic Agent Harness consists of the following core components:

1.  **Model Client**: Responsible for communicating with your LLM. This is where your custom chat completion script fits in.
2.  **Agent Loop**: The "brain" of the entire system. It manages the conversation history, calls the model, parses the model's responses, and decides the next action.
3.  **Tool/Skill System**: The "hands and feet" that give the Agent capabilities. You need to define the tools the Agent can use (e.g., search, calculation, file operations) and implement their execution logic.
4.  **Context Management**: Manages the list of messages (`messages`) passed to the model. This is the model's only "memory."

### ⚙️ Step 2: Implement the Core Agent Loop

The Agent Loop is the engine of the entire Harness. Here is a minimal implementation (pseudo-code):

```python
def run_agent(user_input):
    # 1. Initialize the message list, including the system prompt
    messages = [{"role": "system", "content": "You are a helpful assistant..."}]
    messages.append({"role": "user", "content": user_input})

    # 2. Enter the main loop
    while True:
        # 3. Call your custom model client to get a response
        response = my_chat_completion_script(messages, tools=my_tools_definition)
        
        # 4. Add the model's response to the message history
        messages.append({"role": "assistant", "content": response})
        
        # 5. Check if the model wants to call a tool
        if response.has_tool_calls():
            for tool_call in response.tool_calls:
                # 6. Execute the skill/tool
                tool_result = execute_skill(tool_call.name, tool_call.arguments)
                # 7. Add the tool execution result to the message history
                messages.append({
                    "role": "tool", 
                    "tool_call_id": tool_call.id, 
                    "content": tool_result
                })
            # 8. Continue the loop, passing the tool results back to the model
            continue
        else:
            # 9. No tool call requested, meaning the task is complete. Return the final answer.
            return response.content
```

**Key Insight**: The entire complexity of advanced Agent frameworks ultimately boils down to this simple loop.

### 🧠 Step 3: Integrate Your Custom Chat Completion Script

This is the key to fulfilling your requirement of "using my own custom chatcompletion Script." You need to encapsulate your script into a standardized model client.

- **Define a Unified Interface**: Create a function (e.g., `my_chat_completion_script`) that receives the message history (`messages`) and tool definitions (`tools`) as input and returns the model's response.
- **Support Tool Calling**: Your script needs to understand and return tool-call requests in a standard format. Most mainstream APIs (like OpenAI's and Anthropic's) support the standardized `tool_calls` format.
- **Example**: You can refer to the `basic-agent-harness` project, which demonstrates how to build an Agent that supports tool calls. Alternatively, projects like `LocalHarness` use YAML configurations to define an Agent and connect it to any OpenAI-compatible endpoint.

### 🛠️ Step 4: Design a Flexible Skill (Tool) System

This is the core of supporting "custom skills." A well-designed skill system should have the following features:

- **Skill Registry**: Maintain a dictionary of all available skills, making it easy to look up and invoke them by name.
- **Standardized Interface**: Each skill is an independent function or class that follows a consistent input (arguments) and output (result) specification.
- **Dynamic Loading**: Support loading skills dynamically from the file system or a database to make the system easily extensible.
- **Skill Descriptions**: Provide a clear, plain-text description for each skill so the LLM can understand when and how to use it.
- **Progressive Disclosure**: First, inject the skill's metadata (like its name and a short description) into the model. Only load the full, detailed instructions when the model decides to call that specific skill.

### 🔒 Step 5: Security and Sandboxing (Important)

Allowing an Agent to execute code or manipulate the file system carries risks. Therefore, **a sandbox environment is crucial**.

- **Restrict File System Access**: Confine all file operations performed by the Agent to a specific working directory.
- **Command Execution Approval**: For high-risk operations (like executing shell commands), implement a **Human-in-the-Loop (HITL)** process. The Agent proposes the action and waits for the user to confirm before executing it.
- **Use Isolated Environments**: Consider using Docker containers or dedicated sandboxing services (like Modal Sandboxes) to run the Agent's code with complete isolation.

### 🚀 Step 6: Advanced Features (Optional)

Once the basic version is working, you can incrementally add more complex functionalities:

- **Memory**: Implement short-term memory (maintaining context within a session) and long-term memory (storing information across sessions).
- **Planning**: Allow the Agent to create a multi-step plan before execution, improving its efficiency in handling complex tasks.
- **Observability**: Log every thought, tool call, and timing metric of the Agent for easier debugging and optimization.
- **Middleware**: Implement a middleware mechanism to inject custom logic at different stages of the Agent loop (e.g., before/after model calls, before/after tool execution) for fine-grained control.

### 📚 Learning Resources

To help you put this into practice, here are some excellent reference projects:

- **[agent-zero-to-hero](https://github.com/KeWang0622/agent-zero-to-hero)** - A 7-week course that builds an Agent similar to Claude Code from scratch in about 5,000 lines of Python code. **Highly recommended.**
- **[your-first-harness.md](https://github.com/nexu-io/harness-engineering-guide/blob/main/guide/your-first-harness.md)** - A minimalist example that implements a complete Harness in just 50 lines of Python code.
- **[basic-agent-harness](https://github.com/rogiia/basic-agent-harness)** - An example project containing both a basic Agent and one with tools, featuring a clear structure.
- **[LocalHarness](https://github.com/ahwurm/localharness)** - A model-agnostic Agent Harness that supports defining Agents via YAML and connecting to any OpenAI-compatible endpoint.

Start with the core loop and iterate step by step, and you will build a powerful Agent Harness perfectly tailored to your needs. If you need more specific code examples for any particular step, feel free to ask!