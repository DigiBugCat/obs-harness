"""Twitch EventSub WebSocket client for channel points and chat.

Uses TwitchIO for EventSub WebSocket connection and Twitch Helix API.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Awaitable

import twitchio
from twitchio import eventsub

from .config import settings

logger = logging.getLogger(__name__)


@dataclass
class ChannelPointRedemption:
    """A channel point redemption event."""

    redemption_id: str
    reward_id: str
    reward_title: str
    user_id: str
    user_login: str
    user_display_name: str
    user_input: str | None  # Text input if reward requires it
    redeemed_at: str


@dataclass
class ChatMessage:
    """A chat message from EventSub."""

    message_id: str
    user_id: str
    user_login: str
    user_display_name: str
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


class ChatBuffer:
    """Thread-safe ring buffer for recent chat messages."""

    def __init__(self, max_messages: int = 100):
        self._messages: deque[ChatMessage] = deque(maxlen=max_messages)
        self._seen_ids: set[str] = set()  # Track message IDs in buffer
        # Lock can be created outside event loop in Python 3.10+
        self._lock: asyncio.Lock = asyncio.Lock()

    def _get_lock(self) -> asyncio.Lock:
        """Get the buffer lock."""
        return self._lock

    async def add(self, message: ChatMessage) -> bool:
        """Add a message to the buffer. Returns False if duplicate."""
        async with self._get_lock():
            if message.message_id in self._seen_ids:
                return False
            # If buffer is at capacity, remove oldest message's ID from seen set
            if len(self._messages) == self._messages.maxlen:
                oldest = self._messages[0]
                self._seen_ids.discard(oldest.message_id)
            self._seen_ids.add(message.message_id)
            self._messages.append(message)
            return True

    async def get_recent(self, seconds: int = 60) -> list[ChatMessage]:
        """Get messages from the last N seconds."""
        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        async with self._get_lock():
            return [m for m in self._messages if m.timestamp >= cutoff]

    async def clear(self) -> None:
        """Clear all messages."""
        async with self._get_lock():
            self._messages.clear()
            self._seen_ids.clear()

    def format_for_prompt(self, messages: list[ChatMessage], max_messages: int = 20) -> str:
        """Format messages for inclusion in AI prompt."""
        if not messages:
            return ""
        recent = messages[-max_messages:]
        lines = [f"[{m.user_display_name}]: {m.message}" for m in recent]
        return "\n".join(lines)


class TwitchEventSubError(Exception):
    """Error from Twitch EventSub."""

    pass


class TwitchEventSubManager:
    """Manager for Twitch EventSub integration using TwitchIO.

    Handles:
    - EventSub WebSocket connection
    - Channel point redemption callbacks
    - Chat message streaming
    - Reward management via Twitch API
    - Redemption fulfill/cancel via Twitch API
    """

    # TTL for seen IDs (in seconds)
    MESSAGE_TTL_SECONDS = 300  # 5 minutes
    REDEMPTION_TTL_SECONDS = 600  # 10 minutes

    # Stale connection threshold - if no activity for this long, consider disconnected
    STALE_THRESHOLD_SECONDS = 120  # 2 minutes

    def __init__(self):
        self._client: twitchio.Client | None = None
        self._broadcaster_user_id: str | None = None
        self._user_id: str | None = None  # The authenticated user's ID
        self._reward_id: str | None = None
        self._on_redemption: Callable[[ChannelPointRedemption], Awaitable[None]] | None = None
        self._on_chat_message: Callable[[ChatMessage], Awaitable[None]] | None = None
        self._running = False
        self._chat_buffer = ChatBuffer()
        self._last_activity: datetime | None = None  # Track last received event
        # Deduplication tracking
        self._seen_message_ids: dict[str, datetime] = {}  # message_id -> first_seen_time
        self._seen_redemption_ids: dict[str, datetime] = {}  # redemption_id -> first_seen_time
        self._cleanup_task: asyncio.Task | None = None
        # Store tokens for API calls
        self._access_token: str | None = None
        # Lock to prevent concurrent start() calls
        self._start_lock: asyncio.Lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if connected to EventSub."""
        if not self._running or self._client is None:
            return False

        # If we have activity tracking, check for stale connection
        if self._last_activity:
            stale_cutoff = datetime.utcnow() - timedelta(seconds=self.STALE_THRESHOLD_SECONDS)
            if self._last_activity < stale_cutoff:
                logger.warning(f"EventSub connection stale - no activity for {self.STALE_THRESHOLD_SECONDS}s")
                return False

        return True

    def _update_activity(self) -> None:
        """Update last activity timestamp."""
        self._last_activity = datetime.utcnow()

    @property
    def chat_buffer(self) -> ChatBuffer:
        """Get the chat message buffer."""
        return self._chat_buffer

    def set_chat_callback(self, callback: Callable[[ChatMessage], Awaitable[None]] | None) -> None:
        """Set callback for chat messages."""
        self._on_chat_message = callback

    async def _cleanup_seen_ids(self) -> None:
        """Background task to clean up expired seen IDs."""
        while self._running:
            await asyncio.sleep(60)  # Run every minute
            now = datetime.utcnow()

            # Clean up message IDs
            message_cutoff = now - timedelta(seconds=self.MESSAGE_TTL_SECONDS)
            expired_messages = [
                mid for mid, seen_at in self._seen_message_ids.items()
                if seen_at < message_cutoff
            ]
            for mid in expired_messages:
                del self._seen_message_ids[mid]

            # Clean up redemption IDs
            redemption_cutoff = now - timedelta(seconds=self.REDEMPTION_TTL_SECONDS)
            expired_redemptions = [
                rid for rid, seen_at in self._seen_redemption_ids.items()
                if seen_at < redemption_cutoff
            ]
            for rid in expired_redemptions:
                del self._seen_redemption_ids[rid]

            if expired_messages or expired_redemptions:
                logger.debug(f"Cleaned up {len(expired_messages)} message IDs, {len(expired_redemptions)} redemption IDs")

    async def start(
        self,
        access_token: str,
        client_id: str,
        broadcaster_user_id: str,
        user_id: str | None = None,
        refresh_token: str | None = None,
        reward_id: str | None = None,
        on_redemption: Callable[[ChannelPointRedemption], Awaitable[None]] | None = None,
        subscribe_to_chat: bool = True,
        subscribe_to_redemptions: bool = True,
    ) -> None:
        """Start the EventSub client.

        Args:
            access_token: Twitch OAuth token (user token)
            client_id: Twitch client ID
            broadcaster_user_id: Broadcaster's user ID (whose channel to monitor)
            user_id: The authenticated user's ID (for chat - needs to match token)
            refresh_token: OAuth refresh token for token refresh
            reward_id: Optional specific reward ID to listen for
            on_redemption: Callback for redemption events
            subscribe_to_chat: Whether to subscribe to chat messages
            subscribe_to_redemptions: Whether to subscribe to redemptions
        """
        async with self._start_lock:
            if self._running:
                await self.stop()

            self._reward_id = reward_id
            self._broadcaster_user_id = broadcaster_user_id
            self._user_id = user_id or broadcaster_user_id
            self._on_redemption = on_redemption
            self._access_token = access_token

            try:
                # Get client secret from settings
                client_secret = settings.twitch_client_secret or ""

                # Create the TwitchIO client
                self._client = twitchio.Client(
                    client_id=client_id,
                    client_secret=client_secret,
                    bot_id=self._user_id,
                )

                # Set up event handlers
                self._setup_event_handlers()

                # Add token to client (TwitchIO 3.x requires both access and refresh tokens)
                await self._client.add_token(access_token, refresh_token or "")

                # Call login directly (not in background task)
                # Note: Don't use wait_until_ready() - it waits for _ready_event which
                # is only set by client.start(), not login()
                await self._client.login()

                # Subscribe to events
                if subscribe_to_chat:
                    chat_sub = eventsub.ChatMessageSubscription(
                        broadcaster_user_id=broadcaster_user_id,
                        user_id=self._user_id,
                    )
                    await self._client.subscribe_websocket(chat_sub, token_for=self._user_id)
                    logger.info(f"Subscribed to chat for channel {broadcaster_user_id}")

                if subscribe_to_redemptions:
                    redemption_sub = eventsub.ChannelPointsRedeemAddSubscription(
                        broadcaster_user_id=broadcaster_user_id,
                    )
                    await self._client.subscribe_websocket(redemption_sub, token_for=self._user_id)
                    logger.info(f"Subscribed to redemptions for channel {broadcaster_user_id}")

                self._running = True
                self._update_activity()  # Mark as active on start

                # Start cleanup task for seen IDs
                self._cleanup_task = asyncio.create_task(self._cleanup_seen_ids())

                logger.info(f"EventSub started for broadcaster {broadcaster_user_id}")

            except Exception as e:
                await self.stop()
                raise TwitchEventSubError(f"Failed to start EventSub: {e}")

    def _setup_event_handlers(self) -> None:
        """Set up TwitchIO event handlers."""
        if not self._client:
            return

        async def event_ready() -> None:
            logger.info("TwitchIO client ready")

        async def event_message(event: twitchio.ChatMessage) -> None:
            await self._handle_chat_message(event)

        async def event_custom_redemption_add(event: twitchio.ChannelPointsRedemptionAdd) -> None:
            await self._handle_redemption(event)

        # TwitchIO 3.x uses add_listener() instead of @client.event()
        self._client.add_listener(event_ready)
        self._client.add_listener(event_message)
        self._client.add_listener(event_custom_redemption_add)

    async def stop(self) -> None:
        """Stop the EventSub client."""
        self._running = False

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        # Close client
        if self._client:
            try:
                await self._client.close()
            except Exception as e:
                logger.warning(f"Error closing TwitchIO client: {e}")
            self._client = None

        # Clear seen IDs
        self._seen_message_ids.clear()
        self._seen_redemption_ids.clear()

        logger.info("EventSub stopped")

    async def _handle_chat_message(self, event: twitchio.ChatMessage) -> None:
        """Handle incoming chat message from EventSub."""
        self._update_activity()  # Track activity

        message_id = event.id

        # Deduplicate: skip if we've already processed this message
        if message_id in self._seen_message_ids:
            logger.debug(f"Duplicate chat message ignored: {message_id}")
            return
        self._seen_message_ids[message_id] = datetime.utcnow()

        # Ignore messages from the logged-in user (bot's own messages)
        if self._user_id and event.chatter.id == self._user_id:
            return

        logger.debug(f"Chat message received: {message_id} from {event.chatter.name}")

        message = ChatMessage(
            message_id=message_id,
            user_id=event.chatter.id,
            user_login=event.chatter.name,  # TwitchIO PartialUser doesn't have login, use name
            user_display_name=event.chatter.display_name,
            message=event.text,
        )

        # Add to buffer
        await self._chat_buffer.add(message)

        # Call callback if set
        if self._on_chat_message:
            try:
                await self._on_chat_message(message)
            except Exception as e:
                logger.error(f"Error in chat message callback: {e}")

    async def _handle_redemption(self, event: twitchio.ChannelPointsRedemptionAdd) -> None:
        """Handle incoming redemption event from TwitchIO."""
        self._update_activity()  # Track activity

        redemption_id = event.id

        # Deduplicate: skip if we've already processed this redemption
        if redemption_id in self._seen_redemption_ids:
            logger.warning(f"Duplicate redemption ignored: {redemption_id}")
            return
        self._seen_redemption_ids[redemption_id] = datetime.utcnow()

        redemption = ChannelPointRedemption(
            redemption_id=redemption_id,
            reward_id=event.reward.id,
            reward_title=event.reward.title,
            user_id=event.user.id,
            user_login=event.user.name,  # TwitchIO PartialUser doesn't have login, use name
            user_display_name=event.user.display_name,
            user_input=event.user_input,
            redeemed_at=event.redeemed_at.isoformat() if event.redeemed_at else "",
        )

        logger.info(f"Redemption {redemption_id}: {redemption.user_display_name} redeemed '{redemption.reward_title}'")

        if self._on_redemption:
            try:
                await self._on_redemption(redemption)
            except Exception as e:
                logger.error(f"Error in redemption callback: {e}")

    # -------------------------------------------------------------------------
    # Chat Helper Methods
    # -------------------------------------------------------------------------

    async def get_chat_context(self, seconds: int = 60, max_messages: int = 20) -> str:
        """Get formatted chat context for AI prompt."""
        messages = await self._chat_buffer.get_recent(seconds)
        return self._chat_buffer.format_for_prompt(messages, max_messages)

    async def get_raw_messages(self, seconds: int = 60) -> list[ChatMessage]:
        """Get raw chat messages for processing."""
        return await self._chat_buffer.get_recent(seconds)

    async def send_chat_message(self, message: str) -> bool:
        """Send a message to the chat.

        Args:
            message: The message to send (max 500 characters)

        Returns:
            True if message was sent successfully
        """
        if not self._client or not self._broadcaster_user_id or not self._user_id:
            logger.warning("Cannot send chat: not connected or missing broadcaster/user ID")
            return False

        try:
            # Truncate message if too long (Twitch limit is 500 chars)
            if len(message) > 500:
                message = message[:497] + "..."

            broadcaster = self._client.create_partialuser(user_id=self._broadcaster_user_id)
            await broadcaster.send_chat_message(
                text=message,
                token_for=self._user_id,
            )
            logger.info(f"Sent chat message: {message[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to send chat message: {e}")
            return False

    # -------------------------------------------------------------------------
    # Reward Management API
    # -------------------------------------------------------------------------

    async def disable_reward(self, reward_id: str | None = None) -> bool:
        """Disable a channel point reward (hide it completely)."""
        rid = reward_id or self._reward_id
        if not self._client or not rid or not self._broadcaster_user_id:
            return False

        try:
            broadcaster = self._client.create_partialuser(user_id=self._broadcaster_user_id)
            await broadcaster.update_custom_reward(
                reward_id=rid,
                is_enabled=False,
                token_for=self._user_id,
            )
            logger.info(f"Disabled reward: {rid}")
            return True
        except Exception as e:
            logger.error(f"Failed to disable reward: {e}")
            return False

    async def enable_reward(self, reward_id: str | None = None) -> bool:
        """Enable a channel point reward (show it)."""
        rid = reward_id or self._reward_id
        if not self._client or not rid or not self._broadcaster_user_id:
            return False

        try:
            broadcaster = self._client.create_partialuser(user_id=self._broadcaster_user_id)
            await broadcaster.update_custom_reward(
                reward_id=rid,
                is_enabled=True,
                token_for=self._user_id,
            )
            logger.info(f"Enabled reward: {rid}")
            return True
        except Exception as e:
            logger.error(f"Failed to enable reward: {e}")
            return False

    async def fulfill_redemption(self, redemption_id: str, reward_id: str | None = None) -> bool:
        """Mark a redemption as fulfilled."""
        rid = reward_id or self._reward_id
        if not self._client or not rid or not self._broadcaster_user_id:
            return False

        try:
            broadcaster = self._client.create_partialuser(user_id=self._broadcaster_user_id)
            await broadcaster.update_reward_redemption(
                reward_id=rid,
                redemption_id=redemption_id,
                status="FULFILLED",
                token_for=self._user_id,
            )
            logger.info(f"Fulfilled redemption: {redemption_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to fulfill redemption: {e}")
            return False

    async def cancel_redemption(self, redemption_id: str, reward_id: str | None = None) -> bool:
        """Cancel a redemption (refund points)."""
        rid = reward_id or self._reward_id
        if not self._client or not rid or not self._broadcaster_user_id:
            return False

        try:
            broadcaster = self._client.create_partialuser(user_id=self._broadcaster_user_id)
            await broadcaster.update_reward_redemption(
                reward_id=rid,
                redemption_id=redemption_id,
                status="CANCELED",
                token_for=self._user_id,
            )
            logger.info(f"Cancelled redemption: {redemption_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel redemption: {e}")
            return False

    async def get_rewards(self) -> list[dict]:
        """Get all custom rewards for the broadcaster."""
        if not self._client or not self._broadcaster_user_id:
            return []

        try:
            broadcaster = self._client.create_partialuser(user_id=self._broadcaster_user_id)
            rewards = await broadcaster.fetch_custom_rewards(token_for=self._user_id)
            result = []
            for reward in rewards:
                result.append({
                    "id": reward.id,
                    "title": reward.title,
                    "cost": reward.cost,
                    "is_paused": reward.is_paused,
                    "is_enabled": reward.is_enabled,
                })
            return result
        except Exception as e:
            logger.error(f"Failed to get rewards: {e}")
            return []

    async def create_reward(
        self,
        title: str,
        cost: int,
        prompt: str = "",
        is_user_input_required: bool = True,
        is_enabled: bool = True,
    ) -> dict | None:
        """Create a new channel point reward.

        Args:
            title: The reward title
            cost: Cost in channel points
            prompt: Description/prompt shown to users
            is_user_input_required: Whether user must enter text when redeeming
            is_enabled: Whether reward is enabled

        Returns:
            Dict with reward info if successful, None otherwise.
        """
        if not self._client or not self._broadcaster_user_id:
            return None

        try:
            broadcaster = self._client.create_partialuser(user_id=self._broadcaster_user_id)
            reward = await broadcaster.create_custom_reward(
                title=title,
                cost=cost,
                prompt=prompt if prompt else None,
                is_user_input_required=is_user_input_required,
                is_enabled=is_enabled,
                should_redemptions_skip_request_queue=False,  # We want to manage redemptions
                token_for=self._user_id,
            )
            logger.info(f"Created reward: {title} (id={reward.id})")
            return {
                "id": reward.id,
                "title": reward.title,
                "cost": reward.cost,
                "is_paused": reward.is_paused,
                "is_enabled": reward.is_enabled,
            }
        except Exception as e:
            logger.error(f"Failed to create reward: {e}")
            return None

    async def cleanup_subscriptions(self, access_token: str, client_id: str) -> int:
        """Delete all EventSub subscriptions for this app.

        Useful for cleaning up 'maximum subscriptions exceeded' errors.

        Args:
            access_token: Twitch OAuth token
            client_id: Twitch client ID

        Returns:
            Number of subscriptions deleted
        """
        import httpx

        deleted = 0
        try:
            async with httpx.AsyncClient() as http:
                # Get all subscriptions
                resp = await http.get(
                    "https://api.twitch.tv/helix/eventsub/subscriptions",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Client-Id": client_id,
                    },
                )
                if resp.status_code != 200:
                    logger.error(f"Failed to list subscriptions: {resp.status_code}")
                    return 0

                data = resp.json()
                subscriptions = data.get("data", [])

                # Delete each subscription
                for sub in subscriptions:
                    sub_id = sub.get("id")
                    if sub_id:
                        del_resp = await http.delete(
                            f"https://api.twitch.tv/helix/eventsub/subscriptions?id={sub_id}",
                            headers={
                                "Authorization": f"Bearer {access_token}",
                                "Client-Id": client_id,
                            },
                        )
                        if del_resp.status_code == 204:
                            deleted += 1
                            logger.debug(f"Deleted subscription {sub_id}")
                        else:
                            logger.warning(f"Failed to delete subscription {sub_id}: {del_resp.status_code}")

                logger.info(f"Cleaned up {deleted} EventSub subscriptions")
                return deleted
        except Exception as e:
            logger.error(f"Failed to cleanup subscriptions: {e}")
            return deleted
