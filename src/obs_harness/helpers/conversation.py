"""Conversation memory management helpers.

Provides CRUD operations for character conversation history.
Supports both in-memory and persistent (database) storage.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from sqlmodel import select

from ..database import get_session
from ..models import Character, ConversationMessage

if TYPE_CHECKING:
    from ..state import AppState

logger = logging.getLogger(__name__)


def parse_message_content(content: str) -> str | list:
    """Parse message content, deserializing JSON if it's multimodal."""
    if content.startswith("["):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
    return content


async def get_conversation_messages(
    state: "AppState",
    tenant_id: str,
    character_name: str,
    persist: bool,
) -> list[dict]:
    """Get conversation messages for a character."""
    if persist:
        async with get_session() as session:
            result = await session.execute(
                select(ConversationMessage)
                .where(
                    ConversationMessage.tenant_id == tenant_id,
                    ConversationMessage.character_name == character_name
                )
                .order_by(ConversationMessage.created_at)
            )
            messages = list(result.scalars().all())
            return [
                {
                    "role": m.role,
                    "content": parse_message_content(m.content),
                    "interrupted": m.interrupted,
                    "generated_text": m.generated_text,
                }
                for m in messages
            ]
    else:
        key = state.tenant_key(tenant_id, character_name)
        return state.conversation_memory.get(key, [])


async def save_conversation_message(
    state: "AppState",
    tenant_id: str,
    character_name: str,
    role: str,
    content: str | list,
    persist: bool,
    interrupted: bool = False,
    generated_text: str | None = None,
) -> tuple[int, int | None]:
    """Save a conversation message. Returns (in-memory index, db_id or None).

    Content can be a string or a list (for multimodal messages with images).
    Lists are JSON-serialized for database storage.
    """
    # For database storage, serialize list content to JSON
    db_content = json.dumps(content) if isinstance(content, list) else content
    key = state.tenant_key(tenant_id, character_name)

    msg = {
        "role": role,
        "content": content,  # Keep as list in memory for API format
        "interrupted": interrupted,
        "generated_text": generated_text,
    }

    if persist:
        async with get_session() as session:
            db_msg = ConversationMessage(
                tenant_id=tenant_id,
                character_name=character_name,
                role=role,
                content=db_content,  # JSON string for lists
                interrupted=interrupted,
                generated_text=generated_text,
            )
            session.add(db_msg)
            await session.commit()
            await session.refresh(db_msg)
            # Also keep in memory for current session
            if key not in state.conversation_memory:
                state.conversation_memory[key] = []
            state.conversation_memory[key].append(msg)
            return len(state.conversation_memory[key]) - 1, db_msg.id
    else:
        if key not in state.conversation_memory:
            state.conversation_memory[key] = []
        state.conversation_memory[key].append(msg)
        return len(state.conversation_memory[key]) - 1, None


async def update_interrupted_message(
    state: "AppState",
    tenant_id: str,
    character_name: str,
    msg_idx: int,
    actual_content: str,
    persist: bool,
    db_msg_id: int | None,
) -> None:
    """Update an interrupted message with the actual spoken content."""
    key = state.tenant_key(tenant_id, character_name)
    # Update in-memory
    if key in state.conversation_memory and msg_idx < len(state.conversation_memory[key]):
        state.conversation_memory[key][msg_idx]["content"] = actual_content

    # Update in database if persisted
    if persist and db_msg_id is not None:
        async with get_session() as session:
            result = await session.execute(
                select(ConversationMessage).where(ConversationMessage.id == db_msg_id)
            )
            db_msg = result.scalar_one_or_none()
            if db_msg:
                db_msg.content = actual_content
                await session.commit()


async def clear_conversation_messages(
    state: "AppState",
    tenant_id: str,
    character_name: str,
    persist: bool,
) -> None:
    """Clear all conversation messages for a character."""
    key = state.tenant_key(tenant_id, character_name)
    # Clear in-memory
    if key in state.conversation_memory:
        del state.conversation_memory[key]

    # Clear from database if persisted
    if persist:
        async with get_session() as session:
            result = await session.execute(
                select(ConversationMessage).where(
                    ConversationMessage.tenant_id == tenant_id,
                    ConversationMessage.character_name == character_name
                )
            )
            messages = list(result.scalars().all())
            for msg in messages:
                await session.delete(msg)
            await session.commit()


async def load_persisted_memory_on_startup(state: "AppState") -> None:
    """Load persisted memory into in-memory cache on startup."""
    async with get_session() as session:
        # Get all characters with persist_memory enabled
        result = await session.execute(
            select(Character).where(Character.persist_memory == True)
        )
        characters = list(result.scalars().all())

        for char in characters:
            # Load their messages into memory using tenant-scoped key
            msg_result = await session.execute(
                select(ConversationMessage)
                .where(
                    ConversationMessage.tenant_id == char.tenant_id,
                    ConversationMessage.character_name == char.name
                )
                .order_by(ConversationMessage.created_at)
            )
            messages = list(msg_result.scalars().all())
            if messages:
                key = state.tenant_key(char.tenant_id, char.name)
                state.conversation_memory[key] = [
                    {
                        "role": m.role,
                        "content": m.content,
                        "interrupted": m.interrupted,
                        "generated_text": m.generated_text,
                    }
                    for m in messages
                ]
                logger.info(f"Loaded {len(messages)} persisted messages for {char.tenant_id}:{char.name}")
