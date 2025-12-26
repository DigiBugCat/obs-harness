"""Twitch EventSub WebSocket client for channel points and chat.

Uses pyTwitchAPI for EventSub WebSocket connection and Twitch Helix API.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Awaitable

from twitchAPI.twitch import Twitch
from twitchAPI.eventsub.websocket import EventSubWebsocket
from twitchAPI.object.eventsub import (
    ChannelPointsCustomRewardRedemptionAddEvent,
    ChannelChatMessageEvent,
)
from twitchAPI.type import AuthScope

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
        self._lock = asyncio.Lock()

    async def add(self, message: ChatMessage) -> None:
        """Add a message to the buffer."""
        async with self._lock:
            self._messages.append(message)

    async def get_recent(self, seconds: int = 60) -> list[ChatMessage]:
        """Get messages from the last N seconds."""
        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        async with self._lock:
            return [m for m in self._messages if m.timestamp >= cutoff]

    async def clear(self) -> None:
        """Clear all messages."""
        async with self._lock:
            self._messages.clear()

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
    """Manager for Twitch EventSub integration using pyTwitchAPI.

    Handles:
    - EventSub WebSocket connection
    - Channel point redemption callbacks
    - Chat message streaming
    - Reward pause/unpause via Twitch API
    - Redemption fulfill/cancel via Twitch API
    """

    def __init__(self):
        self._twitch: Twitch | None = None
        self._eventsub: EventSubWebsocket | None = None
        self._reward_id: str | None = None
        self._broadcaster_user_id: str | None = None
        self._user_id: str | None = None  # The authenticated user's ID
        self._on_redemption: Callable[[ChannelPointRedemption], Awaitable[None]] | None = None
        self._on_chat_message: Callable[[ChatMessage], Awaitable[None]] | None = None
        self._running = False
        self._chat_buffer = ChatBuffer()

    @property
    def is_connected(self) -> bool:
        """Check if connected to EventSub."""
        return self._running and self._eventsub is not None

    @property
    def chat_buffer(self) -> ChatBuffer:
        """Get the chat message buffer."""
        return self._chat_buffer

    def set_chat_callback(self, callback: Callable[[ChatMessage], Awaitable[None]] | None) -> None:
        """Set callback for chat messages."""
        self._on_chat_message = callback

    async def start(
        self,
        access_token: str,
        client_id: str,
        broadcaster_user_id: str,
        user_id: str | None = None,
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
            reward_id: Optional specific reward ID to listen for
            on_redemption: Callback for redemption events
            subscribe_to_chat: Whether to subscribe to chat messages
            subscribe_to_redemptions: Whether to subscribe to redemptions
        """
        if self._running:
            await self.stop()

        self._reward_id = reward_id
        self._broadcaster_user_id = broadcaster_user_id
        self._user_id = user_id or broadcaster_user_id
        self._on_redemption = on_redemption

        try:
            # Initialize Twitch API with public client (no app authentication)
            self._twitch = await Twitch(client_id, authenticate_app=False)

            # Set user authentication with all needed scopes
            # Disable auto-refresh BEFORE setting auth (we only have access token, no refresh token from implicit grant)
            self._twitch.auto_refresh_auth = False

            # Include all scopes we need (for both events and API calls like get_rewards)
            scopes = [
                AuthScope.USER_READ_CHAT,
                AuthScope.CHANNEL_READ_REDEMPTIONS,
                AuthScope.CHANNEL_MANAGE_REDEMPTIONS,
            ]

            await self._twitch.set_user_authentication(
                access_token,
                scopes,
                validate=True,
            )

            # Create and start EventSub WebSocket
            self._eventsub = EventSubWebsocket(self._twitch)
            self._eventsub.start()

            # Subscribe to chat messages
            if subscribe_to_chat:
                await self._eventsub.listen_channel_chat_message(
                    broadcaster_user_id=broadcaster_user_id,
                    user_id=self._user_id,
                    callback=self._handle_chat_message,
                )
                logger.info(f"Subscribed to chat for channel {broadcaster_user_id}")

            # Subscribe to channel point redemptions
            if subscribe_to_redemptions:
                print(f"[DEBUG] Subscribing to redemptions for {broadcaster_user_id}, reward_id={reward_id}")
                await self._eventsub.listen_channel_points_custom_reward_redemption_add(
                    broadcaster_user_id=broadcaster_user_id,
                    reward_id=reward_id,  # None means all rewards
                    callback=self._handle_redemption,
                )
                print(f"[DEBUG] Successfully subscribed to redemptions")
                logger.info(f"Subscribed to redemptions for channel {broadcaster_user_id}")

            self._running = True
            logger.info(f"EventSub started for broadcaster {broadcaster_user_id}")

        except Exception as e:
            await self.stop()
            raise TwitchEventSubError(f"Failed to start EventSub: {e}")

    async def stop(self) -> None:
        """Stop the EventSub client."""
        self._running = False

        if self._eventsub:
            try:
                await self._eventsub.stop()
            except Exception as e:
                logger.warning(f"Error stopping EventSub: {e}")
            self._eventsub = None

        if self._twitch:
            try:
                await self._twitch.close()
            except Exception as e:
                logger.warning(f"Error closing Twitch client: {e}")
            self._twitch = None

        logger.info("EventSub stopped")

    async def _handle_chat_message(self, event: ChannelChatMessageEvent) -> None:
        """Handle incoming chat message from EventSub."""
        message = ChatMessage(
            message_id=event.event.message_id,
            user_id=event.event.chatter_user_id,
            user_login=event.event.chatter_user_login,
            user_display_name=event.event.chatter_user_name,
            message=event.event.message.text,
        )

        # Add to buffer
        await self._chat_buffer.add(message)

        # Call callback if set
        if self._on_chat_message:
            try:
                await self._on_chat_message(message)
            except Exception as e:
                logger.error(f"Error in chat message callback: {e}")

    async def _handle_redemption(self, event: ChannelPointsCustomRewardRedemptionAddEvent) -> None:
        """Handle incoming redemption event from pyTwitchAPI."""
        print(f"[DEBUG] Redemption event received!")
        redemption = ChannelPointRedemption(
            redemption_id=event.event.id,
            reward_id=event.event.reward.id,
            reward_title=event.event.reward.title,
            user_id=event.event.user_id,
            user_login=event.event.user_login,
            user_display_name=event.event.user_name,
            user_input=event.event.user_input,
            redeemed_at=event.event.redeemed_at.isoformat() if event.event.redeemed_at else "",
        )

        print(f"[DEBUG] Redemption: {redemption.user_display_name} redeemed '{redemption.reward_title}'")
        logger.info(f"Redemption: {redemption.user_display_name} redeemed '{redemption.reward_title}'")

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

    # -------------------------------------------------------------------------
    # Reward Management API
    # -------------------------------------------------------------------------

    async def disable_reward(self, reward_id: str | None = None) -> bool:
        """Disable a channel point reward (hide it completely)."""
        rid = reward_id or self._reward_id
        if not self._twitch or not rid or not self._broadcaster_user_id:
            print(f"[DEBUG] disable_reward early return: twitch={self._twitch}, rid={rid}, broadcaster={self._broadcaster_user_id}")
            return False

        try:
            print(f"[DEBUG] Calling update_custom_reward: broadcaster_id={self._broadcaster_user_id}, reward_id={rid}")
            await self._twitch.update_custom_reward(
                broadcaster_id=self._broadcaster_user_id,
                reward_id=rid,
                is_enabled=False,
            )
            logger.info(f"Disabled reward: {rid}")
            return True
        except Exception as e:
            print(f"[DEBUG] disable_reward exception: {e}")
            logger.error(f"Failed to disable reward: {e}")
            return False

    async def enable_reward(self, reward_id: str | None = None) -> bool:
        """Enable a channel point reward (show it)."""
        rid = reward_id or self._reward_id
        if not self._twitch or not rid or not self._broadcaster_user_id:
            return False

        try:
            await self._twitch.update_custom_reward(
                broadcaster_id=self._broadcaster_user_id,
                reward_id=rid,
                is_enabled=True,
            )
            logger.info(f"Enabled reward: {rid}")
            return True
        except Exception as e:
            logger.error(f"Failed to enable reward: {e}")
            return False

    async def fulfill_redemption(self, redemption_id: str, reward_id: str | None = None) -> bool:
        """Mark a redemption as fulfilled."""
        rid = reward_id or self._reward_id
        if not self._twitch or not rid or not self._broadcaster_user_id:
            return False

        try:
            await self._twitch.update_redemption_status(
                broadcaster_id=self._broadcaster_user_id,
                reward_id=rid,
                redemption_ids=[redemption_id],
                status="FULFILLED",
            )
            logger.info(f"Fulfilled redemption: {redemption_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to fulfill redemption: {e}")
            return False

    async def cancel_redemption(self, redemption_id: str, reward_id: str | None = None) -> bool:
        """Cancel a redemption (refund points)."""
        rid = reward_id or self._reward_id
        if not self._twitch or not rid or not self._broadcaster_user_id:
            return False

        try:
            await self._twitch.update_redemption_status(
                broadcaster_id=self._broadcaster_user_id,
                reward_id=rid,
                redemption_ids=[redemption_id],
                status="CANCELED",
            )
            logger.info(f"Cancelled redemption: {redemption_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel redemption: {e}")
            return False

    async def get_rewards(self) -> list[dict]:
        """Get all custom rewards for the broadcaster."""
        if not self._twitch or not self._broadcaster_user_id:
            return []

        try:
            result = await self._twitch.get_custom_reward(
                broadcaster_id=self._broadcaster_user_id,
                only_manageable_rewards=False,
            )
            rewards = []
            for reward in result:
                rewards.append({
                    "id": reward.id,
                    "title": reward.title,
                    "cost": reward.cost,
                    "is_paused": reward.is_paused,
                    "is_enabled": reward.is_enabled,
                })
            return rewards
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
        if not self._twitch or not self._broadcaster_user_id:
            return None

        try:
            result = await self._twitch.create_custom_reward(
                broadcaster_id=self._broadcaster_user_id,
                title=title,
                cost=cost,
                prompt=prompt if prompt else None,
                is_user_input_required=is_user_input_required,
                is_enabled=is_enabled,
                should_redemptions_skip_request_queue=False,  # We want to manage redemptions
            )
            logger.info(f"Created reward: {title} (id={result.id})")
            return {
                "id": result.id,
                "title": result.title,
                "cost": result.cost,
                "is_paused": result.is_paused,
                "is_enabled": result.is_enabled,
            }
        except Exception as e:
            logger.error(f"Failed to create reward: {e}")
            return None
