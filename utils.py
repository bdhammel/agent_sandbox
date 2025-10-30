"""Helper functions for converting between PydanticAI and AG-UI message formats."""

from __future__ import annotations

import json
import uuid

from ag_ui.core import (
    AssistantMessage,
    BaseMessage,
    DeveloperMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from ag_ui.core.types import FunctionCall, ToolCall
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)


from typing import Any, Dict


class EventMessage(BaseMessage):
    """Message representing a single event (STATE_SNAPSHOT or CUSTOM).
    
    Used to represent individual events from PydanticAI metadata
    as displayable messages in AG-UI format.
    """
    role: str = "event"
    tool_call_id: str
    content: Dict[str, Any]  # type: ignore[assignment]


def _process_user_prompt_part(part: UserPromptPart) -> UserMessage:
    """Create a UserMessage from a UserPromptPart.

    Args:
        part: The UserPromptPart to convert

    Returns:
        A UserMessage object
    """
    # We only support string content at this time.
    # Multi-modal content (images, audio, etc.) is not yet supported.
    if not isinstance(part.content, str):
        raise TypeError(
            "Multi-modal content is not supported. UserPromptPart.content must be a string."
        )

    return UserMessage(
        id=str(uuid.uuid4()),
        role="user",
        content=part.content,
    )


def _process_tool_return_part(part: ToolReturnPart) -> ToolMessage:
    """Create a ToolMessage from a ToolReturnPart.

    Args:
        part: The ToolReturnPart to convert

    Returns:
        A ToolMessage object
    """
    content = part.content if isinstance(part.content, str) else json.dumps(part.content)
    return ToolMessage(
        id=str(uuid.uuid4()),
        role="tool",
        content=content,
        tool_call_id=part.tool_call_id,
    )


def _extract_metadata_events(part: ToolReturnPart) -> list[dict]:
    """Extract STATE_SNAPSHOT and CUSTOM events from ToolReturnPart metadata.

    Args:
        part: The ToolReturnPart to extract events from

    Returns:
        List of event dictionaries with type, and other relevant fields
    """
    events = []
    if not hasattr(part, 'metadata') or not part.metadata:
        return events
    
    for meta in part.metadata:
        if not isinstance(meta, dict):
            continue
        
        event_type = meta.get('type')
        if event_type in ['STATE_SNAPSHOT', 'CUSTOM']:
            events.append(meta)
    
    return events


def _process_model_request(
    msg: ModelRequest,
    convert_events: bool = False,
) -> list[UserMessage | ToolMessage | EventMessage]:
    """Process a ModelRequest and convert to AG-UI messages.

    Args:
        msg: The ModelRequest to process
        convert_events: If True, extract metadata events and create separate EventMessages

    Returns:
        List of UserMessage, ToolMessage, and optionally EventMessage objects
    """
    messages: list[UserMessage | ToolMessage | EventMessage] = []
    
    for part in msg.parts:
        if isinstance(part, UserPromptPart) and part.content:
            messages.append(_process_user_prompt_part(part))
        elif isinstance(part, ToolReturnPart):
            # If convert_events is True, create separate EventMessages for each event
            if convert_events:
                events = _extract_metadata_events(part)
                for event in events:
                    messages.append(
                        EventMessage(
                            id=str(uuid.uuid4()),
                            role="event",
                            tool_call_id=part.tool_call_id,
                            content=event,
                        )
                    )
            
            # Always add the tool message
            messages.append(_process_tool_return_part(part))
    
    return messages


def _create_assistant_messages(
    tool_calls: list[ToolCall], text_content: str
) -> list[AssistantMessage]:
    """Create assistant messages based on tool calls and text content.

    Args:
        tool_calls: List of tool calls
        text_content: Text content from the assistant

    Returns:
        List of AssistantMessage objects
    """
    if tool_calls and text_content:
        # Split into two messages if we have both
        return [
            AssistantMessage(
                id=str(uuid.uuid4()),
                role="assistant",
                content="",
                tool_calls=tool_calls,
            ),
            AssistantMessage(
                id=str(uuid.uuid4()),
                role="assistant",
                content=text_content,
            ),
        ]
    if tool_calls:
        return [
            AssistantMessage(
                id=str(uuid.uuid4()),
                role="assistant",
                content="",
                tool_calls=tool_calls,
            )
        ]
    if text_content:
        return [
            AssistantMessage(
                id=str(uuid.uuid4()),
                role="assistant",
                content=text_content,
            )
        ]
    return []


def _process_model_response(msg: ModelResponse) -> list[AssistantMessage]:
    """Process a ModelResponse and convert to AG-UI messages.

    Args:
        msg: The ModelResponse to process

    Returns:
        List of AssistantMessage objects
    """
    tool_calls: list[ToolCall] = []
    text_content: str = ""

    for part in msg.parts:
        if isinstance(part, ToolCallPart):
            tool_call = ToolCall(
                id=part.tool_call_id,
                function=FunctionCall(
                    name=part.tool_name,
                    arguments=part.args if isinstance(part.args, str) else json.dumps(part.args),
                ),
            )
            tool_calls.append(tool_call)
        elif isinstance(part, TextPart) and part.content:
            text_content = part.content

    return _create_assistant_messages(tool_calls, text_content)


def pydantic_ai2ag_ui(
    messages: list[ModelMessage],
    convert_events: bool = False,
) -> list[DeveloperMessage | SystemMessage | AssistantMessage | UserMessage | ToolMessage | EventMessage]:
    """Convert stored conversation messages to AG-UI format.

    This converts PydanticAI ModelMessage objects to AG-UI typed message objects.
    It handles all message types including tool calls and tool returns, and properly
    splits messages that contain both tool calls and text content.

    Args:
        messages: List of ModelMessage objects
        convert_events: If True, extract metadata events (STATE_SNAPSHOT, CUSTOM) from
            ToolReturnPart and render as EventMessage with events field

    Returns:
        List of AG-UI formatted messages
    """
    full_messages: list[
        DeveloperMessage | SystemMessage | AssistantMessage | UserMessage | ToolMessage | EventMessage
    ] = []

    for msg in messages:
        if isinstance(msg, ModelRequest):
            full_messages.extend(_process_model_request(msg, convert_events=convert_events))
        elif isinstance(msg, ModelResponse):
            full_messages.extend(_process_model_response(msg))

    return full_messages
