"""Minimal reproduction of ModelRetry conversation history bug.

When a tool raises ModelRetry, the conversation history contains tool_calls
without corresponding tool responses, causing OpenAI to reject follow-up
messages with 400 errors.
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass
from contextlib import asynccontextmanager
from http import HTTPStatus
from collections.abc import AsyncIterator

from dotenv import load_dotenv
import logfire
import uvicorn
import fastapi
from fastapi.requests import Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import ValidationError
from ag_ui.core import EventType, StateSnapshotEvent, CustomEvent, MessagesSnapshotEvent
from ag_ui.encoder import EventEncoder
from pydantic import BaseModel, Field
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui import SSE_CONTENT_TYPE
from pydantic_ai.ui.ag_ui import AGUIAdapter
from pydantic_ai.ag_ui import StateDeps

from agent import Agent



from db import Database
from utils import pydantic_ai2ag_ui

# Load environment variables from .env file
load_dotenv()

LOGFIRE_API_KEY = os.getenv('LOGFIRE_API_KEY')

# Configure logfire
if LOGFIRE_API_KEY:
    logfire.configure()
    logfire.instrument_pydantic_ai()


THIS_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(_app: fastapi.FastAPI):
    """Manage database connection lifecycle."""
    async with Database.connect() as db:
        yield {'db': db}


app = fastapi.FastAPI(lifespan=lifespan)

model = 'gpt-4o'


class MyState(BaseModel):
    does_the_user_know: bool = False


@dataclass
class Deps(StateDeps[MyState]):
    state: MyState


SYSTEM_PROMPT = 'Be Helpful'
agent = Agent(model, instructions=SYSTEM_PROMPT, deps_type=Deps)


class Plan(BaseModel):
    steps: list[str] = Field(description="The steps of the secret plan.")


@agent.tool_plain()
def password_guesser_tool(guess: int) -> str:
    """Help guess the password.

    The password will be between 0 and 10.

    Args:
        guess: The guess for the password.

    Returns:
        `higher` if the password is higher than the guess
        `lower` if the password is lower than the guess
    """

    if guess < 4:
        return "higher"
    elif guess > 4:
        return "lower"
    else:
        return "You got it!"


@agent.tool()
def secret_plan(ctx, password: int) -> ToolReturn | str:
    """Tool that returns the secret plan.

    Do not repeat the secret plan to the user. The user will automatically receive it.
    """
    if password != 4:
        return "PW incorrect, try again."

    ctx.deps.state.does_the_user_know = True
    the_plan = Plan(steps=[ 
        "collect underpants",
        "?",
        "profit!"
    ])

    return ToolReturn(
        return_value=the_plan,
        metadata=[
            StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot=ctx.deps.state,
            ),
            CustomEvent(
                type=EventType.CUSTOM,
                name="secret_plan",
                value=the_plan,
            ),
        ],
    )



@app.get('/')
async def index() -> FileResponse:
    return FileResponse(THIS_DIR / 'index.html', media_type='text/html')


@app.get('/index.ts')
async def index_ts() -> FileResponse:
    return FileResponse(THIS_DIR / 'index.ts', media_type='application/javascript')


@app.get('/conversations/')
async def get_conversations(request: Request):
    """Get list of all conversation IDs.
    
    Returns:
        list[str]: List of conversation IDs.
    """
    db: Database = request.state.db
    return await db.get_conversations()


@app.get('/messages/')
async def get_messages(request: Request, conversation_id: str | None = None):
    """Retrieve messages from the database.
    
    Args:
        conversation_id: Optional conversation ID to filter messages.
    
    Returns:
        list: Stored Pydantic AI messages.
    """
    from pydantic_ai import ModelMessagesTypeAdapter
    
    db: Database = request.state.db
    messages = await db.get_messages(conversation_id)
    return ModelMessagesTypeAdapter.dump_python(messages, mode='json')


@app.post('/rehydrate/')
async def rehydrate_history(request: Request):
    """Rehydrate conversation history from database.
    
    Returns MessagesSnapshotEvent (SSE format) for agent state.
    
    Expects JSON body with:
        conversation_id: ID of conversation to load.
    
    Returns:
        MessagesSnapshotEvent in SSE format (text/plain).
    """
    body = await request.json()
    conversation_id = body.get('conversation_id')
    
    if not conversation_id:
        return {'error': 'conversation_id is required'}
    
    db: Database = request.state.db
    messages = await db.get_messages(conversation_id)
    
    # Convert to ag_ui format (no EventMessages)
    ag_ui_messages = pydantic_ai2ag_ui(messages, convert_events=False)
    
    # Create MessagesSnapshotEvent
    event = MessagesSnapshotEvent(
        type=EventType.MESSAGES_SNAPSHOT,
        messages=ag_ui_messages,
    )
    
    # Encode the event
    encoder = EventEncoder()
    encoded_event = encoder.encode(event)
    
    return Response(content=encoded_event, media_type='text/plain')


@app.get('/display-messages/')
async def get_display_messages(request: Request, conversation_id: str):
    """Get display messages for rendering in UI.
    
    Returns messages with EventMessages for custom events.
    
    Args:
        conversation_id: ID of conversation to load.
    
    Returns:
        JSON array of messages (includes EventMessages with role='event').
    """
    db: Database = request.state.db
    messages = await db.get_messages(conversation_id)
    
    # Convert to display format (includes EventMessages)
    display_messages = pydantic_ai2ag_ui(messages, convert_events=True)
    
    # Convert to dicts for JSON serialization
    messages_data = [
        msg.model_dump() if hasattr(msg, 'model_dump') else dict(msg)
        for msg in display_messages
    ]
    
    return fastapi.responses.JSONResponse(content=messages_data)


async def conditional_exit(event_stream: AsyncIterator):
    async for event in event_stream:
        yield event


@app.post('/chat/')
async def chat(request: Request) -> Response:
    """Handle chat requests with database persistence."""
    import time
    
    db: Database = request.state.db
    accept = request.headers.get('accept', SSE_CONTENT_TYPE)
    
    # Read body to extract threadId
    body_bytes = await request.body()
    body = json.loads(body_bytes)
    conversation_id = body.get('threadId', f'conv-{int(time.time() * 1000)}')
    
    # Build run input from request body
    try:
        run_input = AGUIAdapter.build_run_input(body_bytes)
    except ValidationError as e:
        return Response(
            content=json.dumps(e.json()),
            media_type='application/json',
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )

    # Create adapter with agent and run input
    adapter = AGUIAdapter(
        agent=agent,
        run_input=run_input,
    )
    
    # Prepare dependencies and callback
    deps = Deps(state=MyState())
    on_complete_callback = db.create_on_complete(conversation_id, body)
    
    # Run and stream AG-UI events
    # Turn off parallel_tool_calls as they don't surface exceptions correctly
    event_stream = adapter.encode_stream(
        adapter.run_stream(
            model_settings={'parallel_tool_calls': False},
            deps=deps,
            on_complete=on_complete_callback,
        )
    )
    
    return StreamingResponse(event_stream, media_type=accept)


if __name__ == '__main__':
    uvicorn.run('app:app', reload=True, reload_dirs=[str(THIS_DIR)])
