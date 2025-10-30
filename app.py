"""Minimal reproduction of ModelRetry conversation history bug.

When a tool raises ModelRetry, the conversation history contains tool_calls
without corresponding tool responses, causing OpenAI to reject follow-up
messages with 400 errors.
"""

import os
from pathlib import Path
from dataclasses import dataclass
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from basalt import Basalt
import logfire
import uvicorn
import fastapi
from fastapi.requests import Request
from fastapi.responses import FileResponse, Response
from ag_ui.core import EventType, StateSnapshotEvent, CustomEvent, MessagesSnapshotEvent
from ag_ui.encoder import EventEncoder
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.messages import ToolReturn
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.models.test import TestModel
from pydantic_ai.ag_ui import handle_ag_ui_request
from pydantic_ai.ag_ui import StateDeps

from db import Database
from utils import pydantic_ai2ag_ui

# Load environment variables from .env file
load_dotenv()

# Configure logfire
logfire.configure()
logfire.instrument_pydantic_ai()

BASALT_API_KEY = os.getenv('BASALT_API_KEY')
if not BASALT_API_KEY:
    raise ValueError("BASALT_API_KEY not found in environment variables")

basalt = Basalt(api_key=BASALT_API_KEY)

THIS_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(_app: fastapi.FastAPI):
    """Manage database connection lifecycle."""
    async with Database.connect() as db:
        yield {'db': db}


app = fastapi.FastAPI(lifespan=lifespan)

# Switch between TestModel (works) and gpt-4o-mini (fails on second message)
# from pydantic_ai.models.test import TestModel
# model = TestModel()
model = 'gpt-4o-mini'



class MyState(BaseModel):
    does_the_user_know: bool = False


@dataclass
class Deps(StateDeps[MyState]):
    state: MyState


SYSTEM_PROMPT = 'Be Helpful'
agent = Agent(model, instructions=SYSTEM_PROMPT, deps_type=Deps)

class Password(BaseModel):
    password: int = Field(description="The secret password to access the plan.")
    guess: str = Field(description="Guess what you think the secret is, lets see if you're right.")


def password_guesser_tool(ctx, guess: int) -> str:
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


class Plan(BaseModel):
    steps: list[str] = Field(description="The steps of the secret plan.")

@agent.tool()
def secret_plan(ctx, password: Password) -> ToolReturn | str:
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


@app.post('/chat/')
async def chat(request: Request) -> Response:
    """Handle chat requests with database persistence."""
    import time
    import json as json_module
    
    db: Database = request.state.db
    
    # Read body to extract threadId and pass to on_complete
    body_bytes = await request.body()
    body = json_module.loads(body_bytes)
    conversation_id = body.get('threadId', f'conv-{int(time.time() * 1000)}')
    
    # Reconstruct request for handle_ag_ui_request
    async def receive():
        return {'type': 'http.request', 'body': body_bytes}
    
    from fastapi import Request as FastAPIRequest
    modified_request = FastAPIRequest(request.scope, receive)
    modified_request._state = request.state
    
    deps = Deps(state=MyState())
    return await handle_ag_ui_request(
        agent,
        modified_request,
        model_settings={'parallel_tool_calls': False},
        deps=deps,
        on_complete=db.create_on_complete(conversation_id, body),
    )


if __name__ == '__main__':
    uvicorn.run('app:app', reload=True, reload_dirs=[str(THIS_DIR)])
