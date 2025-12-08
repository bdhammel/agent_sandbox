from __future__ import annotations

import inspect
from collections.abc import AsyncIterable, Awaitable, Callable, Sequence
from typing import Any, TypeAlias

from pydantic_graph.beta.graph import EndMarker
from typing_extensions import TypeVar

from pydantic_ai import (
    Agent as _Agent,
    _agent_graph,
    messages as _messages,
    models,
    usage as _usage,
)
from pydantic_ai._agent_graph import ModelRequestNode
from pydantic_ai.builtin_tools import AbstractBuiltinTool
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.output import OutputSpec
from pydantic_ai.result import FinalResult
from pydantic_ai.run import AgentRun, AgentRunResult
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import AgentDepsT, DeferredToolResults, RunContext
from pydantic_ai.toolsets import AbstractToolset

RunOutputDataT = TypeVar('RunOutputDataT')
"""Type variable for the result data of a run where `output_type` was customized on the run call."""

EventStreamHandler: TypeAlias = Callable[
    [RunContext[AgentDepsT], AsyncIterable[_messages.AgentStreamEvent]], Awaitable[None]
]
"""A function that receives agent RunContext and an async iterable of events from the model's streaming response and the agent's execution of tools."""

Instructions: TypeAlias = (
    str
    | Callable[[RunContext[AgentDepsT]], str | None]
    | Sequence[str | Callable[[RunContext[AgentDepsT]], str | None]]
    | None
)


def early_exit_if_terminal_node(
    node: _agent_graph.AgentNode,
    agent_run: AgentRun,
    terminal_tools: set[str],
) -> FinalResult | None:
    """Check if node contains a terminal tool return and exit early if so.

    When a ModelRequestNode contains a ToolReturnPart for a tool registered
    as terminal, this function creates a FinalResult with the tool's output
    and sets it on the agent_run so that agent_run.result works correctly.

    Args:
        node: The current node from the agent iteration.
        agent_run: The AgentRun instance to set the result on.
        terminal_tools: Set of tool names that should trigger early exit.

    Returns:
        FinalResult if early exit was triggered, None otherwise.
    """
    if not isinstance(node, ModelRequestNode):
        return None

    for part in node.request.parts:
        if isinstance(part, ToolReturnPart) and part.tool_name in terminal_tools:
            final_result = FinalResult(
                output=part.content,
                tool_name=part.tool_name,
                tool_call_id=part.tool_call_id,
            )
            # Set the EndMarker so agent_run.result works correctly
            agent_run._graph_run._next = EndMarker(final_result)
            return final_result

    return None


class Agent(_Agent):
    """Extended Agent with terminal tool support.

    Attributes:
        terminal_tools: Set of tool names that trigger early exit when they return.
            When a tool in this set returns, the agent run ends immediately with
            the tool's output as the final result, skipping any further model calls.
    """

    terminal_tools: set[str] = set()

    async def run(
        self,
        user_prompt: str | Sequence[_messages.UserContent] | None = None,
        *,
        output_type: OutputSpec[RunOutputDataT] | None = None,
        message_history: Sequence[_messages.ModelMessage] | None = None,
        deferred_tool_results: DeferredToolResults | None = None,
        model: models.Model | models.KnownModelName | str | None = None,
        instructions: Instructions[AgentDepsT] = None,
        deps: AgentDepsT = None,
        model_settings: ModelSettings | None = None,
        usage_limits: _usage.UsageLimits | None = None,
        usage: _usage.RunUsage | None = None,
        infer_name: bool = True,
        toolsets: Sequence[AbstractToolset[AgentDepsT]] | None = None,
        builtin_tools: Sequence[AbstractBuiltinTool] | None = None,
        event_stream_handler: EventStreamHandler[AgentDepsT] | None = None,
    ) -> AgentRunResult[Any]:
        """Run the agent with a user prompt in async mode.

        This method builds an internal agent graph (using system prompts, tools and output schemas) and then
        runs the graph to completion. The result of the run is returned.

        Example:
        ```python
        from pydantic_ai import Agent

        agent = Agent('openai:gpt-4o')

        async def main():
            agent_run = await agent.run('What is the capital of France?')
            print(agent_run.output)
            #> The capital of France is Paris.
        ```

        Args:
            user_prompt: User input to start/continue the conversation.
            output_type: Custom output type to use for this run, `output_type` may only be used if the agent has no
                output validators since output validators would expect an argument that matches the agent's output type.
            message_history: History of the conversation so far.
            deferred_tool_results: Optional results for deferred tool calls in the message history.
            model: Optional model to use for this run, required if `model` was not set when creating the agent.
            instructions: Optional additional instructions to use for this run.
            deps: Optional dependencies to use for this run.
            model_settings: Optional settings to use for this model's request.
            usage_limits: Optional limits on model request count or token usage.
            usage: Optional usage to start with, useful for resuming a conversation or agents used in tools.
            infer_name: Whether to try to infer the agent name from the call frame if it's not set.
            toolsets: Optional additional toolsets for this run.
            event_stream_handler: Optional handler for events from the model's streaming response and the agent's execution of tools to use for this run.
            builtin_tools: Optional additional builtin tools for this run.

        Returns:
            The result of the run.
        """
        if infer_name and self.name is None:
            self._infer_name(inspect.currentframe())

        event_stream_handler = event_stream_handler or self.event_stream_handler

        calls = []

        async with self.iter(
            user_prompt=user_prompt,
            output_type=output_type,
            message_history=message_history,
            deferred_tool_results=deferred_tool_results,
            model=model,
            instructions=instructions,
            deps=deps,
            model_settings=model_settings,
            usage_limits=usage_limits,
            usage=usage,
            toolsets=toolsets,
            builtin_tools=builtin_tools,
        ) as agent_run:
            async for node in agent_run:
                calls.append(str(node))

                # Check for early exit on terminal tool return
                if self.terminal_tools and early_exit_if_terminal_node(
                    node, agent_run, self.terminal_tools
                ):
                    break

                if event_stream_handler is not None and (
                    self.is_model_request_node(node) or self.is_call_tools_node(node)
                ):
                    async with node.stream(agent_run.ctx) as stream:
                        await event_stream_handler(_agent_graph.build_run_context(agent_run.ctx), stream)

        print('\n\n'.join(calls))
        assert agent_run.result is not None, 'The graph run did not finish properly'
        return agent_run.result
