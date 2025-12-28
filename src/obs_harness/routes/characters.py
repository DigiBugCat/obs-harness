"""Character API routes.

Handles character CRUD, speak, chat, stop, and memory operations.
"""

import json
import logging
import secrets
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlmodel import select

from ..auth import require_auth
from ..chat_pipeline import ChatPipeline, ChatPipelineConfig
from ..database import get_session
from ..helpers.conversation import (
    clear_conversation_messages,
    get_conversation_messages,
    save_conversation_message,
)
from ..helpers.generation import cancel_active_generation
from ..helpers.keys import get_api_key
from ..models import (
    Character,
    CharacterCreate,
    CharacterResponse,
    CharacterUpdate,
    ChatRequest,
    ChatResponse,
    Moderator,
    SpeakRequest,
    get_character_tts_config,
)
from ..tts import (
    TTSProviderType,
    ElevenLabsWSError,
    CartesiaWSError,
    KokoroError,
    ElevenLabsSettings,
    CartesiaSettings,
    KokoroSettings,
)
from ..tts_pipeline import TTSStreamer, TTSStreamConfig, TextDisplayConfig
from . import get_state
from ..state import AppState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/characters", tags=["Characters"])


async def get_effective_tenant(
    channel: str | None,
    tenant_id: str,
) -> str:
    """Get effective tenant ID, validating moderator access if channel specified.

    Args:
        channel: Optional channel (tenant_id) to view. If None, returns tenant_id.
        tenant_id: The authenticated user's tenant_id.

    Returns:
        The effective tenant_id to use for queries.

    Raises:
        HTTPException: If user doesn't have moderator access to the channel.
    """
    if not channel or channel == tenant_id:
        return tenant_id

    # Verify user has moderator access to this channel
    async with get_session() as session:
        result = await session.execute(
            select(Moderator).where(
                Moderator.broadcaster_tenant_id == channel,
                Moderator.moderator_user_id == tenant_id,
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Not authorized for this channel")

    return channel


def _validate_tts_settings(provider: str | None, tts_settings: dict | None) -> None:
    """Validate TTS settings match the provider schema.

    Raises:
        HTTPException: If settings are invalid for the provider
    """
    if not tts_settings:
        return  # No settings to validate

    provider_type = TTSProviderType(provider or "elevenlabs")

    try:
        if provider_type == TTSProviderType.ELEVENLABS:
            ElevenLabsSettings(**tts_settings)
        elif provider_type == TTSProviderType.CARTESIA:
            CartesiaSettings(**tts_settings)
        elif provider_type == TTSProviderType.KOKORO:
            KokoroSettings(**tts_settings)
    except ValidationError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid TTS settings for {provider_type.value}: {e.errors()}"
        )


def _character_to_response(c: Character, state: AppState) -> CharacterResponse:
    """Convert a Character model to CharacterResponse with connection status."""
    # Use tenant-scoped key for connection state
    channel_key = state.tenant_key(c.tenant_id, c.name)
    return CharacterResponse(
        id=c.id,
        name=c.name,
        description=c.description,
        color=c.color,
        icon=c.icon,
        default_volume=c.default_volume,
        mute_state=c.mute_state,
        default_text_style=c.default_text_style,
        text_font_family=c.text_font_family,
        text_font_size=c.text_font_size,
        text_color=c.text_color,
        text_stroke_color=c.text_stroke_color,
        text_stroke_width=c.text_stroke_width,
        text_position_x=c.text_position_x,
        text_position_y=c.text_position_y,
        text_duration=c.text_duration,
        elevenlabs_voice_id=c.elevenlabs_voice_id,
        elevenlabs_model_id=c.elevenlabs_model_id,
        voice_stability=c.voice_stability,
        voice_similarity_boost=c.voice_similarity_boost,
        voice_style=c.voice_style,
        voice_speed=c.voice_speed,
        system_prompt=c.system_prompt,
        model=c.model,
        provider=c.provider,
        temperature=c.temperature,
        max_tokens=c.max_tokens,
        twitch_chat_enabled=c.twitch_chat_enabled,
        twitch_chat_window_seconds=c.twitch_chat_window_seconds,
        twitch_chat_max_messages=c.twitch_chat_max_messages,
        memory_enabled=c.memory_enabled,
        persist_memory=c.persist_memory,
        tts_provider=c.tts_provider,
        tts_settings=json.loads(c.tts_settings) if c.tts_settings else None,
        ws_token=c.ws_token,
        connected=state.manager.is_connected(channel_key),
        playing=state.manager._channel_state.get(channel_key, {}).get("playing", False),
        streaming=state.manager._channel_state.get(channel_key, {}).get("streaming", False),
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


async def _broadcast_all_characters(state: AppState, tenant_id: str) -> None:
    """Fetch all characters for tenant from DB and broadcast to dashboard clients."""
    async with get_session() as session:
        result = await session.execute(
            select(Character).where(Character.tenant_id == tenant_id)
        )
        characters = list(result.scalars().all())
        char_dicts = [_character_to_response(c, state).model_dump() for c in characters]
        await state.manager.broadcast_character_sync(char_dicts, tenant_id)


@router.post("", status_code=201)
async def create_character(
    request: CharacterCreate,
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> Character:
    """Create a new character."""
    logger.info(f"POST /api/characters - creating \"{request.name}\" for tenant {tenant_id}")

    # Validate TTS settings before saving
    _validate_tts_settings(request.tts_provider, request.tts_settings)

    async with get_session() as session:
        # Check if character already exists for this tenant
        result = await session.execute(
            select(Character).where(
                Character.tenant_id == tenant_id,
                Character.name == request.name
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Character already exists")

        # Serialize tts_settings dict to JSON string for storage
        data = request.model_dump()
        if data.get("tts_settings") is not None:
            data["tts_settings"] = json.dumps(data["tts_settings"])

        # Generate WebSocket auth token for OBS browser sources
        ws_token = secrets.token_urlsafe(32)

        character = Character(tenant_id=tenant_id, ws_token=ws_token, **data)
        session.add(character)
        await session.commit()
        await session.refresh(character)
        await state.manager._notify_dashboard()
        await _broadcast_all_characters(state, tenant_id)
        return character


@router.get("")
async def list_characters(
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
    channel: str | None = Query(default=None, description="Channel to view (requires moderator access)"),
) -> list[CharacterResponse]:
    """List all characters for a channel with connection status.

    If channel is specified, verifies the user has moderator access.
    """
    effective_tenant = await get_effective_tenant(channel, tenant_id)

    async with get_session() as session:
        result = await session.execute(
            select(Character).where(Character.tenant_id == effective_tenant)
        )
        characters = list(result.scalars().all())

        # Generate tokens for any characters that don't have one (migration)
        for c in characters:
            if not c.ws_token:
                c.ws_token = secrets.token_urlsafe(32)
                session.add(c)

        return [_character_to_response(c, state) for c in characters]


@router.get("/{name}")
async def get_character(
    name: str,
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> CharacterResponse:
    """Get a character by name."""
    async with get_session() as session:
        result = await session.execute(
            select(Character).where(
                Character.tenant_id == tenant_id,
                Character.name == name
            )
        )
        character = result.scalar_one_or_none()
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

        # Generate token if missing (migration)
        if not character.ws_token:
            character.ws_token = secrets.token_urlsafe(32)
            session.add(character)

        return _character_to_response(character, state)


@router.put("/{name}")
async def update_character(
    name: str,
    request: CharacterUpdate,
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> Character:
    """Update a character."""
    logger.debug(f"PUT /api/characters/{name} - updating for tenant {tenant_id}")

    async with get_session() as session:
        result = await session.execute(
            select(Character).where(
                Character.tenant_id == tenant_id,
                Character.name == name
            )
        )
        character = result.scalar_one_or_none()
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

        # Optimistic concurrency control - reject if record was modified since client loaded it
        if request.expected_updated_at is not None:
            if character.updated_at != request.expected_updated_at:
                raise HTTPException(
                    status_code=409,
                    detail="Character was modified by another client. Please refresh and try again."
                )

        # Validate TTS settings if being updated
        # Use new provider if specified, otherwise use character's current provider
        provider_for_validation = request.tts_provider if request.tts_provider is not None else character.tts_provider
        if request.tts_settings is not None:
            _validate_tts_settings(provider_for_validation, request.tts_settings)

        update_data = request.model_dump(exclude_unset=True, exclude={"expected_updated_at"})
        # Serialize tts_settings dict to JSON string for storage
        if "tts_settings" in update_data and update_data["tts_settings"] is not None:
            update_data["tts_settings"] = json.dumps(update_data["tts_settings"])
        for key, value in update_data.items():
            setattr(character, key, value)
        character.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(character)
        await state.manager._notify_dashboard()
        await _broadcast_all_characters(state, tenant_id)
        return character


@router.delete("/{name}")
async def delete_character(
    name: str,
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Delete a character. Disconnects any active connection."""
    logger.info(f"DELETE /api/characters/{name} for tenant {tenant_id}")

    async with get_session() as session:
        result = await session.execute(
            select(Character).where(
                Character.tenant_id == tenant_id,
                Character.name == name
            )
        )
        character = result.scalar_one_or_none()
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

        # Disconnect if connected
        if state.manager.is_connected(name):
            state.manager.disconnect(name)

        await session.delete(character)
        await session.commit()
        await state.manager._notify_dashboard()
        await _broadcast_all_characters(state, tenant_id)
        return {"success": True, "deleted": name}


@router.post("/{name}/speak")
async def character_speak(
    name: str,
    request: SpeakRequest,
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Speak text directly using character's voice (no AI).

    This endpoint:
    1. Looks up the character configuration
    2. Streams TTS audio to the connected browser
    """
    start_time = time.time()
    text_preview = request.text[:50] + "..." if len(request.text) > 50 else request.text
    logger.info(f"POST /api/characters/{name}/speak - \"{text_preview}\" ({len(request.text)} chars)")

    # Look up character
    async with get_session() as session:
        result = await session.execute(
            select(Character).where(
                Character.tenant_id == tenant_id,
                Character.name == name
            )
        )
        character = result.scalar_one_or_none()
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

    # Get TTS provider and settings
    try:
        provider, tts_settings = get_character_tts_config(character)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Get tenant-specific API key (falls back to global)
    tts_api_key = await get_api_key(tenant_id, provider.value)
    if not tts_api_key:
        raise HTTPException(
            status_code=500,
            detail=f"{provider.value.upper()}_API_KEY not configured. Add it in Settings or set environment variable.",
        )

    # Use tenant-scoped channel key for WebSocket operations
    channel_key = state.tenant_key(tenant_id, name)

    # Verify character is connected
    if not state.manager.is_connected(channel_key):
        raise HTTPException(
            status_code=400, detail=f"Character '{name}' is not connected"
        )

    # Create TTS and text display configs
    tts_config = TTSStreamConfig(
        provider=provider,
        settings=tts_settings,
        api_key=tts_api_key,
    )
    text_config = TextDisplayConfig(
        font_family=character.text_font_family,
        font_size=character.text_font_size,
        color=character.text_color,
        stroke_color=character.text_stroke_color,
        stroke_width=character.text_stroke_width,
        position_x=character.text_position_x,
        position_y=character.text_position_y,
    )

    harness = state.harness

    # Create unified TTS streamer with browser callbacks
    streamer = TTSStreamer(
        tts_config=tts_config,
        text_config=text_config,
        show_text=request.show_text,
        send_text_start=lambda: harness.text_stream_start(
            channel_key,
            font_family=text_config.font_family,
            font_size=text_config.font_size,
            color=text_config.color,
            stroke_color=text_config.stroke_color,
            stroke_width=text_config.stroke_width,
            position_x=text_config.position_x,
            position_y=text_config.position_y,
        ),
        send_text_end=lambda: harness.text_stream_end(channel_key),
        send_audio_start=lambda: harness.stream_start(channel_key, sample_rate=24000, channels=1),
        send_audio_chunk=lambda audio: harness.stream_audio(channel_key, audio),
        send_audio_end=lambda: harness.stream_end(channel_key),
        send_word_timing=lambda words: harness.word_timing(channel_key, words),
    )

    # Acquire lock for entire streaming operation to prevent concurrent requests
    gen_key = state.tenant_key(tenant_id, name)
    async with state.get_generation_lock(tenant_id, name):
        if gen_key in state.active_generations:
            await cancel_active_generation(state, tenant_id, name)
            await harness.stop_stream(channel_key)
        state.active_generations[gen_key] = streamer

        try:
            await streamer.stream(request.text)
            await harness._log_playback(channel_key, request.text, "stream")
            elapsed = time.time() - start_time
            logger.info(f"POST /api/characters/{name}/speak - completed in {elapsed:.2f}s")
            return {"success": True, "character": name}
        except (ElevenLabsWSError, CartesiaWSError, KokoroError) as e:
            await harness.stop_stream(channel_key)
            logger.error(f"POST /api/characters/{name}/speak - TTS error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            await harness.stop_stream(channel_key)
            logger.error(f"POST /api/characters/{name}/speak - error: {e}")
            raise HTTPException(status_code=500, detail=f"TTS error: {e}")
        finally:
            state.active_generations.pop(gen_key, None)


@router.post("/{name}/chat")
async def character_chat(
    name: str,
    request: ChatRequest,
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> ChatResponse:
    """Chat with a character - streams LLM response through TTS to browser.

    This endpoint:
    1. Looks up the character configuration
    2. Validates system_prompt is set (required for AI chat)
    3. Streams LLM response tokens through TTS (ElevenLabs or Cartesia)
    4. Sends audio and text to the browser in real-time
    """
    start_time = time.time()
    msg_preview = request.message[:50] + "..." if len(request.message) > 50 else request.message
    logger.info(f"POST /api/characters/{name}/chat - \"{msg_preview}\"")

    # Get tenant-specific OpenRouter API key (required for LLM)
    openrouter_api_key = await get_api_key(tenant_id, "openrouter")
    if not openrouter_api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY not configured. Add it in Settings or set environment variable.",
        )

    # Look up character
    async with get_session() as session:
        result = await session.execute(
            select(Character).where(
                Character.tenant_id == tenant_id,
                Character.name == name
            )
        )
        character = result.scalar_one_or_none()
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

    # Validate system_prompt is set (required for AI chat)
    if not character.system_prompt:
        raise HTTPException(
            status_code=400,
            detail="Character has no system_prompt configured. Use /speak endpoint for direct TTS.",
        )

    # Get TTS provider and settings
    try:
        provider, tts_settings = get_character_tts_config(character)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Get tenant-specific TTS API key (falls back to global)
    tts_api_key = await get_api_key(tenant_id, provider.value)
    if not tts_api_key:
        raise HTTPException(
            status_code=500,
            detail=f"{provider.value.upper()}_API_KEY not configured. Add it in Settings or set environment variable.",
        )

    # Use tenant-scoped channel key for WebSocket operations
    channel_key = state.tenant_key(tenant_id, name)

    # Verify character is connected
    if not state.manager.is_connected(channel_key):
        raise HTTPException(
            status_code=400, detail=f"Character '{name}' is not connected"
        )

    # Determine twitch chat seconds (request override or character default)
    # request.twitch_chat_seconds == 0 means disabled for this request
    # request.twitch_chat_seconds == None means use character default
    twitch_seconds = request.twitch_chat_seconds
    if twitch_seconds is None:
        twitch_seconds = character.twitch_chat_window_seconds if character.twitch_chat_enabled else 0

    # Get Twitch chat context if enabled (using EventSub)
    twitch_chat_context = None
    eventsub_mgr = state.eventsub_managers.get(tenant_id)
    if twitch_seconds > 0 and eventsub_mgr and eventsub_mgr.is_connected:
        twitch_chat_context = await eventsub_mgr.get_chat_context(
            seconds=twitch_seconds,
            max_messages=character.twitch_chat_max_messages,
        )

    # Get conversation history if memory is enabled
    history = None
    gen_key = state.tenant_key(tenant_id, name)
    if character.memory_enabled:
        all_history = state.conversation_memory.get(gen_key, [])
        # Include user/assistant/context messages, converting context to user role
        history = []
        for m in all_history:
            role = m.get("role")
            if role in ("user", "assistant"):
                history.append({"role": role, "content": m["content"]})
            elif role == "context":
                # Include Twitch chat context as a user message so LLM remembers it
                history.append({"role": "user", "content": f"[Twitch chat at the time]:\n{m['content']}"})

    # Create TTS and text display configs
    tts_config = TTSStreamConfig(
        provider=provider,
        settings=tts_settings,
        api_key=tts_api_key,
    )
    text_config = TextDisplayConfig(
        font_family=character.text_font_family,
        font_size=character.text_font_size,
        color=character.text_color,
        stroke_color=character.text_stroke_color,
        stroke_width=character.text_stroke_width,
        position_x=character.text_position_x,
        position_y=character.text_position_y,
    )

    harness = state.harness

    # Create unified TTS streamer with browser callbacks
    tts_streamer = TTSStreamer(
        tts_config=tts_config,
        text_config=text_config,
        show_text=request.show_text,
        send_text_start=lambda: harness.text_stream_start(
            channel_key,
            font_family=text_config.font_family,
            font_size=text_config.font_size,
            color=text_config.color,
            stroke_color=text_config.stroke_color,
            stroke_width=text_config.stroke_width,
            position_x=text_config.position_x,
            position_y=text_config.position_y,
        ),
        send_text_end=lambda: harness.text_stream_end(channel_key),
        send_audio_start=lambda: harness.stream_start(channel_key, sample_rate=24000, channels=1),
        send_audio_chunk=lambda audio: harness.stream_audio(channel_key, audio),
        send_audio_end=lambda: harness.stream_end(channel_key),
        send_word_timing=lambda words: harness.word_timing(channel_key, words),
    )

    # Create LLM pipeline configuration
    images = None
    if request.images:
        images = [{"data": img.data, "media_type": img.media_type} for img in request.images]

    pipeline_config = ChatPipelineConfig(
        system_prompt=character.system_prompt,
        model=character.model,
        provider=character.provider,
        temperature=character.temperature,
        max_tokens=character.max_tokens,
        twitch_chat_context=twitch_chat_context,
        conversation_history=history,
        images=images,
        api_key=openrouter_api_key,
    )

    # Create and run pipeline
    pipeline = ChatPipeline(
        config=pipeline_config,
        tts_streamer=tts_streamer,
    )

    # Acquire lock for entire pipeline operation to prevent concurrent requests
    async with state.get_generation_lock(tenant_id, name):
        if gen_key in state.active_generations:
            # Cancel the previous generation - it will save its own interrupted state
            await cancel_active_generation(state, tenant_id, name)
            await harness.stop_stream(channel_key)
        state.active_generations[gen_key] = pipeline

        try:
            response_text = await pipeline.run(request.message)

            # Store conversation in memory
            # Store twitch context if present
            if twitch_chat_context:
                await save_conversation_message(
                    state, tenant_id, name, "context", twitch_chat_context, character.persist_memory
                )
            # Build user content - multimodal if images present
            if images:
                user_content: str | list = [{"type": "text", "text": request.message}]
                for img in images:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{img['media_type']};base64,{img['data']}"}
                    })
            else:
                user_content = request.message
            await save_conversation_message(
                state, tenant_id, name, "user", user_content, character.persist_memory
            )

            # Check if we were cancelled (interrupted by stop button or new chat)
            if pipeline._cancelled:
                # Save as interrupted - browser will update content with actual spoken text
                spoken_text = pipeline.get_spoken_text()
                if spoken_text:
                    msg_idx, db_id = await save_conversation_message(
                        state=state,
                        tenant_id=tenant_id,
                        character_name=name,
                        role="assistant",
                        content=spoken_text,  # Will be updated by browser's stream_stopped
                        persist=character.persist_memory,
                        interrupted=True,
                        generated_text=response_text,  # Full LLM response for strikethrough
                    )
                    # Track for browser update
                    state.pending_interrupted[gen_key] = (msg_idx, character.persist_memory, db_id)
            else:
                # Normal completion - save full response
                await save_conversation_message(
                    state, tenant_id, name, "assistant", response_text, character.persist_memory
                )
                # Log the chat
                await harness._log_playback(channel_key, f"chat:{name}", "stream")

            elapsed = time.time() - start_time
            response_preview = response_text[:50] + "..." if len(response_text) > 50 else response_text
            logger.info(f"POST /api/characters/{name}/chat - completed in {elapsed:.2f}s - \"{response_preview}\"")

            return ChatResponse(
                success=True,
                character=name,
                response_text=response_text,
                twitch_chat_context=twitch_chat_context,
            )

        except Exception as e:
            # Force stop streams on error and clean up pending state
            state.pending_interrupted.pop(gen_key, None)
            await harness.stop_stream(channel_key)
            logger.error(f"POST /api/characters/{name}/chat - error: {e}")
            raise HTTPException(status_code=500, detail=f"Chat error: {e}")
        finally:
            state.active_generations.pop(gen_key, None)


@router.post("/{name}/stop")
async def stop_character_generation(
    name: str,
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Stop any active generation (speak/chat) for a character.

    Note: The interrupted message is saved by the original chat endpoint
    when it detects it was cancelled, not here.
    """
    was_active = False
    spoken_text = None
    gen_key = state.tenant_key(tenant_id, name)
    channel_key = state.tenant_key(tenant_id, name)  # Same as gen_key, but semantically for WebSocket

    async with state.get_generation_lock(tenant_id, name):
        if gen_key in state.active_generations:
            was_active = True
            # Cancel the generation (sets _cancelled=True)
            spoken_text = await cancel_active_generation(state, tenant_id, name)

    # Always send stop command to browser - audio may still be playing
    # even if generation has already completed
    await state.harness.stop_stream(channel_key)

    if was_active:
        logger.info(f"POST /api/characters/{name}/stop - generation cancelled")
    else:
        logger.debug(f"POST /api/characters/{name}/stop - no active generation")

    return {
        "success": True,
        "character": name,
        "was_active": was_active,
        "spoken_text": spoken_text,
    }


@router.delete("/{name}/memory")
async def clear_character_memory(
    name: str,
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Clear conversation memory for a character."""
    # Look up character to get persist_memory setting
    async with get_session() as session:
        result = await session.execute(
            select(Character).where(
                Character.tenant_id == tenant_id,
                Character.name == name
            )
        )
        character = result.scalar_one_or_none()
        persist = character.persist_memory if character else False

    await clear_conversation_messages(state, tenant_id, name, persist)
    return {"success": True, "character": name, "message": "Memory cleared"}


@router.get("/{name}/memory")
async def get_character_memory(
    name: str,
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Get conversation memory for a character."""
    # Look up character to get persist_memory setting
    async with get_session() as session:
        result = await session.execute(
            select(Character).where(
                Character.tenant_id == tenant_id,
                Character.name == name
            )
        )
        character = result.scalar_one_or_none()
        persist = character.persist_memory if character else False

    history = await get_conversation_messages(state, tenant_id, name, persist)
    return {"character": name, "message_count": len(history), "messages": history}


@router.post("/{name}/rotate-token")
async def rotate_character_token(
    name: str,
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Rotate the WebSocket token for a character.

    This invalidates any existing browser source URLs and generates a new token.
    Use this if a token is accidentally leaked.
    """
    async with get_session() as session:
        result = await session.execute(
            select(Character).where(
                Character.tenant_id == tenant_id,
                Character.name == name
            )
        )
        character = result.scalar_one_or_none()
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

        # Generate new token
        new_token = secrets.token_urlsafe(32)
        character.ws_token = new_token
        session.add(character)
        await session.commit()

        logger.info(f"POST /api/characters/{name}/rotate-token - token rotated")
        return {
            "success": True,
            "character": name,
            "ws_token": new_token,
            "message": "Token rotated. Update your OBS browser source URL.",
        }
