"""Database module for storing chat messages in SQLite."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator, Callable
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, TypeVar

from ag_ui.core import RunAgentInput
from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter
from typing_extensions import LiteralString, ParamSpec
from pydantic_ai.ui.ag_ui import AGUIAdapter


P = ParamSpec('P')
R = TypeVar('R')


@dataclass
class Database:
    """Rudimentary database to store chat messages in SQLite.

    The SQLite standard library package is synchronous, so we
    use a thread pool executor to run queries asynchronously.
    """

    con: sqlite3.Connection
    _loop: asyncio.AbstractEventLoop
    _executor: ThreadPoolExecutor

    @classmethod
    @asynccontextmanager
    async def connect(
        cls, file: Path | None = None
    ) -> AsyncIterator[Database]:
        """Connect to the SQLite database.

        Args:
            file: Path to the SQLite database file. If None, uses default location.

        Yields:
            Database: Connected database instance.
        """
        if file is None:
            file = Path(__file__).parent / '.chat_app_messages.sqlite'
        
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=1)
        con = await loop.run_in_executor(executor, cls._connect, file)
        slf = cls(con, loop, executor)
        
        try:
            yield slf
        finally:
            await slf._asyncify(con.close)

    @staticmethod
    def _connect(file: Path) -> sqlite3.Connection:
        """Create the SQLite connection and initialize the schema.

        Args:
            file: Path to the SQLite database file.

        Returns:
            sqlite3.Connection: The database connection.
        """
        con = sqlite3.connect(str(file))
        cur = con.cursor()
        cur.execute(
            'CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, conversation_id TEXT, message_list TEXT);'
        )
        con.commit()
        return con

    async def add_messages(self, conversation_id: str, messages: bytes) -> None:
        """Add messages to the database.

        Args:
            conversation_id: Unique identifier for the conversation.
            messages: JSON-encoded messages to store.
        """
        await self._asyncify(
            self._execute,
            'INSERT INTO messages (conversation_id, message_list) VALUES (?, ?);',
            conversation_id,
            messages,
            commit=True,
        )
        await self._asyncify(self.con.commit)

    async def get_messages(self, conversation_id: str | None = None) -> list[ModelMessage]:
        """Retrieve messages from the database.

        Args:
            conversation_id: If provided, get messages for specific conversation.
                           If None, get all messages.

        Returns:
            list[ModelMessage]: List of stored messages.
        """
        if conversation_id:
            c = await self._asyncify(
                self._execute,
                'SELECT message_list FROM messages WHERE conversation_id = ? ORDER BY id',
                conversation_id
            )
        else:
            c = await self._asyncify(
                self._execute, 'SELECT message_list FROM messages ORDER BY id'
            )
        rows = await self._asyncify(c.fetchall)
        messages: list[ModelMessage] = []
        for row in rows:
            messages.extend(ModelMessagesTypeAdapter.validate_json(row[0]))
        return messages

    async def get_conversations(self) -> list[str]:
        """Retrieve list of all conversation IDs.

        Returns:
            list[str]: List of unique conversation IDs.
        """
        c = await self._asyncify(
            self._execute, 'SELECT DISTINCT conversation_id FROM messages ORDER BY conversation_id'
        )
        rows = await self._asyncify(c.fetchall)
        return [row[0] for row in rows]

    def _execute(
        self, sql: LiteralString, *args: Any, commit: bool = False
    ) -> sqlite3.Cursor:
        """Execute a SQL query.

        Args:
            sql: SQL query to execute.
            *args: Query parameters.
            commit: Whether to commit after execution.

        Returns:
            sqlite3.Cursor: The cursor after execution.
        """
        cur = self.con.cursor()
        cur.execute(sql, args)
        if commit:
            self.con.commit()
        return cur

    async def _asyncify(
        self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs
    ) -> R:
        """Run a synchronous function asynchronously using the thread pool.

        Args:
            func: Function to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            R: The function's return value.
        """
        return await self._loop.run_in_executor(  # type: ignore
            self._executor,
            partial(func, **kwargs),
            *args,  # type: ignore
        )

    def create_on_complete(self, conversation_id: str, request_body: dict[str, Any]):
        """Create an on_complete callback for handle_ag_ui_request.

        Args:
            conversation_id: Unique identifier for the conversation.
            request_body: The AG-UI request body containing user messages.

        Returns:
            Callable: Async function that saves new messages to the database.
        """
        async def on_complete_callback(result) -> None:
            """Save new messages from the agent run result to the database.

            Args:
                result: AgentRunResult containing new messages.
            """
            # Extract and convert user messages from AG-UI request
            run_input = RunAgentInput.model_validate(request_body)
            user_messages = AGUIAdapter.load_messages(run_input.messages) if run_input.messages else []
            
            # Combine user messages with agent's new messages
            all_messages: list[ModelMessage] = []
            all_messages.extend(user_messages)
            all_messages.extend(result.new_messages())
            
            # Save all messages together
            messages_json = ModelMessagesTypeAdapter.dump_json(all_messages)
            await self.add_messages(conversation_id, messages_json)
        
        return on_complete_callback
