Agent
In this tutorial, we first focus on introducing the ReAct agent in AgentScope, then we briefly introduce how to customize your own agent from scratch.

ReAct Agent
In AgentScope, the ReActAgent class integrates various features into a final implementation, including

Features of ReActAgent
Feature

Reference

Support realtime steering

Support memory compression

Support parallel tool calls

Support structured output

Support fine-grained MCP control

MCP

Support agent-controlled tools management (Meta tool)

Tool

Support self-controlled long-term memory

Long-Term Memory

Support automatic state management

State/Session Management

Due to limited space, in this tutorial we only demonstrate the first three features of ReActAgent class, leaving the others to the corresponding sections listed above.

import asyncio
import json
import os
from datetime import datetime
import time

from pydantic import BaseModel, Field

from agentscope.agent import ReActAgent
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import TextBlock, Msg
from agentscope.model import DashScopeChatModel
from agentscope.tool import Toolkit, ToolResponse
Realtime Steering
The realtime steering allows user to interrupt the agent’s reply at any time, which is implemented based on the asyncio cancellation mechanism.

Specifically, when calling the interrupt method of the agent, it will cancel the current reply task, and execute the handle_interrupt method for postprocessing.

Hint

With the feature of supporting streaming tool results in Tool, users can interrupt the tool execution if it takes too long or deviates from user expectations by Ctrl+C in the terminal or calling the interrupt method of the agent in your code.

The interruption logic has been implemented in the AgentBase class as a basic feature, leaving a handle_interrupt method for users to customize the post-processing of interruption as follows:

# code snippet of AgentBase
class AgentBase:
    ...
    async def __call__(self, *args: Any, **kwargs: Any) -> Msg:
        ...
        reply_msg: Msg | None = None
        try:
            self._reply_task = asyncio.current_task()
            reply_msg = await self.reply(*args, **kwargs)

        except asyncio.CancelledError:
            # Catch the interruption and handle it by the handle_interrupt method
            reply_msg = await self.handle_interrupt(*args, **kwargs)

        ...

    @abstractmethod
    async def handle_interrupt(self, *args: Any, **kwargs: Any) -> Msg:
        pass
In ReActAgent class, we return a fixed message “I noticed that you have interrupted me. What can I do for you?” as follows:

Example of interruption
Example of interruption

You can override it with your own implementation, for example, calling the LLM to generate a simple response to the interruption.

Memory Compression
As conversations grow longer, the token count in memory can exceed model context limits or slow down inference. ReActAgent provides an automatic memory compression feature to address this issue.

Basic Usage

To enable memory compression, provide a CompressionConfig instance when initializing the ReActAgent:

from agentscope.agent import ReActAgent
from agentscope.token import CharTokenCounter

agent = ReActAgent(
    name="Assistant",
    sys_prompt="You are a helpful assistant.",
    model=model,
    formatter=formatter,
    compression_config=ReActAgent.CompressionConfig(
        enable=True,
        agent_token_counter=CharTokenCounter(),  # The token counter for the agent
        trigger_threshold=10000,  # Trigger compression when exceeding 10000 tokens
        keep_recent=3,            # Keep the most recent 3 messages uncompressed
    ),
)
When memory compression is enabled, the agent monitors the token count in its memory. Once it exceeds the trigger_threshold, the agent automatically:

Identifies messages that haven’t been compressed yet (via exclude_mark)

Keeps the most recent keep_recent messages uncompressed (to preserve recent context)

Sends older messages to an LLM to generate a structured summary

Marks the compressed messages with MemoryMark.COMPRESSED (via update_messages_mark)

Stores the summary in memory (via update_compressed_summary)

Important

The compression uses a marking mechanism rather than replacing messages. Old messages are marked as compressed and excluded from future retrievals via exclude_mark=MemoryMark.COMPRESSED, while the generated summary is stored separately and retrieved when needed. This approach preserves the original messages and allows flexible memory management. For more details about the mark functionality, please refer to Memory.

By default, the compressed summary is structured into five key fields:

task_overview: The user’s core request and success criteria

current_state: What has been completed so far, including files and outputs

important_discoveries: Technical constraints, decisions, errors, and failed approaches

next_steps: Specific actions needed to complete the task

context_to_preserve: User preferences, domain details, and promises made

Customizing Compression

You can customize how compression works by specifying summary_schema, summary_template, and compression_prompt parameters.

compression_prompt: Guides the LLM on how to generate the summary

summary_schema: Defines the structure of the compressed summary using a Pydantic model

summary_template: Formats how the compressed summary is presented back to the agent

Here’s an example of customizing the compression:

from pydantic import BaseModel, Field

# Define a custom summary structure
class CustomSummary(BaseModel):
    main_topic: str = Field(
        max_length=200,
        description="The main topic of the conversation"
    )
    key_points: str = Field(
        max_length=400,
        description="Important points discussed"
    )
    pending_tasks: str = Field(
        max_length=200,
        description="Tasks that remain to be done"
    )

# Create agent with custom compression configuration
agent = ReActAgent(
    name="Assistant",
    sys_prompt="You are a helpful assistant.",
    model=model,
    formatter=formatter,
    compression_config=ReActAgent.CompressionConfig(
        enable=True,
        agent_token_counter=CharTokenCounter(),
        trigger_threshold=10000,
        keep_recent=3,
        # Custom schema for structured summary
        summary_schema=CustomSummary,
        # Custom prompt to guide compression
        compression_prompt=(
            "<system-hint>Please summarize the above conversation "
            "focusing on the main topic, key discussion points, "
            "and any pending tasks.</system-hint>"
        ),
        # Custom template to format the summary
        summary_template=(
            "<system-info>Conversation Summary:\n"
            "Main Topic: {main_topic}\n\n"
            "Key Points:\n{key_points}\n\n"
            "Pending Tasks:\n{pending_tasks}"
            "</system-info>"
        ),
    ),
)
The summary_template uses the fields defined in summary_schema as placeholders (e.g., {main_topic}, {key_points}). After the LLM generates the structured summary, these placeholders will be replaced with the actual values.

Note

The agent ensures that tool use and tool result pairs are kept together during compression to maintain the integrity of the conversation flow.

Tip

You can use a smaller, faster model for compression by specifying a different compression_model and compression_formatter to reduce costs and latency.

Parallel Tool Calls
ReActAgent supports parallel tool calls by providing a parallel_tool_calls argument in its constructor. When multiple tool calls are generated, and parallel_tool_calls is set to True, they will be executed in parallel by the asyncio.gather function.

Note

The parallel tool execution in ReActAgent is implemented based on asyncio.gather. Therefore, to maximize the effect of parallel tool execution, both the tool function itself and the logic within it must be asynchronous.

Note

When running, please ensure that parallel tool calling is supported at the model level and the corresponding parameters are set correctly (can be passed through generate_kwargs). For example, for the DashScope API, you need to set parallel_tool_calls to True, otherwise parallel tool calling will not be possible.

# prepare a tool function
async def example_tool_function(tag: str) -> ToolResponse:
    """A sample example tool function"""
    start_time = datetime.now().strftime("%H:%M:%S.%f")

    # Sleep for 3 seconds to simulate a long-running task
    await asyncio.sleep(3)

    end_time = datetime.now().strftime("%H:%M:%S.%f")
    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=f"Tag {tag} started at {start_time} and ended at {end_time}. ",
            ),
        ],
    )


toolkit = Toolkit()
toolkit.register_tool_function(example_tool_function)

# Create an ReAct agent
agent = ReActAgent(
    name="Jarvis",
    sys_prompt="You're a helpful assistant named Jarvis.",
    model=DashScopeChatModel(
        model_name="qwen-max",
        api_key=os.environ["DASHSCOPE_API_KEY"],
        # Preset the generation kwargs to enable parallel tool calls
        generate_kwargs={
            "parallel_tool_calls": True,
        },
    ),
    memory=InMemoryMemory(),
    formatter=DashScopeChatFormatter(),
    toolkit=toolkit,
    parallel_tool_calls=True,
)


async def example_parallel_tool_calls() -> None:
    """Example of parallel tool calls"""
    # prompt the agent to generate two tool calls at once
    await agent(
        Msg(
            "user",
            "Generate two tool calls of the 'example_tool_function' function with tag as 'tag1' and 'tag2' AT ONCE so that they can execute in parallel.",
            "user",
        ),
    )


asyncio.run(example_parallel_tool_calls())
Jarvis: {
    "type": "tool_use",
    "id": "call_060933caa9cf4a7ea820a9",
    "name": "example_tool_function",
    "input": {
        "tag": "tag1"
    }
}
Jarvis: {
    "type": "tool_use",
    "id": "call_5ff6b7e85d4c44a0bbe4dc",
    "name": "example_tool_function",
    "input": {
        "tag": "tag2"
    }
}
system: {
    "type": "tool_result",
    "id": "call_060933caa9cf4a7ea820a9",
    "name": "example_tool_function",
    "output": [
        {
            "type": "text",
            "text": "Tag tag1 started at 08:08:01.927172 and ended at 08:08:04.930418. "
        }
    ]
}
system: {
    "type": "tool_result",
    "id": "call_5ff6b7e85d4c44a0bbe4dc",
    "name": "example_tool_function",
    "output": [
        {
            "type": "text",
            "text": "Tag tag2 started at 08:08:01.927244 and ended at 08:08:04.930927. "
        }
    ]
}
Jarvis: The 'example_tool_function' has been called in parallel with the tags 'tag1' and 'tag2'. Here are the results:

- For 'tag1', the function started at 08:08:01.927172 and ended at 08:08:04.930418.
- For 'tag2', the function started at 08:08:01.927244 and ended at 08:08:04.930927.

Both functions executed during the same time frame, indicating that they were indeed running in parallel.
Structured Output
To generate a structured output, the ReActAgent instance receives a child class of the pydantic.BaseModel as the structured_model argument in its __call__ function. Then we can get the structured output from the metadata field of the returned message.

Taking introducing Einstein as an example:

# Create an ReAct agent
agent = ReActAgent(
    name="Jarvis",
    sys_prompt="You're a helpful assistant named Jarvis.",
    model=DashScopeChatModel(
        model_name="qwen-max",
        api_key=os.environ["DASHSCOPE_API_KEY"],
        # Preset the generation kwargs to enable parallel tool calls
        generate_kwargs={
            "parallel_tool_calls": True,
        },
    ),
    memory=InMemoryMemory(),
    formatter=DashScopeChatFormatter(),
    toolkit=Toolkit(),
    parallel_tool_calls=True,
)


# The structured model
class Model(BaseModel):
    name: str = Field(description="The name of the person")
    description: str = Field(
        description="A one-sentence description of the person",
    )
    age: int = Field(description="The age")
    honor: list[str] = Field(description="A list of honors of the person")


async def example_structured_output() -> None:
    """The example structured output"""
    res = await agent(
        Msg(
            "user",
            "Introduce Einstein",
            "user",
        ),
        structured_model=Model,
    )
    print("\nThe structured output:")
    print(json.dumps(res.metadata, indent=4))


asyncio.run(example_structured_output())
/home/runner/work/agentscope/agentscope/src/agentscope/model/_dashscope_model.py:194: DeprecationWarning: 'required' is not supported by DashScope API. It will be converted to 'auto'.
  warnings.warn(
Jarvis: {
    "type": "tool_use",
    "id": "call_1b44f841d03940bcbd7a91",
    "name": "generate_response",
    "input": {
        "name": "Albert Einstein",
        "description": "A renowned theoretical physicist, best known for developing the theory of relativity.",
        "age": 76,
        "honor": [
            "Nobel Prize in Physics (1921)",
            "Copley Medal (1925)",
            "Max Planck Medal (1929)"
        ]
    }
}
system: {
    "type": "tool_result",
    "id": "call_1b44f841d03940bcbd7a91",
    "name": "generate_response",
    "output": [
        {
            "type": "text",
            "text": "Successfully generated response."
        }
    ]
}
Jarvis: Albert Einstein was a renowned theoretical physicist, best known for developing the theory of relativity. Born in 1879, he made significant contributions to the field of physics and changed our understanding of the universe. He was awarded the Nobel Prize in Physics in 1921, not primarily for his work on relativity, but for his discovery of the law of the photoelectric effect, which was pivotal in the development of quantum theory. Throughout his career, Einstein also received other prestigious awards such as the Copley Medal in 1925 and the Max Planck Medal in 1929. He passed away at the age of 76, leaving behind a legacy that continues to influence science and philosophy.

The structured output:
{
    "name": "Albert Einstein",
    "description": "A renowned theoretical physicist, best known for developing the theory of relativity.",
    "age": 76,
    "honor": [
        "Nobel Prize in Physics (1921)",
        "Copley Medal (1925)",
        "Max Planck Medal (1929)"
    ]
}
Customizing Agent
AgentScope provides two base classes, AgentBase and ReActAgentBase, which differ in the abstract methods they define and the hooks they support. Specifically, the ReActAgentBase extends AgentBase with additional _reasoning and _acting abstract methods, as well as their pre- and post- hooks.

Developers can choose to inherit from either of these base classes based on their needs. We summarize the agent under agentscope.agent module as follows:

Agent classes in AgentScope
Class

Abstract Method

Support Hooks

Description

AgentBase

reply
observe
print
handle_interrupt
pre_/post_reply
pre_/post_observe
pre_/post_print
The base class for all agents, providing the basic interface and hooks.

ReActAgentBase

reply
observe
print
handle_interrupt
_reasoning
_acting
pre_/post_reply
pre_/post_observe
pre_/post_print
pre_/post_reasoning
pre_/post_acting
The abstract class for ReAct agent, extending AgentBase with reasoning and acting abstract methods and their hooks.

ReActAgent

-

pre_/post_reply
pre_/post_observe
pre_/post_print
pre_/post_reasoning
pre_/post_acting
An implementation of ReActAgentBase

UserAgent

A special agent that represents the user, used to interact with the agent

A2aAgent

-

pre_/post_reply
pre_/post_observe
pre_/post_print
Agent for communicating with remote A2A agents, see A2A Agent






State/Session Management
In AgentScope, the “state” refers to the agent status in the running application, including its current system prompt, memory, context, equipped tools, and other information that change over time.

To manage the state of an application, AgentScope designs an automatic state registration system and session-level state management, which features:

Support automatic state registration for all variables inherited from StateModule

Support manual state registration with custom serialization/deserialization methods

Support session/application-level management

import asyncio
import json
import os

from agentscope.agent import ReActAgent
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.model import DashScopeChatModel
from agentscope.module import StateModule
from agentscope.session import JSONSession
from agentscope.tool import Toolkit
State Module
The StateModule class is the foundation for state management in AgentScope and provides three basic functions:

Methods of StateModule
Method

Arguments

Description

register_state

attr_name,
custom_to_json (optional),
custom_from_json (optional)
Register an attribute as its state, with optional serialization/deserialization function.

state_dict

-

Get the state dictionary of current object

load_state_dict

state_dict,
strict (optional)
Load the state dictionary to current object

Within an object of StateModule, all the following attributes will be treated as parts of its state:

the attributes that inherit from StateModule

the attributes registered by the register_state method

Note the StateModule supports NESTED serialization and deserialization:

class ClassA(StateModule):
    def __init__(self) -> None:
        super().__init__()
        self.cnt = 123
        # register cnt attribute as state
        self.register_state("cnt")


class ClassB(StateModule):
    def __init__(self) -> None:
        super().__init__()

        # attribute "a" inherits from StateModule
        self.a = ClassA()

        # register attribute "c" as state manually
        self.c = "Hello, world!"
        self.register_state("c")


obj_b = ClassB()

print("State of obj_b.a:")
print(obj_b.a.state_dict())

print("\nState of obj_b:")
print(json.dumps(obj_b.state_dict(), indent=4))
State of obj_b.a:
{'cnt': 123}

State of obj_b:
{
    "a": {
        "cnt": 123
    },
    "c": "Hello, world!"
}
We can observe the state of obj_b contains the state of its attribute a automatically.

In AgentScope, the AgentBase, MemoryBase, LongTermMemoryBase and Toolkit classes all inherit from StateModule, thus supporting automatic and nested state management.

# Creating an agent
agent = ReActAgent(
    name="Friday",
    sys_prompt="You're a assistant named Friday.",
    model=DashScopeChatModel(
        model_name="qwen-max",
        api_key=os.environ["DASHSCOPE_API_KEY"],
    ),
    formatter=DashScopeChatFormatter(),
    memory=InMemoryMemory(),
    toolkit=Toolkit(),
)

initial_state = agent.state_dict()

print("Initial state of the agent:")
print(json.dumps(initial_state, indent=4))
Initial state of the agent:
{
    "memory": {
        "content": []
    },
    "toolkit": {
        "active_groups": []
    },
    "name": "Friday",
    "_sys_prompt": "You're a assistant named Friday."
}
Then we change its state by generating a reply message:

async def example_agent_state() -> None:
    """Example of agent state management"""
    await agent(Msg("user", "Hello, agent!", "user"))

    print("State of the agent after generating a reply:")
    print(json.dumps(agent.state_dict(), indent=4))


asyncio.run(example_agent_state())
Friday: Hello! I'm Friday, your virtual assistant. How can I assist you today?
State of the agent after generating a reply:
{
    "memory": {
        "content": [
            [
                {
                    "id": "kgfJLZLWy5rijCo3YE5XNJ",
                    "name": "user",
                    "role": "user",
                    "content": "Hello, agent!",
                    "metadata": null,
                    "timestamp": "2026-01-27 08:07:55.784"
                },
                []
            ],
            [
                {
                    "id": "FyMej8urBg3vwdivpm3CNi",
                    "name": "Friday",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Hello! I'm Friday, your virtual assistant. How can I assist you today?"
                        }
                    ],
                    "metadata": null,
                    "timestamp": "2026-01-27 08:07:55.785"
                },
                []
            ]
        ]
    },
    "toolkit": {
        "active_groups": []
    },
    "name": "Friday",
    "_sys_prompt": "You're a assistant named Friday."
}
Now we recover the state of the agent to its initial state:

agent.load_state_dict(initial_state)

print("State after loading the initial state:")
print(json.dumps(agent.state_dict(), indent=4))
State after loading the initial state:
{
    "memory": {
        "content": []
    },
    "toolkit": {
        "active_groups": []
    },
    "name": "Friday",
    "_sys_prompt": "You're a assistant named Friday."
}
Session Management
In AgentScope, a session refers to a collection of StateModule in an application, e.g. multiple agents.

AgentScope provides a SessionBase class with two abstract methods for session management: save_session_state and load_session_state. Developers can implement these methods with their own storage solution.

In AgentScope, we provide a JSON based session class JSONSession that stores/loads the session state in/from a JSON file named with the session ID.

Here we show how to use the JSON based session management in AgentScope.

Saving Session State
# change the agent state by generating a reply message
asyncio.run(example_agent_state())

print("\nState of agent:")
print(json.dumps(agent.state_dict(), indent=4))
Friday: Hello! I'm Friday, your virtual assistant. How can I assist you today?
State of the agent after generating a reply:
{
    "memory": {
        "content": [
            [
                {
                    "id": "iZ5rU4uKdmPwJNh6g5fz6p",
                    "name": "user",
                    "role": "user",
                    "content": "Hello, agent!",
                    "metadata": null,
                    "timestamp": "2026-01-27 08:07:57.422"
                },
                []
            ],
            [
                {
                    "id": "ctGbQ2DEKpXNWAmomKLppj",
                    "name": "Friday",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Hello! I'm Friday, your virtual assistant. How can I assist you today?"
                        }
                    ],
                    "metadata": null,
                    "timestamp": "2026-01-27 08:07:57.422"
                },
                []
            ]
        ]
    },
    "toolkit": {
        "active_groups": []
    },
    "name": "Friday",
    "_sys_prompt": "You're a assistant named Friday."
}

State of agent:
{
    "memory": {
        "content": [
            [
                {
                    "id": "iZ5rU4uKdmPwJNh6g5fz6p",
                    "name": "user",
                    "role": "user",
                    "content": "Hello, agent!",
                    "metadata": null,
                    "timestamp": "2026-01-27 08:07:57.422"
                },
                []
            ],
            [
                {
                    "id": "ctGbQ2DEKpXNWAmomKLppj",
                    "name": "Friday",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Hello! I'm Friday, your virtual assistant. How can I assist you today?"
                        }
                    ],
                    "metadata": null,
                    "timestamp": "2026-01-27 08:07:57.422"
                },
                []
            ]
        ]
    },
    "toolkit": {
        "active_groups": []
    },
    "name": "Friday",
    "_sys_prompt": "You're a assistant named Friday."
}
Then we save it to a session file:

session = JSONSession(
    save_dir="./",  # The dir used to save the session files
)


async def example_session() -> None:
    """Example of session management."""
    await session.save_session_state(
        session_id="user_1",  # Use the name as the session id
        agent=agent,
    )

    print("The saved state:")
    with open("./user_1.json", "r", encoding="utf-8") as f:
        print(json.dumps(json.load(f), indent=4))


asyncio.run(example_session())
The saved state:
{
    "agent": {
        "memory": {
            "content": [
                [
                    {
                        "id": "iZ5rU4uKdmPwJNh6g5fz6p",
                        "name": "user",
                        "role": "user",
                        "content": "Hello, agent!",
                        "metadata": null,
                        "timestamp": "2026-01-27 08:07:57.422"
                    },
                    []
                ],
                [
                    {
                        "id": "ctGbQ2DEKpXNWAmomKLppj",
                        "name": "Friday",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": "Hello! I'm Friday, your virtual assistant. How can I assist you today?"
                            }
                        ],
                        "metadata": null,
                        "timestamp": "2026-01-27 08:07:57.422"
                    },
                    []
                ]
            ]
        },
        "toolkit": {
            "active_groups": []
        },
        "name": "Friday",
        "_sys_prompt": "You're a assistant named Friday."
    }
}
Loading Session State
Now we load the session state from the saved file:

async def example_load_session() -> None:
    """Example of loading session state."""

    # we first clear the memory of the agent
    await agent.memory.clear()

    print("Current state of the agent:")
    print(json.dumps(agent.state_dict(), indent=4))

    # then we load the session state
    await session.load_session_state(
        session_id="user_1",
        # The keyword argument must be the same as the one used in `save_session_state`
        agent=agent,
    )
    print("After loading the session state:")
    print(json.dumps(agent.state_dict(), indent=4))


asyncio.run(example_load_session())
Current state of the agent:
{
    "memory": {
        "content": []
    },
    "toolkit": {
        "active_groups": []
    },
    "name": "Friday",
    "_sys_prompt": "You're a assistant named Friday."
}
After loading the session state:
{
    "memory": {
        "content": [
            [
                {
                    "id": "iZ5rU4uKdmPwJNh6g5fz6p",
                    "name": "user",
                    "role": "user",
                    "content": "Hello, agent!",
                    "metadata": null,
                    "timestamp": "2026-01-27 08:07:57.422"
                },
                []
            ],
            [
                {
                    "id": "ctGbQ2DEKpXNWAmomKLppj",
                    "name": "Friday",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Hello! I'm Friday, your virtual assistant. How can I assist you today?"
                        }
                    ],
                    "metadata": null,
                    "timestamp": "2026-01-27 08:07:57.422"
                },
                []
            ]
        ]
    },
    "toolkit": {
        "active_groups": []
    },
    "name": "Friday",
    "_sys_prompt": "You're a assistant named Friday."
}
Now we can see the agent state is restored to the saved state.





Long-Term Memory
In AgentScope, we provide a basic class for long-term memory (LongTermMemoryBase) and an implementation based on the mem0 library (Mem0LongTermMemory). Together with the design of ReActAgent class in Agent section, we provide two long-term memory modes:

agent_control: the agent autonomously manages long-term memory by tool calls, and

static_control: the developer explicitly controls long-term memory operations.

Developers can also use the both mode, which activates both memory management modes.

Hint

These memory modes are suitable for different usage scenarios. Developers can choose the appropriate mode based on their needs.

Using mem0 Long-Term Memory
Note

We provide an example of using mem0 long-term memory in the GitHub repository under the examples/long_term_memory/mem0 directory.

import os
import asyncio

from agentscope.message import Msg
from agentscope.memory import InMemoryMemory
from agentscope.agent import ReActAgent
from agentscope.formatter import DashScopeChatFormatter
from agentscope.model import DashScopeChatModel
from agentscope.tool import Toolkit


# Create mem0 long-term memory instance
from agentscope.memory import Mem0LongTermMemory
from agentscope.embedding import DashScopeTextEmbedding


long_term_memory = Mem0LongTermMemory(
    agent_name="Friday",
    user_name="user_123",
    model=DashScopeChatModel(
        model_name="qwen-max-latest",
        api_key=os.environ.get("DASHSCOPE_API_KEY"),
        stream=False,
    ),
    embedding_model=DashScopeTextEmbedding(
        model_name="text-embedding-v2",
        api_key=os.environ.get("DASHSCOPE_API_KEY"),
    ),
    on_disk=False,
)
/opt/hostedtoolcache/Python/3.10.19/x64/lib/python3.10/site-packages/mem0/client/project.py:14: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
  class ProjectConfig(BaseModel):
The Mem0LongTermMemory class provides two main methods for long-term memory operations: record and retrieve. They take a list of messages as input and record/retrieve information from long-term memory.

As an example, we first store a user preference and then retrieve related information from long-term memory.

# Basic usage example
async def basic_usage():
    """Basic usage example"""
    # Record memory
    await long_term_memory.record(
        [Msg("user", "I like staying in homestays", "user")],
    )

    # Retrieve memory
    results = await long_term_memory.retrieve(
        [Msg("user", "My accommodation preferences", "user")],
    )
    print(f"Retrieval results: {results}")


asyncio.run(basic_usage())
Retrieval results: Likes staying in homestays
Integration with ReAct Agent
In AgentScope, the ReActAgent class receives a long_term_memory parameter in its constructor, as well as a long_term_memory_mode parameter that specifies the long-term memory mode.

If long_term_memory_mode is set to agent_control or both, two tool functions record_to_memory and retrieve_from_memory will be registered in the agent’s toolkit, allowing the agent to autonomously manage long-term memory through tool calls.

Note

To achieve the best results, the "agent_control" mode may require additional instructions in the system prompt.

# Create ReAct agent with long-term memory
agent = ReActAgent(
    name="Friday",
    sys_prompt="You are an assistant with long-term memory capabilities.",
    model=DashScopeChatModel(
        api_key=os.environ.get("DASHSCOPE_API_KEY"),
        model_name="qwen-max-latest",
    ),
    formatter=DashScopeChatFormatter(),
    toolkit=Toolkit(),
    memory=InMemoryMemory(),
    long_term_memory=long_term_memory,
    long_term_memory_mode="static_control",  # Use static_control mode
)


async def record_preferences():
    """ReAct agent integration example"""
    # Conversation example
    msg = Msg(
        "user",
        "When I travel to Hangzhou, I like staying in homestays",
        "user",
    )
    await agent(msg)


asyncio.run(record_preferences())
Friday: It sounds like you enjoy the cozy and personal experience that homestays offer when visiting Hangzhou! Homestays can indeed be a wonderful way to immerse yourself in the local culture, enjoy a more personalized stay, and even get insider tips from your hosts about hidden gems in the city.

If you're planning another trip to Hangzhou and looking for recommendations or help with finding great homestay options, I can definitely assist. Would you like me to suggest some popular neighborhoods or platforms where you can find unique homestays?
Then we clear the short-term memory and ask the agent about the user’s preferences.

async def retrieve_preferences():
    """Retrieve user preferences from long-term memory"""
    # Clear short-term memory
    await agent.memory.clear()
    # The agent will remember previous conversations
    msg2 = Msg("user", "What are my preferences? Answer briefly.", "user")
    await agent(msg2)


asyncio.run(retrieve_preferences())
Friday: You prefer staying in homestays, especially enjoying the experience of living in民宿 (homestays) in Hangzhou.
Using ReMe Long-Term Memory
Note

We provide an example of using ReMe long-term memory in the GitHub repository under the examples/long_term_memory/reme directory.

Example of ReMe long-term memory setup
from agentscope.memory import ReMePersonalLongTermMemory

# Create ReMe personal long-term memory instance
reme_long_term_memory = ReMePersonalLongTermMemory(
    agent_name="Friday",
    user_name="user_123",
    model=DashScopeChatModel(
        model_name="qwen3-max",
        api_key=os.environ.get("DASHSCOPE_API_KEY"),
        stream=False,
    ),
    embedding_model=DashScopeTextEmbedding(
        model_name="text-embedding-v4",
        api_key=os.environ.get("DASHSCOPE_API_KEY"),
        dimensions=1024,
    ),
)
The ReMePersonalLongTermMemory class provides four main methods for long-term memory operations. They include record_to_memory and retrieve_from_memory for tool calls, as well as record and retrieve for direct calls.

As an example, we use record_to_memory to record user preferences.

Example of recording to ReMe long-term memory
async def test_record_to_memory():
    """Test record_to_memory tool function interface"""
    async with reme_long_term_memory:
        result = await reme_long_term_memory.record_to_memory(
            thinking="The user is sharing their travel preferences and habits",
            content=[
                "I prefer to stay in homestays when traveling to Hangzhou",
                "I like to visit the West Lake in the morning",
                "I enjoy drinking Longjing tea",
            ],
        )
        # Extract result text
        result_text = " ".join(
            block.get("text", "")
            for block in result.content
            if block.get("type") == "text"
        )
        print(f"Recording result: {result_text}")
Then we use retrieve_from_memory to retrieve related memories.

Example of retrieving from ReMe long-term memory
async def test_retrieve_from_memory():
    """Test retrieve_from_memory tool function interface"""
    async with reme_long_term_memory:
        # First record some content
        await reme_long_term_memory.record_to_memory(
            thinking="User is sharing travel preferences",
            content=[
                "I prefer to stay in homestays when traveling to Hangzhou",
            ],
        )

        # Then retrieve
        result = await reme_long_term_memory.retrieve_from_memory(
            keywords=["Hangzhou travel", "tea preference"],
        )
        retrieved_text = " ".join(
            block.get("text", "")
            for block in result.content
            if block.get("type") == "text"
        )
        print(f"Retrieved memories: {retrieved_text}")
Besides the tool function interface, we can also use the record method to directly record message conversations.

Example of direct recording to ReMe long-term memory
async def test_record_direct():
    """Test record direct recording method"""
    async with reme_long_term_memory:
        await reme_long_term_memory.record(
            msgs=[
                Msg(
                    role="user",
                    content="I work as a software engineer and prefer remote work",
                    name="user",
                ),
                Msg(
                    role="assistant",
                    content="Understood! You're a software engineer who values remote work flexibility.",
                    name="assistant",
                ),
                Msg(
                    role="user",
                    content="I usually start my day at 9 AM with a cup of coffee",
                    name="user",
                ),
            ],
        )
        print("Successfully recorded conversation messages")
Similarly, we use the retrieve method to retrieve related memories.

Example of direct retrieval from ReMe long-term memory
async def test_retrieve_direct():
    """Test retrieve direct retrieval method"""
    async with reme_long_term_memory:
        # First record some content
        await reme_long_term_memory.record(
            msgs=[
                Msg(
                    role="user",
                    content="I work as a software engineer and prefer remote work",
                    name="user",
                ),
            ],
        )

        # Then retrieve
        memories = await reme_long_term_memory.retrieve(
            msg=Msg(
                role="user",
                content="What do you know about my work preferences?",
                name="user",
            ),
        )
        print(
            f"Retrieved memories: {memories if memories else 'No memories found'}",
        )
Integration with ReAct Agent
In AgentScope, the ReActAgent class receives a long_term_memory parameter in its constructor, as well as a long_term_memory_mode parameter.

If long_term_memory_mode is set to agent_control or both, record_to_memory and retrieve_from_memory tool functions will be registered, allowing the agent to autonomously manage long-term memory through tool calls.

Note

To achieve the best results, the "agent_control" mode may require additional instructions in the system prompt.

Example of ReAct agent with ReMe long-term memory
# Create ReAct agent with long-term memory (agent_control mode)
async def test_react_agent_with_reme():
    """Test ReActAgent integration with ReMe personal memory"""
    async with reme_long_term_memory:
        agent_with_reme = ReActAgent(
            name="Friday",
            sys_prompt=(
                "You are a helpful assistant named Friday with long-term memory capabilities. "
                "\n\n## Memory Management Guidelines:\n"
                "1. **Recording Memories**: When users share personal information, preferences, "
                "habits, or facts about themselves, ALWAYS record them using `record_to_memory` "
                "for future reference.\n"
                "\n2. **Retrieving Memories**: BEFORE answering questions about the user's preferences, "
                "past information, or personal details, you MUST FIRST call `retrieve_from_memory` "
                "to check if you have any relevant stored information. Do NOT rely solely on the "
                "current conversation context.\n"
                "\n3. **When to Retrieve**: Call `retrieve_from_memory` when:\n"
                "   - User asks questions like 'what do I like?', 'what are my preferences?', "
                "'what do you know about me?'\n"
                "   - User asks about their past behaviors, habits, or preferences\n"
                "   - User refers to information they mentioned before\n"
                "   - You need context about the user to provide personalized responses\n"
                "\nAlways check your memory first before claiming you don't know something about the user."
            ),
            model=DashScopeChatModel(
                model_name="qwen3-max",
                api_key=os.environ.get("DASHSCOPE_API_KEY"),
                stream=False,
            ),
            formatter=DashScopeChatFormatter(),
            toolkit=Toolkit(),
            memory=InMemoryMemory(),
            long_term_memory=reme_long_term_memory,
            long_term_memory_mode="agent_control",  # Use agent_control mode
        )

        # User shares preferences
        msg = Msg(
            role="user",
            content="When I travel to Hangzhou, I prefer to stay in a homestay",
            name="user",
        )
        response = await agent_with_reme(msg)
        print(f"Agent response: {response.get_text_content()}")

        # Clear short-term memory to test long-term memory
        await agent_with_reme.memory.clear()

        # Query preferences
        msg2 = Msg(
            role="user",
            content="what preference do I have?",
            name="user",
        )
        response2 = await agent_with_reme(msg2)
        print(f"Agent response: {response2.get_text_content()}")
Then we clear the short-term memory and ask the agent about the user’s preferences.

Example of retrieving preferences with ReAct agent and ReMe long-term memory
async def retrieve_reme_preferences():
    """Retrieve user preferences from long-term memory"""
    async with reme_long_term_memory:
        # Create agent (reusing for demonstration completeness)
        agent_with_reme = ReActAgent(
            name="Friday",
            sys_prompt="You are an assistant with long-term memory capabilities.",
            model=DashScopeChatModel(
                api_key=os.environ.get("DASHSCOPE_API_KEY"),
                model_name="qwen3-max",
                stream=False,
            ),
            formatter=DashScopeChatFormatter(),
            toolkit=Toolkit(),
            memory=InMemoryMemory(),
            long_term_memory=reme_long_term_memory,
            long_term_memory_mode="agent_control",
        )

        # Clear short-term memory
        await agent_with_reme.memory.clear()
        # The agent will remember previous conversations
        msg2 = Msg("user", "What are my preferences? Answer briefly.", "user")
        await agent_with_reme(msg2)
Customizing Long-Term Memory
AgentScope provides the LongTermMemoryBase base class, which defines the basic

Developers can inherit from LongTermMemoryBase to implement custom long-term memory systems according to their needs：

Long-term memory classes in AgentScope
Class

Abstract Methods

Description

LongTermMemoryBase

record
retrieve
record_to_memory
retrieve_from_memory
For "static_control" mode, you must implement the record and retrieve methods.

For "agent_control" mode, the record_to_memory and retrieve_from_memory methods must be implemented.

Mem0LongTermMemory

record
retrieve
record_to_memory
retrieve_from_memory
Long-term memory implementation based on the mem0 library, supporting vector storage and retrieval.

ReMePersonalLongTermMemory

record
retrieve
record_to_memory
retrieve_from_memory
Personal memory implementation based on the ReMe framework, providing powerful memory management and retrieval capabilities.





Tool
To ensure accurate and reliable tool parsing, AgentScope fully embraces the use of tools API with the following features:

Support automatic tool parsing from Python functions with their docstrings

Support both synchronous and asynchronous tool functions

Support streaming tool responses (either synchronous or asynchronous generators)

Support dynamic extension to the tool JSON Schema

Support interrupting the tool execution with proper signal handling

Support autonomous tool management by agents

All above features are implemented by the Toolkit class in AgentScope, which is responsible for managing tool functions and their execution.

Tip

The support of MCP (Model Context Protocol) refers to the MCP section.

import asyncio
import inspect
import json
from typing import Any, AsyncGenerator

from pydantic import BaseModel, Field

import agentscope
from agentscope.message import TextBlock, ToolUseBlock
from agentscope.tool import ToolResponse, Toolkit, execute_python_code
Tool Function
In AgentScope, a tool function is a Python function that

returns a ToolResponse object or a generator that yields ToolResponse objects

has a docstring that describes the tool’s functionality and parameters

A template of a tool function is as follows:

def tool_function(a: int, b: str) -> ToolResponse:
    """{function description}

    Args:
        a (int):
            {description of the first parameter}
        b (str):
            {description of the second parameter}
    """
Tip

Instance method and class method can also be used as tool functions, and the self and cls parameters will be ignored.

AgentScope provides several built-in tool functions under the agentscope.tool module, such as execute_python_code, execute_shell_command and text file write/read functions.

print("Built-in Tool Functions:")
for _ in agentscope.tool.__all__:
    if _ not in ["Toolkit", "ToolResponse"]:
        print(_)
Built-in Tool Functions:
execute_python_code
execute_shell_command
view_text_file
write_text_file
insert_text_file
dashscope_text_to_image
dashscope_text_to_audio
dashscope_image_to_text
openai_text_to_image
openai_text_to_audio
openai_edit_image
openai_create_image_variation
openai_image_to_text
openai_audio_to_text
Toolkit
The Toolkit class is designed to manage tool functions, extracting their JSON Schema from docstrings and providing a unified interface for tool execution.

Basic Usage
The basic functionality of the Toolkit class is to register tool functions and execute them.

# Prepare a custom tool function
async def my_search(query: str, api_key: str) -> ToolResponse:
    """A simple example tool function.

    Args:
        query (str):
            The search query.
        api_key (str):
            The API key for authentication.
    """
    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=f"Searching for '{query}' with API key '{api_key}'",
            ),
        ],
    )


# Register the tool function in a toolkit
toolkit = Toolkit()
toolkit.register_tool_function(my_search)
When registering a tool function, you can get its JSON Schema by calling the get_json_schemas method.

print("Tool JSON Schemas:")
print(json.dumps(toolkit.get_json_schemas(), indent=4, ensure_ascii=False))
Tool JSON Schemas:
[
    {
        "type": "function",
        "function": {
            "name": "my_search",
            "parameters": {
                "properties": {
                    "query": {
                        "description": "The search query.",
                        "type": "string"
                    },
                    "api_key": {
                        "description": "The API key for authentication.",
                        "type": "string"
                    }
                },
                "required": [
                    "query",
                    "api_key"
                ],
                "type": "object"
            },
            "description": "A simple example tool function."
        }
    }
]
Toolkit also allows developers to preset the arguments for tool functions, especially useful for API keys or other sensitive information.

# Clear the toolkit first
toolkit.clear()

# Register tool function with preset keyword arguments
toolkit.register_tool_function(my_search, preset_kwargs={"api_key": "xxx"})

print("Tool JSON Schemas with Preset Arguments:")
print(json.dumps(toolkit.get_json_schemas(), indent=4, ensure_ascii=False))
Tool JSON Schemas with Preset Arguments:
[
    {
        "type": "function",
        "function": {
            "name": "my_search",
            "parameters": {
                "properties": {
                    "query": {
                        "description": "The search query.",
                        "type": "string"
                    }
                },
                "required": [
                    "query"
                ],
                "type": "object"
            },
            "description": "A simple example tool function."
        }
    }
]
In Toolkit, the call_tool_function method takes a tool use block as input and executes the corresponding tool function, returning a unified asynchronous generator that yields ToolResponse objects.

async def example_tool_execution() -> None:
    """Example of executing a tool call."""
    res = await toolkit.call_tool_function(
        ToolUseBlock(
            type="tool_use",
            id="123",
            name="my_search",
            input={"query": "AgentScope"},
        ),
    )

    # Only one tool response is expected in this case
    print("Tool Response:")
    async for tool_response in res:
        print(tool_response)


asyncio.run(example_tool_execution())
Tool Response:
ToolResponse(content=[{'type': 'text', 'text': "Searching for 'AgentScope' with API key 'xxx'"}], metadata=None, stream=False, is_last=True, is_interrupted=False, id='2026-01-27 08:10:25.663_ff6bd2')
Extending JSON Schema Dynamically
Toolkit allows to extend the JSON schemas of tool functions dynamically by calling the set_extended_model method. Such feature allows to add more parameters to the tool function without modifying its original definition.

Tip

Related scenarios include dynamic structured-output and CoT (Chain of Thought) reasoning

Note

The function to be extended should accept variable keyword arguments (**kwargs), so that the additional fields can be passed to it.

Taking the CoT reasoning as an example, we can extend all tool functions with a thinking field, allowing the agent to summarize the current state and then decide what to do next.

# Example tool function
def tool_function(**kwargs: Any) -> ToolResponse:
    """A tool function"""
    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=f"Received parameters: {kwargs}",
            ),
        ],
    )


# Add a thinking field so that the agent could think before giving the other parameters.
class ThinkingModel(BaseModel):
    """A Pydantic model for additional fields."""

    thinking: str = Field(
        description="Summarize the current state and decide what to do next.",
    )


# Register
toolkit.set_extended_model("my_search", ThinkingModel)

print("The extended JSON Schema:")
print(json.dumps(toolkit.get_json_schemas(), indent=4, ensure_ascii=False))
The extended JSON Schema:
[
    {
        "type": "function",
        "function": {
            "name": "my_search",
            "parameters": {
                "properties": {
                    "query": {
                        "description": "The search query.",
                        "type": "string"
                    },
                    "thinking": {
                        "description": "Summarize the current state and decide what to do next.",
                        "type": "string"
                    }
                },
                "required": [
                    "query",
                    "thinking"
                ],
                "type": "object"
            },
            "description": "A simple example tool function."
        }
    }
]
Interrupting Tool Execution
The Toolkit class supports execution interruption of async tool functions and provides a comprehensive agent-oriented post-processing mechanism. Such interruption is implemented based on the asyncio cancellation mechanism, and the post-processing varies depending on the return type of tool function.

Note

For synchronous tool functions, their execution cannot be interrupted by asyncio cancellation. So the interruption is handled within the agent rather than the toolkit. Refer to the Agent section for more information.

Specifically, if the tool function returns a ToolResponse object, a predefined ToolResponse object with an interrupted message will be yielded. So that the agent can observe the interruption and handle it accordingly. Besides, a flag is_interrupted will be set to True in the response, and the external caller can decide whether to throw the CancelledError exception to the outer layer.

An example of async tool function that can be interrupted is as follows:

async def non_streaming_function() -> ToolResponse:
    """A non-streaming tool function that can be interrupted."""
    await asyncio.sleep(1)  # Simulate a long-running task

    # Fake interruption for demonstration
    raise asyncio.CancelledError()

    # The following code won't be executed due to the cancellation
    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text="Run successfully!",
            ),
        ],
    )


async def example_tool_interruption() -> None:
    """Example of tool interruption."""
    toolkit = Toolkit()
    toolkit.register_tool_function(non_streaming_function)
    res = await toolkit.call_tool_function(
        ToolUseBlock(
            type="tool_use",
            id="123",
            name="non_streaming_function",
            input={},
        ),
    )

    async for tool_response in res:
        print("Tool Response:")
        print(tool_response)
        print("The interrupted flag:")
        print(tool_response.is_interrupted)


asyncio.run(example_tool_interruption())
Tool Response:
ToolResponse(content=[{'type': 'text', 'text': '<system-info>The tool call has been interrupted by the user.</system-info>'}], metadata=None, stream=True, is_last=True, is_interrupted=True, id='2026-01-27 08:10:26.667_4ad171')
The interrupted flag:
True
For streaming tool functions, which returns an asynchronous generator, the Toolkit will attach the interrupted message to the previous chunk of the response. By this way, the agent can observe what the tool has returned before the interruption.

The example of interrupting a streaming tool function is as follows:

async def streaming_function() -> AsyncGenerator[ToolResponse, None]:
    """A streaming tool function that can be interrupted."""
    # Simulate a chunk of response
    yield ToolResponse(
        content=[
            TextBlock(
                type="text",
                text="1234",
            ),
        ],
        stream=True,
    )

    # Simulate interruption
    raise asyncio.CancelledError()

    # The following code won't be executed due to the cancellation
    yield ToolResponse(
        content=[
            TextBlock(
                type="text",
                text="123456789",
            ),
        ],
    )


async def example_streaming_tool_interruption() -> None:
    """Example of streaming tool interruption."""
    toolkit = Toolkit()
    toolkit.register_tool_function(streaming_function)

    res = await toolkit.call_tool_function(
        ToolUseBlock(
            type="tool_use",
            id="xxx",
            name="streaming_function",
            input={},
        ),
    )

    i = 0
    async for tool_response in res:
        print(f"Chunk {i}:")
        print(tool_response)
        print("The interrupted flag: ", tool_response.is_interrupted, "\n")
        i += 1


asyncio.run(example_streaming_tool_interruption())
Chunk 0:
ToolResponse(content=[{'type': 'text', 'text': '1234'}], metadata=None, stream=True, is_last=True, is_interrupted=False, id='2026-01-27 08:10:26.669_b17e19')
The interrupted flag:  False

Chunk 1:
ToolResponse(content=[{'type': 'text', 'text': '1234'}, {'type': 'text', 'text': '<system-info>The tool call has been interrupted by the user.</system-info>'}], metadata=None, stream=True, is_last=True, is_interrupted=True, id='2026-01-27 08:10:26.669_b17e19')
The interrupted flag:  True
Automatic Tool Management
Automatic Tool Management
The Toolkit class supports automatic tool management by introducing the concept of tool group, as well as a meta tool function named reset_equipped_tools.

The tool group is a set of related tool functions, e.g. browser-use tools, map services tools, etc., which will be managed together. Only the tools in the activated groups will be visible to agents, i.e. accessible by the toolkit.get_json_schemas() method.

Note there is a special group called basic, which is always activated and the tools registered without specifying the group name will be added to this group by default.

Tip

The basic group ensures that the basic usage of tools won’t be affected by the group features if you don’t need them.

Now we try to create a tool group named browser_use, which contains some web browsing tools.

def navigate(url: str) -> ToolResponse:
    """Navigate to a web page.

    Args:
        url (str):
            The URL of the web page to navigate to.
    """
    pass


def click_element(element_id: str) -> ToolResponse:
    """Click an element on the web page.

    Args:
        element_id (str):
            The ID of the element to click.
    """
    pass


toolkit = Toolkit()

# Create a tool group named browser_use
toolkit.create_tool_group(
    group_name="browser_use",
    description="The tool functions for web browsing.",
    active=False,
    # The notes when using these tools
    notes="""1. Use ``navigate`` to open a web page.
2. When requiring user authentication, ask the user for the credentials
3. ...""",
)

toolkit.register_tool_function(navigate, group_name="browser_use")
toolkit.register_tool_function(click_element, group_name="browser_use")

# We can also register some basic tools
toolkit.register_tool_function(execute_python_code)
If we check the tools JSON schema, we can only see the execute_python_code tool, because the browser_use group is not activated yet:

print("Tool JSON Schemas with Group:")
print(json.dumps(toolkit.get_json_schemas(), indent=4, ensure_ascii=False))
Tool JSON Schemas with Group:
[
    {
        "type": "function",
        "function": {
            "name": "execute_python_code",
            "parameters": {
                "properties": {
                    "code": {
                        "description": "The Python code to be executed.",
                        "type": "string"
                    },
                    "timeout": {
                        "default": 300,
                        "description": "The maximum time (in seconds) allowed for the code to run.",
                        "type": "number"
                    }
                },
                "required": [
                    "code"
                ],
                "type": "object"
            },
            "description": "Execute the given python code in a temp file and capture the return\ncode, standard output and error. Note you must `print` the output to get\nthe result, and the tmp file will be removed right after the execution."
        }
    }
]
Use the update_tool_groups method to activate or deactivate tool groups:

toolkit.update_tool_groups(group_names=["browser_use"], active=True)

print("Tool JSON Schemas with Group:")
print(json.dumps(toolkit.get_json_schemas(), indent=4, ensure_ascii=False))
Tool JSON Schemas with Group:
[
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "parameters": {
                "properties": {
                    "url": {
                        "description": "The URL of the web page to navigate to.",
                        "type": "string"
                    }
                },
                "required": [
                    "url"
                ],
                "type": "object"
            },
            "description": "Navigate to a web page."
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "parameters": {
                "properties": {
                    "element_id": {
                        "description": "The ID of the element to click.",
                        "type": "string"
                    }
                },
                "required": [
                    "element_id"
                ],
                "type": "object"
            },
            "description": "Click an element on the web page."
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_python_code",
            "parameters": {
                "properties": {
                    "code": {
                        "description": "The Python code to be executed.",
                        "type": "string"
                    },
                    "timeout": {
                        "default": 300,
                        "description": "The maximum time (in seconds) allowed for the code to run.",
                        "type": "number"
                    }
                },
                "required": [
                    "code"
                ],
                "type": "object"
            },
            "description": "Execute the given python code in a temp file and capture the return\ncode, standard output and error. Note you must `print` the output to get\nthe result, and the tmp file will be removed right after the execution."
        }
    }
]
Additionally, Toolkit provides a meta tool function named reset_equipped_tools, taking the current group names as the argument to indicate which groups to activate:

Note

In ReActAgent class, you can enable the meta tool function by setting enable_meta_tool=True in the constructor.

# Register the meta tool function
toolkit.register_tool_function(toolkit.reset_equipped_tools)

reset_equipped = next(
    tool
    for tool in toolkit.get_json_schemas()
    if tool["function"]["name"] == "reset_equipped_tools"
)
print("JSON schema of the ``reset_equipped_tools`` function:")
print(
    json.dumps(
        reset_equipped,
        indent=4,
        ensure_ascii=False,
    ),
)
JSON schema of the ``reset_equipped_tools`` function:
{
    "type": "function",
    "function": {
        "name": "reset_equipped_tools",
        "parameters": {
            "properties": {
                "browser_use": {
                    "default": false,
                    "description": "The tool functions for web browsing.",
                    "type": "boolean"
                }
            },
            "type": "object"
        },
        "description": "This function allows you to activate or deactivate tool groups\ndynamically based on your current task requirements.\n**Important: Each call sets the absolute final state of ALL tool\ngroups, not incremental changes**. Any group not explicitly set to True\nwill be deactivated, regardless of its previous state.\n\n**Best practice**: Actively manage your tool groups——activate only\nwhat you need for the current task, and promptly deactivate groups as\nsoon as they are no longer needed to conserve context space.\n\nThe function will return the usage instructions for the activated tool\ngroups, which you **MUST pay attention to and follow**. You can also\nreuse this function to check the notes of the tool groups."
    }
}
When agent calls the reset_equipped_tools function, the corresponding tool groups will be activated, and the tool response will contain the notes of the activated tool groups.

async def mock_agent_reset_tools() -> None:
    """Mock agent to reset tool groups."""
    # Call the meta tool function
    res = await toolkit.call_tool_function(
        ToolUseBlock(
            type="tool_use",
            id="154",
            name="reset_equipped_tools",
            input={
                "browser_user": True,
            },
        ),
    )

    async for tool_response in res:
        print("Text content in tool Response:")
        print(tool_response)


asyncio.run(mock_agent_reset_tools())
Text content in tool Response:
ToolResponse(content=[{'type': 'text', 'text': "Now tool groups 'browser_user' are activated."}], metadata=None, stream=False, is_last=True, is_interrupted=False, id='2026-01-27 08:10:26.676_d00167')
The toolkit also provides a method to gather the notes of the activated tool groups, and you can assemble it into your agent’s system prompt.

Tip

The automatic tool management feature is already implemented in the ReActAgent class, refer to the Agent section for more details.

# Create one more tool group
toolkit.create_tool_group(
    group_name="map_service",
    description="The google map service tools.",
    active=True,
    notes="""1. Use ``get_location`` to get the location of a place.
2. ...""",
)

print("The gathered notes of the activated tool groups:")
print(toolkit.get_activated_notes())
The gathered notes of the activated tool groups:
## About Tool Group 'map_service'
1. Use ``get_location`` to get the location of a place.
2. ...