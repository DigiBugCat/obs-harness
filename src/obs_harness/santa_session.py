"""Santa Timmy session manager and state machine.

Handles the multi-turn conversation flow for the Mall Santa feature:
- Channel point redemption triggers a wish session
- State machine manages ask_followup / await_chat / grant / deny flow
- Non-streaming LLM with JSON schema enforcement
- Message debouncing for multi-message responses
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Callable, Awaitable

from .openrouter import OpenRouterClient

if TYPE_CHECKING:
    from .app import OBSHarness
    from .twitch_eventsub import TwitchEventSubManager

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

SANTA_MODEL = "moonshotai/kimi-k2-0905"

SANTA_SYSTEM_PROMPT = """You are Timmy, a jolly mall penguin Santa with magical wish-granting powers!

OUTPUT FORMAT (JSON):
{
  "speech": "Your spoken dialogue",
  "action": "ask_followup" | "await_chat" | "grant" | "deny"
}

RULES:
- "speech" contains ONLY spoken words. No asterisks, no actions, no stage directions.
- Keep speech short (2-4 sentences)
- Talk like a friendly mall Santa, not a fantasy character. Simple, warm, casual.

FLOW:
1. Child states wish → You may "ask_followup" (1-2 times max) OR go straight to "await_chat"
2. When ready for judgment, use "await_chat" and ask chat something like "But what do my elves think about this wish?"
3. Chat responds → You "grant" or "deny" based on their verdict

You remember everything from this stream. Reference past visitors, chat's previous judgments, wishes granted or denied. Chat is your elf council."""

SANTA_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "santa_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "speech": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": ["ask_followup", "await_chat", "grant", "deny"]
                }
            },
            "required": ["speech", "action"],
            "additionalProperties": False
        }
    }
}


# =============================================================================
# State Machine
# =============================================================================


class SantaState(str, Enum):
    """States for Santa session."""

    IDLE = "idle"
    PROCESSING = "processing"
    ASK_FOLLOWUP = "ask_followup"
    AWAIT_CHAT = "await_chat"
    COMPLETE = "complete"


@dataclass
class SantaResponse:
    """Parsed response from Santa LLM."""

    speech: str
    action: str
    raw: str = ""


@dataclass
class SessionData:
    """In-memory session data."""

    session_id: int
    redeemer_user_id: str
    redeemer_username: str
    redeemer_display_name: str
    wish_text: str
    state: SantaState = SantaState.IDLE
    followup_count: int = 0
    conversation: list[dict] = field(default_factory=list)
    outcome: str | None = None


# =============================================================================
# Session Manager
# =============================================================================


class SantaSessionManager:
    """Manages Santa Timmy wish sessions.

    Orchestrates:
    - State machine transitions
    - LLM calls with JSON schema enforcement
    - TTS via existing harness
    - Message debouncing for followup responses
    - Chat voting collection
    """

    def __init__(
        self,
        harness: "OBSHarness",
        eventsub: "TwitchEventSubManager",
        character_name: str = "santa_timmy",
        max_followups: int = 2,
        response_timeout: int = 60,
        debounce_seconds: int = 4,
        chat_vote_seconds: int = 15,
    ):
        self.harness = harness
        self.eventsub = eventsub
        self.character_name = character_name
        self.max_followups = max_followups
        self.response_timeout = response_timeout
        self.debounce_seconds = debounce_seconds
        self.chat_vote_seconds = chat_vote_seconds

        self._session: SessionData | None = None
        self._lock = asyncio.Lock()
        self._speech_lock = asyncio.Lock()  # Prevents overlapping TTS
        self._message_queue: asyncio.Queue[tuple[str, str, str]] = asyncio.Queue()  # (user_id, username, message)
        self._cancelled = False

        # Callbacks for state updates (for WebSocket broadcasting)
        self._on_state_change: Callable[[SessionData], Awaitable[None]] | None = None

    @property
    def active_session(self) -> SessionData | None:
        """Get the current active session."""
        return self._session

    @property
    def is_active(self) -> bool:
        """Check if a session is currently active."""
        return self._session is not None and self._session.state != SantaState.COMPLETE

    def set_state_callback(self, callback: Callable[[SessionData], Awaitable[None]]) -> None:
        """Set callback for state changes (for WebSocket updates)."""
        self._on_state_change = callback

    async def _notify_state_change(self) -> None:
        """Notify listeners of state change."""
        if self._on_state_change and self._session:
            try:
                await self._on_state_change(self._session)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")

    # -------------------------------------------------------------------------
    # Session Lifecycle
    # -------------------------------------------------------------------------

    async def start_session(
        self,
        session_id: int,
        redeemer_user_id: str,
        redeemer_username: str,
        redeemer_display_name: str,
        wish_text: str,
        past_sessions: list[dict] | None = None,
    ) -> bool:
        """Start a new wish session.

        Args:
            session_id: Database ID for this session
            redeemer_user_id: Twitch user ID
            redeemer_username: Twitch username
            redeemer_display_name: Twitch display name
            wish_text: The wish from channel point redemption
            past_sessions: Previous sessions by this user (for repeat visitor detection)

        Returns:
            True if session started, False if another session is active.
        """
        async with self._lock:
            if self.is_active:
                logger.warning("Cannot start session - another session is active")
                return False

            self._session = SessionData(
                session_id=session_id,
                redeemer_user_id=redeemer_user_id,
                redeemer_username=redeemer_username,
                redeemer_display_name=redeemer_display_name,
                wish_text=wish_text,
            )
            self._cancelled = False

            # Clear message queue
            while not self._message_queue.empty():
                try:
                    self._message_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

        logger.info(f"Santa session started for {redeemer_display_name}: {wish_text[:50]}...")

        # Build initial message with repeat visitor context if applicable
        user_message = wish_text
        if past_sessions:
            context_lines = ["[RETURNING VISITOR ALERT]", f"This person ({redeemer_display_name}) has visited before:"]
            for ps in past_sessions[-3:]:  # Last 3 visits
                context_lines.append(f"- Wished for \"{ps.get('wish_text', '?')[:50]}\" - Outcome: {ps.get('outcome', '?')}")
            context_lines.append("")
            context_lines.append("Consider calling them out playfully if they're trying to get greedy!")
            context_lines.append("")
            context_lines.append(f"Their new wish: {wish_text}")
            user_message = "\n".join(context_lines)

        # Process the initial wish
        await self._process_turn(user_message)
        return True

    async def cancel_session(self, outcome: str = "cancelled") -> None:
        """Cancel the current session."""
        async with self._lock:
            if self._session:
                self._session.state = SantaState.COMPLETE
                self._session.outcome = outcome
                self._cancelled = True
                logger.info(f"Santa session cancelled: {outcome}")
                await self._notify_state_change()

    async def receive_chat_message(self, user_id: str, username: str, message: str) -> None:
        """Receive a chat message (called by Twitch chat handler).

        Only processes messages from the active redeemer during ASK_FOLLOWUP state.
        """
        if not self._session:
            return

        # Only accept messages from the redeemer during ASK_FOLLOWUP
        if self._session.state == SantaState.ASK_FOLLOWUP:
            if user_id == self._session.redeemer_user_id:
                await self._message_queue.put((user_id, username, message))

    async def force_verdict(self, verdict: str) -> bool:
        """Force a grant/deny verdict from dashboard.

        Args:
            verdict: "grant" or "deny"

        Returns:
            True if verdict was applied.
        """
        if not self._session or self._session.state == SantaState.COMPLETE:
            return False

        if verdict not in ("grant", "deny"):
            return False

        # Send forced verdict message to LLM
        self._session.conversation.append({
            "role": "user",
            "content": f"[DASHBOARD OVERRIDE] Force verdict: {verdict.upper()}"
        })

        await self._process_turn(f"The elves have spoken! Verdict: {verdict}")
        return True

    async def speak_direct(self, text: str) -> bool:
        """Speak directly as Santa (for Mall Director), using the speech lock.

        This ensures Mall Director messages don't overlap with ongoing Santa speech.

        Args:
            text: Text to speak via TTS

        Returns:
            True if speech was sent successfully.
        """
        try:
            await self._speak(text)
            return True
        except Exception as e:
            logger.error(f"Error in speak_direct: {e}")
            return False

    async def interrupt_with_message(self, message: str) -> bool:
        """Send a message through the LLM as an interruption (Mall Director style).

        This uses the speech lock to prevent overlapping speech.

        Args:
            message: The message to send (will be prefixed as MALL DIRECTOR INTERRUPTION)

        Returns:
            True if successful.
        """
        try:
            # Use LLM to generate a response
            llm_client = OpenRouterClient()

            # Build a simple conversation for the interruption
            system_prompt = await self._get_system_prompt()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]

            # Get response (non-streaming, just need the text)
            response = await llm_client.chat(
                messages=messages,
                model="openai/gpt-4o-mini",  # Fast model for quick responses
            )

            if response:
                await self._speak(response)
                return True
            return False

        except Exception as e:
            logger.error(f"Error in interrupt_with_message: {e}")
            return False

    async def send_message(self, message: str) -> bool:
        """Send a message as the "child" from dashboard.

        Args:
            message: Message to send

        Returns:
            True if message was processed.
        """
        if not self._session or self._session.state == SantaState.COMPLETE:
            return False

        await self._process_turn(message)
        return True

    # -------------------------------------------------------------------------
    # Core Processing
    # -------------------------------------------------------------------------

    async def _process_turn(self, user_message: str) -> None:
        """Process a turn in the conversation.

        1. Add user message to conversation
        2. Call LLM with JSON schema enforcement
        3. Parse response and determine action
        4. Send speech to TTS
        5. Transition state based on action
        """
        if self._cancelled or not self._session:
            return

        self._session.state = SantaState.PROCESSING
        await self._notify_state_change()

        # Add user message to conversation
        self._session.conversation.append({"role": "user", "content": user_message})

        # Build messages for LLM
        messages = [{"role": "system", "content": SANTA_SYSTEM_PROMPT}]
        messages.extend(self._session.conversation)

        # Call LLM (non-streaming with JSON schema)
        try:
            client = OpenRouterClient()
            try:
                response_text = await client.chat(
                    messages=messages,
                    model=SANTA_MODEL,
                    temperature=0.8,
                    max_tokens=512,
                    response_format=SANTA_RESPONSE_FORMAT,
                )
            finally:
                await client.close()

            # Parse JSON response
            santa_response = self._parse_response(response_text)

            # Add assistant response to conversation
            self._session.conversation.append({
                "role": "assistant",
                "content": response_text,
                "parsed_speech": santa_response.speech,
                "parsed_action": santa_response.action,
            })

            # Send speech to TTS
            if santa_response.speech and not self._cancelled:
                await self._speak(santa_response.speech)

            # Handle action
            await self._handle_action(santa_response.action)

        except Exception as e:
            logger.error(f"Error in Santa turn: {e}")
            # Try to recover with a fallback message
            await self._speak("Ho ho ho! Santa's magic seems to be having a little trouble. Let me try again!")
            self._session.state = SantaState.COMPLETE
            self._session.outcome = "error"
            await self._notify_state_change()

    def _parse_response(self, text: str) -> SantaResponse:
        """Parse JSON response from LLM."""
        try:
            # Try direct JSON parse first
            data = json.loads(text)
            return SantaResponse(
                speech=data.get("speech", ""),
                action=data.get("action", "await_chat"),
                raw=text,
            )
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from text (may be wrapped in markdown)
        import re
        json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return SantaResponse(
                    speech=data.get("speech", ""),
                    action=data.get("action", "await_chat"),
                    raw=json_match.group(),
                )
            except json.JSONDecodeError:
                pass

        # Fallback: treat entire response as speech
        logger.warning(f"Failed to parse JSON from Santa LLM: {text[:100]}")
        return SantaResponse(
            speech=text.strip(),
            action="await_chat",
            raw=text,
        )

    async def _handle_action(self, action: str) -> None:
        """Handle the action from LLM response."""
        if self._cancelled or not self._session:
            return

        if action == "ask_followup":
            if self._session.followup_count >= self.max_followups:
                # Max followups reached, force await_chat
                logger.info("Max followups reached, transitioning to await_chat")
                self._session.state = SantaState.AWAIT_CHAT
                await self._notify_state_change()
                await self._wait_for_chat_vote()
            else:
                self._session.followup_count += 1
                self._session.state = SantaState.ASK_FOLLOWUP
                await self._notify_state_change()
                await self._wait_for_followup()

        elif action == "await_chat":
            self._session.state = SantaState.AWAIT_CHAT
            await self._notify_state_change()
            await self._wait_for_chat_vote()

        elif action in ("grant", "deny"):
            self._session.state = SantaState.COMPLETE
            self._session.outcome = action
            await self._notify_state_change()
            logger.info(f"Santa session complete: {action}")

        else:
            logger.warning(f"Unknown action: {action}, defaulting to await_chat")
            self._session.state = SantaState.AWAIT_CHAT
            await self._notify_state_change()
            await self._wait_for_chat_vote()

    async def _speak(self, text: str) -> None:
        """Send text to TTS via character speak endpoint and wait for audio to finish.

        Uses a lock to prevent overlapping speech - subsequent calls wait for previous to finish.
        """
        async with self._speech_lock:
            try:
                import httpx
                logger.info(f"Santa speaking: {text[:50]}...")
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"http://localhost:8080/api/characters/{self.character_name}/speak",
                        json={"text": text},
                        timeout=60.0,
                    )
                    if response.status_code != 200:
                        logger.error(f"TTS speak failed: {response.text}")
                        return

                # Wait for audio to finish playing
                # Estimate ~100ms per character for speech (roughly 600 chars/minute)
                # Add 1 second buffer for TTS processing and network latency
                estimated_duration = len(text) * 0.1 + 1.0
                logger.debug(f"Waiting {estimated_duration:.1f}s for audio playback...")
                await asyncio.sleep(estimated_duration)

            except Exception as e:
                logger.error(f"Error sending speech to TTS: {e}")

    # -------------------------------------------------------------------------
    # Message Collection
    # -------------------------------------------------------------------------

    async def _wait_for_followup(self) -> None:
        """Wait for followup response from redeemer with debouncing."""
        if self._cancelled or not self._session:
            return

        logger.info(f"Waiting for followup from {self._session.redeemer_display_name}...")

        collected_messages: list[str] = []
        first_message_time: float | None = None

        try:
            while not self._cancelled:
                # Calculate remaining time
                if first_message_time is None:
                    timeout = self.response_timeout
                else:
                    # After first message, use debounce timeout
                    elapsed = asyncio.get_event_loop().time() - first_message_time
                    remaining_debounce = self.debounce_seconds - elapsed
                    if remaining_debounce <= 0:
                        break
                    timeout = remaining_debounce

                try:
                    user_id, username, message = await asyncio.wait_for(
                        self._message_queue.get(),
                        timeout=timeout
                    )

                    collected_messages.append(message)
                    if first_message_time is None:
                        first_message_time = asyncio.get_event_loop().time()
                        logger.info(f"Received first message, waiting {self.debounce_seconds}s for more...")

                except asyncio.TimeoutError:
                    if first_message_time is None:
                        # No message received within timeout
                        logger.info("Followup timeout - no response received")
                        self._session.state = SantaState.COMPLETE
                        self._session.outcome = "timeout"
                        await self._speak("Ho ho ho! Looks like the little one got shy. Maybe next time!")
                        await self._notify_state_change()
                        return
                    else:
                        # Debounce timeout - done collecting
                        break

        except asyncio.CancelledError:
            return

        if collected_messages and not self._cancelled:
            # Combine all messages and process
            combined = " ".join(collected_messages)
            logger.info(f"Collected {len(collected_messages)} messages: {combined[:50]}...")
            await self._process_turn(combined)

    async def _wait_for_chat_vote(self) -> None:
        """Wait for chat voting period and collect responses."""
        if self._cancelled or not self._session:
            return

        logger.info(f"Waiting {self.chat_vote_seconds}s for elf council (chat) verdict...")

        # Wait for voting period
        await asyncio.sleep(self.chat_vote_seconds)

        if self._cancelled or not self._session:
            return

        # Collect recent chat messages from EventSub buffer
        chat_messages = []
        if self.eventsub and self.eventsub.is_connected:
            # Get messages from the voting period
            raw_messages = await self.eventsub.get_raw_messages(seconds=self.chat_vote_seconds + 5)
            chat_messages = [f"[{m.user_display_name}]: {m.message}" for m in raw_messages]

        # Build verdict prompt
        if chat_messages:
            chat_context = "\n".join(chat_messages[-20:])  # Last 20 messages
            verdict_message = f"""[ELF COUNCIL VERDICT]
The elves have spoken! Here's what they said:

{chat_context}

Based on their feedback, make your final judgment. Use action "grant" or "deny"."""
        else:
            verdict_message = """[ELF COUNCIL VERDICT]
The elves are silent... No one spoke up for or against this wish.
Make your own judgment based on the wish. Use action "grant" or "deny"."""

        # Process the verdict
        await self._process_turn(verdict_message)

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------

    def get_conversation_json(self) -> str:
        """Get conversation history as JSON string."""
        if not self._session:
            return "[]"
        return json.dumps(self._session.conversation)

    def get_session_status(self) -> dict:
        """Get current session status for API response."""
        if not self._session:
            return {
                "active": False,
                "session_id": None,
                "redeemer_display_name": None,
                "wish_text": None,
                "state": None,
                "followup_count": 0,
                "started_at": None,
            }

        return {
            "active": self._session.state != SantaState.COMPLETE,
            "session_id": self._session.session_id,
            "redeemer_display_name": self._session.redeemer_display_name,
            "wish_text": self._session.wish_text,
            "state": self._session.state.value,
            "followup_count": self._session.followup_count,
            "started_at": None,  # Would need to track this
        }
