/**
 * Shared TypeScript types for OBS Harness Frontend
 */

// =============================================================================
// DOM Helpers
// =============================================================================

/**
 * Type-safe element getter. Returns null if element not found.
 */
export function getElement<T extends HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}

/**
 * Type-safe element getter that throws if element not found.
 */
export function requireElement<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id) as T | null;
  if (!el) throw new Error(`Element #${id} not found`);
  return el;
}

// =============================================================================
// WebSocket Message Types (Server -> Client)
// =============================================================================

/** Hello message with server version info */
export interface WSHelloMessage {
  type: 'hello';
  version: string;
  build_id: string;
  tenant_id?: string;
}

/** Ping message for heartbeat */
export interface WSPingMessage {
  type?: 'ping';
  action?: 'ping';
  ts: number;
}

/** Play audio file */
export interface WSPlayMessage {
  action: 'play';
  file: string;
  volume?: number;
  loop?: boolean;
}

/** Stop audio playback */
export interface WSStopMessage {
  action: 'stop';
}

/** Set volume level */
export interface WSVolumeMessage {
  action: 'volume';
  level: number;
}

/** Start audio stream */
export interface WSStreamStartMessage {
  action: 'stream_start';
  sample_rate?: number;
  channels?: number;
}

/** End audio stream gracefully */
export interface WSStreamEndMessage {
  action: 'stream_end';
}

/** Force stop audio stream immediately */
export interface WSStopStreamMessage {
  action: 'stop_stream';
}

/** Show text with animation */
export interface WSTextMessage {
  action: 'text';
  text: string;
  style?: string;
  duration?: number;
  position_x?: number;
  position_y?: number;
  font_family?: string;
  font_size?: number;
  color?: string;
  stroke_color?: string;
  stroke_width?: number;
}

/** Clear text display */
export interface WSClearTextMessage {
  action: 'clear_text';
}

/** Start text stream */
export interface WSTextStreamStartMessage {
  action: 'text_stream_start';
  font_family?: string;
  font_size?: number;
  color?: string;
  stroke_color?: string;
  stroke_width?: number;
  position_x?: number;
  position_y?: number;
  instant_reveal?: boolean;
}

/** Text chunk for streaming */
export interface WSTextChunkMessage {
  action: 'text_chunk';
  text: string;
}

/** End text stream */
export interface WSTextStreamEndMessage {
  action: 'text_stream_end';
}

/** Word timing data for synchronized text reveal */
export interface WSWordTimingMessage {
  action: 'word_timing';
  words: Array<{
    word: string;
    start: number;
    end: number;
  }>;
}

/** Characters status update (dashboard) */
export interface WSCharactersMessage {
  type: 'characters';
  characters: Array<{
    name: string;
    playing?: boolean;
    streaming?: boolean;
  }>;
}

/** Character sync update (dashboard) */
export interface WSCharacterSyncMessage {
  type: 'character_sync';
  characters: Character[];
}

/** Santa session status (santa dashboard) */
export interface WSSantaStatusMessage {
  type: 'santa_status';
  status: SantaSessionStatus;
}

/** Union of all server-to-client WebSocket messages */
export type WSServerMessage =
  | WSHelloMessage
  | WSPingMessage
  | WSPlayMessage
  | WSStopMessage
  | WSVolumeMessage
  | WSStreamStartMessage
  | WSStreamEndMessage
  | WSStopStreamMessage
  | WSTextMessage
  | WSClearTextMessage
  | WSTextStreamStartMessage
  | WSTextChunkMessage
  | WSTextStreamEndMessage
  | WSWordTimingMessage
  | WSCharactersMessage
  | WSCharacterSyncMessage
  | WSSantaStatusMessage;

// =============================================================================
// WebSocket Message Types (Client -> Server)
// =============================================================================

/** Pong response to ping */
export interface WSPongEvent {
  event: 'pong';
  ts?: number;
}

/** Audio playback ended */
export interface WSEndedEvent {
  event: 'ended';
  file: string;
}

/** Audio stream ended */
export interface WSStreamEndedEvent {
  event: 'stream_ended';
}

/** Audio stream stopped (interrupted) */
export interface WSStreamStoppedEvent {
  event: 'stream_stopped';
  playback_time: number;
  spoken_text: string;
  word_count: number;
}

/** Text animation complete */
export interface WSTextCompleteEvent {
  event: 'text_complete';
}

/** Text stream complete */
export interface WSTextStreamCompleteEvent {
  event: 'text_stream_complete';
}

/** Error event */
export interface WSErrorEvent {
  event: 'error';
  message: string;
}

/** Union of all client-to-server WebSocket events */
export type WSClientEvent =
  | WSPongEvent
  | WSEndedEvent
  | WSStreamEndedEvent
  | WSStreamStoppedEvent
  | WSTextCompleteEvent
  | WSTextStreamCompleteEvent
  | WSErrorEvent;

// =============================================================================
// API Response Types
// =============================================================================

/** TTS Provider type */
export type TTSProvider = 'elevenlabs' | 'cartesia';

/** ElevenLabs TTS settings */
export interface ElevenLabsSettings {
  voice_id: string;
  model_id?: string;
  stability?: number;
  similarity_boost?: number;
  style?: number;
  use_speaker_boost?: boolean;
}

/** Cartesia TTS settings */
export interface CartesiaSettings {
  voice_id: string;
  model_id?: string;
  language?: string;
  speed?: number;
  emotion?: string;
}

/** TTS settings union */
export type TTSSettings = ElevenLabsSettings | CartesiaSettings;

/** Character configuration */
export interface Character {
  id: number;
  name: string;
  display_name?: string;
  tts_provider: TTSProvider;
  tts_settings: TTSSettings;
  openrouter_model?: string;
  system_prompt?: string;
  text_font_family?: string;
  text_font_size?: number;
  text_color?: string;
  text_stroke_color?: string;
  text_stroke_width?: number;
  text_position_x?: number;
  text_position_y?: number;
  enabled?: boolean;
  persist_memory?: boolean;
  created_at?: string;
  updated_at?: string;
  // Runtime state (from WebSocket status)
  connected?: boolean;
  playing?: boolean;
  streaming?: boolean;
}

/** Text preset configuration */
export interface TextPreset {
  id: number;
  name: string;
  font_family: string;
  font_size: number;
  color: string;
  stroke_color?: string;
  stroke_width?: number;
  position_x?: number;
  position_y?: number;
  animation_style?: string;
}

/** ElevenLabs model */
export interface ElevenLabsModel {
  model_id: string;
  name: string;
  description?: string;
  can_use_style?: boolean;
  can_use_speaker_boost?: boolean;
}

/** ElevenLabs voice */
export interface ElevenLabsVoice {
  voice_id: string;
  name: string;
  category?: string;
  labels?: Record<string, string>;
}

/** Cartesia voice */
export interface CartesiaVoice {
  id: string;
  name: string;
  description?: string;
  language?: string;
}

/** Playback log entry */
export interface PlaybackLogEntry {
  id: number;
  character_name: string;
  action: string;
  text?: string;
  created_at: string;
}

// =============================================================================
// Santa Session Types
// =============================================================================

/** Santa session state */
export type SantaState =
  | 'idle'
  | 'greeting'
  | 'wish_received'
  | 'wish_granted'
  | 'wish_denied'
  | 'followup'
  | 'farewell';

/** Conversation message */
export interface ConversationMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

/** Santa session status */
export interface SantaSessionStatus {
  active: boolean;
  state: SantaState;
  held?: boolean;
  redeemer_display_name?: string;
  wish_text?: string;
  followup_count?: number;
  conversation?: ConversationMessage[];
}

/** Past santa session */
export interface SantaSession {
  id: number;
  redeemer_display_name: string;
  wish_text?: string;
  outcome?: 'granted' | 'denied' | 'cancelled';
  conversation?: ConversationMessage[];
  started_at?: string;
  ended_at?: string;
}

/** Santa configuration */
export interface SantaConfig {
  enabled: boolean;
  character_name: string;
  reward_id?: string;
  chat_vote_seconds?: number;
  max_followups?: number;
  response_timeout?: number;
  debounce_seconds?: number;
}

/** Twitch custom reward */
export interface TwitchReward {
  id: string;
  title: string;
  cost: number;
  is_enabled: boolean;
  is_paused: boolean;
}

// =============================================================================
// Audio Streaming Types
// =============================================================================

/** Word timing entry */
export interface WordTiming {
  word: string;
  start: number;
  end: number;
}

/** Extended AudioContext with webkit fallback */
export interface ExtendedWindow extends Window {
  webkitAudioContext?: typeof AudioContext;
}

// =============================================================================
// Text Animator Types (re-exported from text-animator.ts)
// =============================================================================

export type {
  AnimationStyle,
  CharState,
  TextSegment,
  WrappedLine,
  AnimationItem,
  ShowOptions,
  StreamSettings,
  CommittedSentence,
} from '../text-animator';
