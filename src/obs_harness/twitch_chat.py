"""Twitch chat integration using raw IRC over WebSocket."""

import asyncio
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import websockets

logger = logging.getLogger(__name__)


@dataclass
class StoredMessage:
    """A single stored chat message."""

    username: str
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


class ChatBuffer:
    """Thread-safe ring buffer for recent chat messages."""

    def __init__(self, max_messages: int = 100):
        self._messages: deque[StoredMessage] = deque(maxlen=max_messages)
        self._lock = asyncio.Lock()

    async def add(self, username: str, content: str) -> None:
        """Add a message to the buffer."""
        async with self._lock:
            self._messages.append(StoredMessage(username=username, content=content))

    async def get_recent(self, seconds: int = 60) -> list[StoredMessage]:
        """Get messages from the last N seconds."""
        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        async with self._lock:
            return [m for m in self._messages if m.timestamp >= cutoff]

    async def clear(self) -> None:
        """Clear all messages."""
        async with self._lock:
            self._messages.clear()


# IRC message parser regex
IRC_MESSAGE_RE = re.compile(
    r"^(?:@(?P<tags>\S+) )?(?::(?P<prefix>\S+) )?(?P<command>\S+)(?: (?P<params>.+))?$"
)


class TwitchIRCClient:
    """Simple Twitch IRC client using raw WebSocket."""

    TWITCH_IRC_URL = "wss://irc-ws.chat.twitch.tv:443"

    def __init__(self, channel: str | None = None, access_token: str | None = None):
        self.access_token = access_token
        self._channel = channel
        self._buffer = ChatBuffer()
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._running = False

    @property
    def buffer(self) -> ChatBuffer:
        return self._buffer

    @property
    def channel(self) -> str | None:
        return self._channel

    async def connect(self) -> None:
        """Connect to Twitch IRC."""
        try:
            self._ws = await websockets.connect(
                self.TWITCH_IRC_URL,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            )

            # Authenticate
            await self._ws.send(f"PASS oauth:{self.access_token}")
            await self._ws.send("NICK justinfan12345")  # Anonymous read-only nick

            # Request tags for username info
            await self._ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")

            # Join channel if specified
            if self._channel:
                await self._ws.send(f"JOIN #{self._channel}")

            self._running = True
            logger.info(f"Twitch IRC connected to #{self._channel}")

        except Exception as e:
            self._running = False
            self._ws = None
            logger.error(f"Twitch IRC connection failed: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from Twitch IRC."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def join_channel(self, channel: str) -> None:
        """Join a channel."""
        if self._channel and self._ws:
            await self._ws.send(f"PART #{self._channel}")
        self._channel = channel
        if self._ws:
            await self._ws.send(f"JOIN #{channel}")
        await self._buffer.clear()

    async def run(self) -> None:
        """Run the message receive loop."""
        if not self._ws:
            return

        try:
            async for message in self._ws:
                if not self._running:
                    break
                await self._handle_message(message)
        except websockets.ConnectionClosed:
            pass

    async def _handle_message(self, raw: str) -> None:
        """Handle incoming IRC message."""
        for line in raw.strip().split("\r\n"):
            if not line:
                continue

            # Respond to PING
            if line.startswith("PING"):
                if self._ws:
                    await self._ws.send("PONG :tmi.twitch.tv")
                continue

            # Parse IRC message
            match = IRC_MESSAGE_RE.match(line)
            if not match:
                continue

            command = match.group("command")

            if command == "PRIVMSG":
                await self._handle_privmsg(match)

    async def _handle_privmsg(self, match: re.Match) -> None:
        """Handle PRIVMSG (chat message)."""
        tags_str = match.group("tags") or ""
        params = match.group("params") or ""

        # Parse tags for display-name
        tags = {}
        if tags_str:
            for tag in tags_str.split(";"):
                if "=" in tag:
                    key, value = tag.split("=", 1)
                    tags[key] = value

        # Get username from tags or prefix
        username = tags.get("display-name", "")
        if not username:
            prefix = match.group("prefix") or ""
            if "!" in prefix:
                username = prefix.split("!")[0]
            else:
                username = prefix

        # Extract message content (after the channel and :)
        if " :" in params:
            content = params.split(" :", 1)[1]
        else:
            content = params

        if username and content:
            await self._buffer.add(username, content)

    def format_for_prompt(
        self,
        messages: list[StoredMessage],
        max_messages: int = 20,
    ) -> str:
        """Format messages for inclusion in AI prompt."""
        if not messages:
            return ""
        recent = messages[-max_messages:]
        lines = [f"[{m.username}]: {m.content}" for m in recent]
        return "\n".join(lines)


class TwitchChatManager:
    """Manager for Twitch chat integration."""

    def __init__(self):
        self._client: TwitchIRCClient | None = None
        self._task: asyncio.Task | None = None
        self._access_token: str | None = None

    @property
    def is_connected(self) -> bool:
        """Check if connected to Twitch chat."""
        return self._client is not None and self._client._running

    @property
    def current_channel(self) -> str | None:
        """Get the currently joined channel."""
        return self._client.channel if self._client else None

    async def start(self, access_token: str, channel: str | None = None) -> None:
        """Start the Twitch chat client.

        Raises:
            Exception: If initial connection fails after retries.
        """
        if self._client:
            await self.stop()

        self._access_token = access_token
        self._client = TwitchIRCClient(channel=channel, access_token=access_token)

        # Try initial connection with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self._client.connect()
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    self._client = None
                    raise Exception(f"Failed to connect to Twitch after {max_retries} attempts: {e}")
                logger.warning(f"Twitch connection attempt {attempt + 1} failed: {e}, retrying...")
                await asyncio.sleep(2)

        self._task = asyncio.create_task(self._run_with_reconnect())

    async def _run_with_reconnect(self) -> None:
        """Run with automatic reconnection."""
        reconnect_delay = 5
        max_reconnect_delay = 60

        while self._client and self._client._running:
            try:
                await self._client.run()
            except Exception as e:
                logger.error(f"Twitch chat error: {e}")

            # If still supposed to be running, attempt reconnection
            if self._client and self._client._running:
                logger.info(f"Twitch disconnected, reconnecting in {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)

                try:
                    await self._client.connect()
                    reconnect_delay = 5  # Reset delay on successful reconnect
                    logger.info("Twitch reconnected successfully")
                except Exception as e:
                    logger.warning(f"Twitch reconnection failed: {e}")
                    # Exponential backoff
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

    async def stop(self) -> None:
        """Stop the Twitch chat client."""
        if self._client:
            await self._client.disconnect()
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

    async def get_chat_context(
        self,
        seconds: int = 60,
        max_messages: int = 20,
    ) -> str:
        """Get formatted chat context for AI prompt."""
        if not self._client:
            return ""

        messages = await self._client.buffer.get_recent(seconds)
        return self._client.format_for_prompt(messages, max_messages)

    async def get_raw_messages(
        self,
        seconds: int = 60,
    ) -> list[StoredMessage]:
        """Get raw chat messages for processing.

        Args:
            seconds: How far back to look for messages

        Returns:
            List of StoredMessage objects
        """
        if not self._client:
            return []

        return await self._client.buffer.get_recent(seconds)
