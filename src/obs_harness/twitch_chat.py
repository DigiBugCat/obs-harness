"""Twitch chat integration for reading chat messages."""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from twitchio import Client, Message


@dataclass
class ChatMessage:
    """A single chat message."""

    username: str
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


class ChatBuffer:
    """Thread-safe ring buffer for recent chat messages."""

    def __init__(self, max_messages: int = 100):
        self._messages: deque[ChatMessage] = deque(maxlen=max_messages)
        self._lock = asyncio.Lock()

    async def add(self, username: str, content: str) -> None:
        """Add a message to the buffer."""
        async with self._lock:
            self._messages.append(ChatMessage(username=username, content=content))

    async def get_recent(self, seconds: int = 60) -> list[ChatMessage]:
        """Get messages from the last N seconds."""
        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        async with self._lock:
            return [m for m in self._messages if m.timestamp >= cutoff]

    async def clear(self) -> None:
        """Clear all messages."""
        async with self._lock:
            self._messages.clear()


class TwitchChatClient(Client):
    """Twitch chat client for reading messages."""

    def __init__(
        self,
        access_token: str,
        initial_channel: str | None = None,
    ):
        """Initialize the Twitch chat client.

        Args:
            access_token: OAuth token for chat access
            initial_channel: Channel to join on startup (without #)
        """
        channels = [initial_channel] if initial_channel else []
        super().__init__(token=access_token, initial_channels=channels)
        self._buffer = ChatBuffer()
        self._current_channel: str | None = initial_channel

    @property
    def buffer(self) -> ChatBuffer:
        """Get the chat buffer."""
        return self._buffer

    @property
    def current_channel(self) -> str | None:
        """Get the currently joined channel."""
        return self._current_channel

    async def event_ready(self) -> None:
        """Called when bot is ready."""
        print(f"Twitch chat connected as {self.nick}")

    async def event_message(self, message: Message) -> None:
        """Handle incoming chat messages."""
        # Ignore messages without an author (e.g., system messages)
        if message.author is None:
            return

        # Store in buffer
        await self._buffer.add(message.author.name, message.content)

    async def join_channel(self, channel: str) -> None:
        """Join a new channel."""
        await self.join_channels([channel])
        self._current_channel = channel

    async def leave_channel(self, channel: str) -> None:
        """Leave a channel."""
        await self.part_channels([channel])
        if self._current_channel == channel:
            self._current_channel = None

    async def get_recent_messages(self, seconds: int = 60) -> list[ChatMessage]:
        """Get recent messages from the buffer."""
        return await self._buffer.get_recent(seconds)

    def format_for_prompt(
        self,
        messages: list[ChatMessage],
        max_messages: int = 20,
    ) -> str:
        """Format messages for inclusion in AI prompt."""
        if not messages:
            return ""

        # Take most recent N messages
        recent = messages[-max_messages:]
        lines = [f"[{m.username}]: {m.content}" for m in recent]
        return "\n".join(lines)


class TwitchChatManager:
    """Manager for Twitch chat integration."""

    def __init__(self):
        self._client: TwitchChatClient | None = None
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def is_connected(self) -> bool:
        """Check if connected to Twitch chat."""
        return self._running and self._client is not None

    @property
    def current_channel(self) -> str | None:
        """Get the currently joined channel."""
        return self._client.current_channel if self._client else None

    async def start(
        self,
        access_token: str,
        channel: str | None = None,
    ) -> None:
        """Start the Twitch chat client.

        Args:
            access_token: OAuth token for chat access
            channel: Channel to join on startup (without #)
        """
        if self._running:
            await self.stop()

        self._client = TwitchChatClient(
            access_token=access_token,
            initial_channel=channel,
        )
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        """Run the client with reconnection logic."""
        while self._running:
            try:
                await self._client.start()
            except Exception as e:
                print(f"Twitch chat error: {e}")
                if self._running:
                    await asyncio.sleep(5)  # Reconnect delay

    async def stop(self) -> None:
        """Stop the Twitch chat client."""
        self._running = False
        if self._client:
            await self._client.close()
            self._client = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def join_channel(self, channel: str) -> None:
        """Join a Twitch channel."""
        if self._client:
            await self._client.join_channel(channel)

    async def leave_channel(self, channel: str) -> None:
        """Leave a Twitch channel."""
        if self._client:
            await self._client.leave_channel(channel)

    async def get_chat_context(
        self,
        seconds: int = 60,
        max_messages: int = 20,
    ) -> str:
        """Get formatted chat context for AI prompt.

        Args:
            seconds: How far back to look for messages
            max_messages: Maximum number of messages to include

        Returns:
            Formatted string of recent chat messages, or empty string if none
        """
        if not self._client:
            return ""

        messages = await self._client.get_recent_messages(seconds)
        return self._client.format_for_prompt(messages, max_messages)
