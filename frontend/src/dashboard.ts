/**
 * OBS Harness Dashboard
 * Real-time monitoring and control of characters
 */

import { TextAnimator } from './text-animator';
import type { AnimationStyle } from './text-animator';
import type { Character, TextPreset, ElevenLabsModel } from './types';

// =============================================================================
// Global Window Interface Extension
// =============================================================================

// Extend Character with runtime properties
interface ExtendedCharacter extends Character {
    ws_token?: string;
    memory_enabled?: boolean;
    color?: string;
    icon?: string;
    description?: string;
}

// Global functions exposed to window for HTML onclick handlers
declare global {
    interface Window {
        openCreateCharacterModal: () => void;
        closeCharacterModal: () => void;
        editCharacter: (characterName: string) => Promise<void>;
        deleteCharacter: (characterName: string) => Promise<void>;
        openSpeakModal: (characterName: string) => void;
        closeSpeakModal: () => void;
        sendSpeak: () => Promise<void>;
        stopGeneration: (modalType: 'speak' | 'chat') => Promise<void>;
        openChatModal: (characterName: string) => Promise<void>;
        closeChatModal: () => void;
        sendChat: () => Promise<void>;
        clearChatMemory: () => Promise<void>;
        attachImage: () => void;
        handleImageSelect: (event: Event) => Promise<void>;
        captureScreen: () => Promise<void>;
        previewCharacterTextStyle: () => void;
        stopCharacterTextPreview: () => void;
        updateProviderDropdown: (model: string) => Promise<void>;
        loadVoiceModels: (voiceId: string) => Promise<void>;
        updateModelInfo: (modelId: string) => void;
        toggleTTSProvider: (provider: string) => void;
        updateCartesiaVoiceInfo: (voiceId: string) => void;
        loadCartesiaVoices: () => Promise<void>;
        selectCartesiaVoice: (voiceId: string) => void;
        onCartesiaManualIdChange: (voiceId: string) => void;
        copyCharacterUrl: (characterName: string) => Promise<void>;
        rotateCharacterToken: (characterName: string) => Promise<void>;
    }
}

// =============================================================================
// DOM Helper Functions
// =============================================================================

/** Get element by ID with type assertion */
function $(id: string): HTMLElement {
    return document.getElementById(id)!;
}

/** Get input element by ID */
function $input(id: string): HTMLInputElement {
    return document.getElementById(id) as HTMLInputElement;
}

/** Get select element by ID */
function $select(id: string): HTMLSelectElement {
    return document.getElementById(id) as HTMLSelectElement;
}

/** Get button element by ID */
function $button(id: string): HTMLButtonElement {
    return document.getElementById(id) as HTMLButtonElement;
}

/** Get textarea element by ID */
function $textarea(id: string): HTMLTextAreaElement {
    return document.getElementById(id) as HTMLTextAreaElement;
}

/** Get canvas element by ID */
function $canvas(id: string): HTMLCanvasElement {
    return document.getElementById(id) as HTMLCanvasElement;
}

/** Get form element by ID */
function $form(id: string): HTMLFormElement {
    return document.getElementById(id) as HTMLFormElement;
}

// Character status from WebSocket
interface CharacterStatus {
    name: string;
    playing?: boolean;
    streaming?: boolean;
}

// Pending image for chat
interface PendingImage {
    data: string;
    mediaType: string;
}

// ElevenLabs voice info (from /api/elevenlabs/voices/{voice_id})
interface ElevenLabsVoiceInfo {
    voice_id: string;
    name: string;
    high_quality_base_model_ids?: string[];
}

// WebSocket connection
let ws: WebSocket | null = null;
let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

// Reconnection with exponential backoff
let reconnectAttempts = 0;
const BASE_RECONNECT_DELAY = 1000;  // Start at 1 second
const MAX_RECONNECT_DELAY = 30000;  // Max 30 seconds
const MAX_RECONNECT_ATTEMPTS = 10;  // Reload page after this many failures

// Heartbeat tracking
const PING_TIMEOUT = 60000;  // 60 seconds - consider connection dead if no ping
const HEALTH_POLL_INTERVAL = 30000;  // 30 seconds - fallback health check
let lastPingTime = Date.now();
let healthPollInterval: ReturnType<typeof setInterval> | null = null;

// Server version tracking for auto-refresh on updates
let serverBuildId: string | null = null;

// State
let presets: TextPreset[] = [];
let characters: ExtendedCharacter[] = [];
let editingCharacter: Character | null = null;
let chatCharacter: Character | null = null;
let speakCharacter: Character | null = null;
let elevenlabsModels: ElevenLabsModel[] = [];  // Cached ElevenLabs models
let activeGenerationCharacter: string | null = null;  // Track which character has active generation
let activeGenerationModal: 'speak' | 'chat' | null = null;  // 'speak' or 'chat'
let sawStreamingStart = false;  // Track if we've seen streaming=true
let pendingImages: PendingImage[] = [];  // Images to attach to next chat message
let currentTenantId: string | null = null;  // Tenant ID from server (for status key matching)

// DOM elements
const wsStatus = document.getElementById('ws-status')!;
const wsStatusText = document.getElementById('ws-status-text')!;
const charactersContainer = document.getElementById('characters-container')!;
const historyList = document.getElementById('history-list')!

    // =========================================================================
    // Security Helpers
    // =========================================================================

    /**
     * Escape HTML special characters to prevent XSS.
     * Uses the browser's built-in escaping via textContent.
     */
    function escapeHtml(text: unknown): string {
        if (text == null) return '';
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }

    /**
     * Validate and sanitize a CSS color value.
     * Only allows valid hex colors, returns fallback otherwise.
     */
    function sanitizeColor(color: string | null | undefined, fallback = '#9146ff'): string {
        if (!color) return fallback;
        // Allow 3, 4, 6, or 8 character hex colors
        if (/^#[0-9a-fA-F]{3,4}$|^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$/.test(color)) {
            return color;
        }
        return fallback;
    }

    /**
     * Get tenant_id from server (sent in WebSocket hello message).
     * Used to construct full channel keys for status matching.
     */
    function getTenantId() {
        return currentTenantId;
    }

    // =========================================================================
    // WebSocket Connection
    // =========================================================================

    function connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            wsStatus.classList.add('connected');
            wsStatusText.textContent = 'Connected';
            reconnectAttempts = 0;  // Reset backoff on successful connection
            lastPingTime = Date.now();  // Reset ping timer
            stopHealthPoll();  // Stop fallback polling
            if (reconnectTimeout) {
                clearTimeout(reconnectTimeout);
                reconnectTimeout = null;
            }
        };

        ws.onclose = () => {
            wsStatus.classList.remove('connected');
            wsStatusText.textContent = 'Disconnected';
            startHealthPoll();  // Start fallback health polling
            scheduleReconnect();
        };

        ws.onerror = (error) => {
            console.error('Dashboard WebSocket error:', error);
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                handleMessage(msg);
            } catch (e) {
                console.error('Error parsing message:', e);
            }
        };
    }

    function scheduleReconnect() {
        if (!reconnectTimeout) {
            // After too many failures, reload the page entirely
            if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
                console.log(`[dashboard] Max reconnect attempts (${MAX_RECONNECT_ATTEMPTS}) reached, reloading page...`);
                location.reload();
                return;
            }

            // Exponential backoff: 1s, 2s, 4s, 8s, ... up to 30s max
            const delay = Math.min(
                BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempts),
                MAX_RECONNECT_DELAY
            );
            reconnectAttempts++;

            console.log(`[dashboard] Reconnecting in ${delay}ms (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
            reconnectTimeout = setTimeout(() => {
                reconnectTimeout = null;
                connect();
            }, delay);
        }
    }

    // =========================================================================
    // Health Poll Fallback
    // =========================================================================

    function startHealthPoll() {
        if (healthPollInterval) return;
        healthPollInterval = setInterval(async () => {
            // Skip if WebSocket is connected
            if (ws && ws.readyState === WebSocket.OPEN) return;

            try {
                const res = await fetch('/health', { signal: AbortSignal.timeout(5000) });
                if (res.ok && reconnectAttempts >= MAX_RECONNECT_ATTEMPTS / 2) {
                    // Server is healthy but WebSocket keeps failing - reload
                    console.log('[dashboard] Server healthy but WebSocket failing, reloading page...');
                    location.reload();
                }
            } catch (e) {
                // Server unreachable, reconnect logic will handle it
            }
        }, HEALTH_POLL_INTERVAL);
    }

    function stopHealthPoll() {
        if (healthPollInterval) {
            clearInterval(healthPollInterval);
            healthPollInterval = null;
        }
    }

    // Ping timeout check (dashboard has no animation loop, so use interval)
    setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN && Date.now() - lastPingTime > PING_TIMEOUT) {
            console.log(`[dashboard] No ping received in ${PING_TIMEOUT}ms, connection stale - reconnecting...`);
            lastPingTime = Date.now();  // Reset to prevent spam
            ws.close();  // Will trigger reconnect via onclose
        }
    }, 10000);  // Check every 10 seconds

    function handleMessage(msg) {
        // Handle ping (heartbeat)
        if (msg.type === 'ping') {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ event: 'pong', ts: msg.ts }));
            }
            lastPingTime = Date.now();
            return;
        }

        // Handle version check (auto-refresh on server update)
        if (msg.type === 'hello') {
            const newBuildId = msg.build_id;

            // Store tenant_id for status key matching
            if (msg.tenant_id) {
                currentTenantId = msg.tenant_id;
                console.log(`[dashboard] Tenant ID: ${currentTenantId}`);
            }

            if (serverBuildId === null) {
                // First connection - store the build ID
                serverBuildId = newBuildId;
                console.log(`[dashboard] Server build ID: ${serverBuildId}`);
            } else if (serverBuildId !== newBuildId) {
                // Server restarted with new version - refresh to get new JS/CSS
                console.log(`[dashboard] Server version changed (${serverBuildId} -> ${newBuildId}), refreshing page...`);
                location.reload();
                return;
            } else {
                console.log(`[dashboard] Reconnected to same server version`);
            }
            return;
        }

        if (msg.type === 'characters') {
            // Merge connection status into character list
            // Status uses full "tenant_id:name" keys, so we construct full keys for lookup
            const tenantId = getTenantId();
            const statusMap = new Map<string, CharacterStatus>(msg.characters.map((c: CharacterStatus) => [c.name, c]));
            characters = characters.map(ch => {
                const fullKey = `${tenantId}:${ch.name}`;
                return {
                    ...ch,
                    connected: statusMap.has(fullKey),
                    playing: statusMap.get(fullKey)?.playing || false,
                    streaming: statusMap.get(fullKey)?.streaming || false,
                };
            });
            renderCharacters();

            // Check if active generation's streaming has ended
            if (activeGenerationCharacter && activeGenerationModal) {
                const fullKey = `${tenantId}:${activeGenerationCharacter}`;
                const charStatus = statusMap.get(fullKey);
                if (charStatus) {
                    // Track when streaming starts
                    if (charStatus.streaming) {
                        sawStreamingStart = true;
                    }
                    // Only hide button when streaming transitions from true to false
                    if (sawStreamingStart && !charStatus.streaming) {
                        // Streaming ended - hide stop button and update status
                        const stopBtn = document.getElementById(`${activeGenerationModal}-stop-btn`);
                        const statusText = document.getElementById(`${activeGenerationModal}-status-text`);
                        if (stopBtn) stopBtn.style.display = 'none';
                        if (statusText) statusText.textContent = 'Complete!';
                        activeGenerationCharacter = null;
                        activeGenerationModal = null;
                        sawStreamingStart = false;
                    }
                }
            }
        } else if (msg.type === 'character_sync') {
            // Full character data sync from another client's changes
            // Replace the entire character list with fresh data
            characters = msg.characters;
            renderCharacters();

            // Show a subtle notification that data was synced (optional)
            // Only show if we didn't just make the change ourselves
            if (!recentLocalUpdate) {
                console.log('Character data synced from server');
            }
            recentLocalUpdate = false;
        }
    }

    // Track if we recently made a local update (to avoid showing sync notification)
    let recentLocalUpdate = false;

    // =========================================================================
    // Toast Notifications
    // =========================================================================

    function showToast(message, type = 'info', duration = 4000) {
        // Remove existing toast if any
        const existingToast = document.querySelector('.toast-notification');
        if (existingToast) {
            existingToast.remove();
        }

        const toast = document.createElement('div');
        toast.className = `toast-notification toast-${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('hiding');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    // =========================================================================
    // API Calls
    // =========================================================================

    async function apiCall(endpoint: string, method = 'GET', body: unknown = null, showErrors = true): Promise<unknown> {
        const options: RequestInit = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body) {
            options.body = JSON.stringify(body);
        }

        try {
            const response = await fetch(endpoint, options);
            const data = await response.json();

            if (!response.ok) {
                const errorMsg = data.detail || data.error || `HTTP ${response.status}`;
                if (showErrors) {
                    showToast(`API Error: ${errorMsg}`, 'error');
                }
                console.error(`API Error [${method} ${endpoint}]:`, errorMsg);
                return { error: errorMsg, status: response.status };
            }

            return data;
        } catch (error) {
            const errorMsg = (error as Error).message || 'Network error';
            if (showErrors) {
                showToast(`Connection Error: ${errorMsg}`, 'error');
            }
            console.error(`Fetch Error [${method} ${endpoint}]:`, error);
            return { error: errorMsg, networkError: true };
        }
    }

    async function loadPresets() {
        const result = await apiCall('/api/presets');
        if (Array.isArray(result)) {
            presets = result;
        }
        return presets;
    }

    async function loadHistory() {
        const result = await apiCall('/api/history');
        if (Array.isArray(result)) {
            renderHistory(result);
        }
    }

    // Character CRUD
    async function getAllCharacters() {
        const result = await apiCall('/api/characters');
        if (Array.isArray(result)) {
            characters = result;
            renderCharacters();
        }
        return characters;
    }

    async function createCharacter(data) {
        recentLocalUpdate = true;
        const result = await apiCall('/api/characters', 'POST', data);
        await getAllCharacters();  // Update local UI immediately
        return result;
    }

    async function updateCharacter(name, data, showErrors = true) {
        recentLocalUpdate = true;
        const result = await apiCall(`/api/characters/${name}`, 'PUT', data, showErrors);
        await getAllCharacters();  // Update local UI immediately
        return result;
    }

    async function deleteCharacterAPI(name: string): Promise<void> {
        if (!confirm(`Delete character "${name}"? This cannot be undone.`)) {
            return;
        }
        recentLocalUpdate = true;
        await apiCall(`/api/characters/${name}`, 'DELETE');
        await getAllCharacters();  // Update local UI immediately
    }

    // Provider dropdown
    async function updateProviderDropdown(model: string) {
        const select = document.getElementById('character-provider') as HTMLSelectElement | null;
        if (!select) return;

        // Reset to default while loading
        select.innerHTML = '<option value="">Loading providers...</option>';
        select.disabled = true;

        if (!model || model.trim() === '') {
            select.innerHTML = '<option value="">Default (auto)</option>';
            select.disabled = false;
            return;
        }

        try {
            const result = await apiCall(`/api/openrouter/models/${encodeURIComponent(model)}/providers`, 'GET', null, false) as { providers?: string[] };
            select.innerHTML = '<option value="">Default (auto)</option>';

            if (result.providers && result.providers.length > 0) {
                for (const provider of result.providers) {
                    const option = document.createElement('option');
                    option.value = provider;
                    option.textContent = provider;
                    select.appendChild(option);
                }
            }
        } catch (e) {
            console.error('Error fetching providers:', e);
            select.innerHTML = '<option value="">Default (auto)</option>';
        } finally {
            select.disabled = false;
        }
    }

    // ElevenLabs Models
    async function loadElevenLabsModels() {
        const select = document.getElementById('character-tts-model');
        if (!select) return;

        try {
            const models = await apiCall('/api/elevenlabs/models', 'GET', null, false);
            if (Array.isArray(models)) {
                elevenlabsModels = models;
                // Populate dropdown with all models
                select.innerHTML = models.map(m => {
                    const label = m.name || m.model_id;
                    return `<option value="${m.model_id}">${label}</option>`;
                }).join('');
            }
        } catch (e) {
            console.error('Error fetching ElevenLabs models:', e);
            // Keep default options if API fails
        }
    }

    async function loadVoiceModels(voiceId: string) {
        const select = $select('character-tts-model');
        const infoEl = document.getElementById('tts-model-info');
        if (!select || !voiceId) return;

        // Clear info
        if (infoEl) infoEl.textContent = '';

        try {
            const voice = await apiCall(`/api/elevenlabs/voices/${voiceId}`, 'GET', null, false) as ElevenLabsVoiceInfo | null;
            if (voice?.high_quality_base_model_ids && voice.high_quality_base_model_ids.length > 0) {
                // Highlight compatible models
                const compatibleIds = new Set(voice.high_quality_base_model_ids);
                Array.from(select.options).forEach((option: HTMLOptionElement) => {
                    if (compatibleIds.has(option.value)) {
                        // Mark as recommended
                        const model = elevenlabsModels.find(m => m.model_id === option.value);
                        option.textContent = `${model?.name || option.value} (Recommended)`;
                    } else {
                        // Restore original name
                        const model = elevenlabsModels.find(m => m.model_id === option.value);
                        option.textContent = model?.name || option.value;
                    }
                });

                if (infoEl) {
                    infoEl.textContent = `Voice "${voice.name}" is optimized for: ${voice.high_quality_base_model_ids.join(', ')}`;
                }
            }
        } catch (e) {
            console.error('Error fetching voice info:', e);
            if (infoEl) infoEl.textContent = 'Could not fetch voice info';
        }
    }

    // Model descriptions from ElevenLabs docs
    const modelDescriptions: Record<string, string> = {
        'eleven_v3': 'Latest flagship model with emotionally rich, expressive speech. 70+ languages. Best for audiobooks & dramatic content. Not optimized for real-time.',
        'eleven_multilingual_v2': 'Advanced emotionally-aware synthesis. 29 languages. Most stable for long-form. Higher latency but best quality.',
        'eleven_flash_v2_5': 'Fastest model (~75ms latency). 32 languages. 50% lower cost. Best for real-time agents & bulk processing.',
        'eleven_turbo_v2_5': 'Balanced quality & speed (~250ms). 32 languages. Good middle-ground between Flash and Multilingual.',
        'eleven_flash_v2': 'Ultra-fast for real-time (~75ms). English only. Great for conversational agents.',
        'eleven_turbo_v2': 'Quality-focused with low latency (~250ms). English only. Good balance for English projects.',
        'eleven_multilingual_v1': 'Legacy multilingual model. Use v2 for better results.',
        'eleven_monolingual_v1': 'Legacy English model. Use newer models for better quality.',
    };

    function updateModelInfo(modelId: string) {
        const infoEl = document.getElementById('tts-model-info');
        const styleRow = document.getElementById('voice-style-row');
        const similarityRow = document.getElementById('voice-similarity-row');

        const model = elevenlabsModels.find(m => m.model_id === modelId);

        if (model) {
            // Show/hide style slider based on model capability
            if (styleRow) {
                styleRow.style.display = model.can_use_style ? '' : 'none';
            }

            // Show/hide similarity boost slider based on model capability
            if (similarityRow) {
                similarityRow.style.display = model.can_use_speaker_boost ? '' : 'none';
            }

            // Update info text with description
            if (infoEl) {
                infoEl.textContent = modelDescriptions[modelId] || '';
            }
        }
    }

    // =========================================================================
    // Cartesia TTS Functions
    // =========================================================================

    interface CartesiaVoice {
        voice_id: string;
        name: string;
        language: string;
        description?: string;
    }

    let cartesiaVoices: CartesiaVoice[] = [];

    async function loadCartesiaVoices() {
        try {
            cartesiaVoices = await apiCall('/api/cartesia/voices', 'GET', null, false) as CartesiaVoice[];
            const select = document.getElementById('cartesia-voice-select') as HTMLSelectElement | null;
            if (!select) return;

            select.innerHTML = '<option value="">-- Select a voice --</option>';
            cartesiaVoices.forEach(voice => {
                const option = document.createElement('option');
                option.value = voice.voice_id;
                option.textContent = `${voice.name} (${voice.language})`;
                select.appendChild(option);
            });
        } catch (e) {
            console.error('Error loading Cartesia voices:', e);
            const select = document.getElementById('cartesia-voice-select') as HTMLSelectElement | null;
            if (select) {
                select.innerHTML = '<option value="">Failed to load voices</option>';
            }
        }
    }

    function selectCartesiaVoice(voiceId: string) {
        // When a voice is selected from dropdown, update the manual ID field
        const manualInput = document.getElementById('cartesia-voice-id') as HTMLInputElement | null;
        if (manualInput && voiceId) {
            manualInput.value = voiceId;
        }
        updateCartesiaVoiceInfo(voiceId);
    }

    function onCartesiaManualIdChange(voiceId: string) {
        // When manual ID is entered, try to find and select in dropdown
        const select = document.getElementById('cartesia-voice-select') as HTMLSelectElement | null;
        if (select && voiceId) {
            // Check if this ID exists in the dropdown
            const option = Array.from(select.options).find((o: HTMLOptionElement) => o.value === voiceId);
            if (option) {
                select.value = voiceId;
                updateCartesiaVoiceInfo(voiceId);
            } else {
                // Custom ID - clear dropdown selection
                select.value = '';
                const infoEl = document.getElementById('cartesia-voice-info');
                if (infoEl) infoEl.textContent = 'Custom voice ID';
            }
        }
    }

    function updateCartesiaVoiceInfo(voiceId) {
        const infoEl = document.getElementById('cartesia-voice-info');
        if (!infoEl) return;

        if (!voiceId) {
            infoEl.textContent = '';
            return;
        }

        const voice = cartesiaVoices.find(v => v.voice_id === voiceId);
        if (voice && voice.description) {
            infoEl.textContent = voice.description;
        } else {
            infoEl.textContent = '';
        }
    }

    function toggleTTSProvider(provider) {
        const elevenlabsSettings = document.getElementById('elevenlabs-settings');
        const cartesiaSettings = document.getElementById('cartesia-settings');

        if (provider === 'cartesia') {
            elevenlabsSettings.style.display = 'none';
            cartesiaSettings.style.display = 'block';
            // Load voices on first switch
            if (cartesiaVoices.length === 0) {
                loadCartesiaVoices();
            }
        } else {
            elevenlabsSettings.style.display = 'block';
            cartesiaSettings.style.display = 'none';
        }
    }

    // Character actions
    async function sendCharacterSpeak(characterName: string, text: string, showText: boolean) {
        return apiCall(`/api/characters/${characterName}/speak`, 'POST', {
            text,
            show_text: showText,
        });
    }

    interface ChatRequestBody {
        message: string;
        show_text: boolean;
        twitch_chat_seconds?: number;
        images?: Array<{ data: string; media_type: string }>;
    }

    async function sendCharacterChat(characterName: string, message: string, showText: boolean, twitchChatSeconds: string | null = null, images: PendingImage[] | null = null) {
        const body: ChatRequestBody = {
            message,
            show_text: showText,
        };
        if (twitchChatSeconds !== null && twitchChatSeconds !== '') {
            body.twitch_chat_seconds = parseInt(twitchChatSeconds);
        }
        if (images && images.length > 0) {
            body.images = images.map(img => ({
                data: img.data,
                media_type: img.mediaType
            }));
        }
        return apiCall(`/api/characters/${characterName}/chat`, 'POST', body);
    }

    async function getCharacterMemory(characterName: string) {
        return apiCall(`/api/characters/${characterName}/memory`);
    }

    async function clearCharacterMemory(characterName: string) {
        return apiCall(`/api/characters/${characterName}/memory`, 'DELETE');
    }

    function renderChatHistory(messages, characterName) {
        const historyDiv = document.getElementById('chat-history');
        const emptyDiv = document.getElementById('chat-history-empty');

        if (!messages || messages.length === 0) {
            emptyDiv.style.display = 'block';
            // Clear any existing bubbles
            historyDiv.querySelectorAll('.chat-bubble').forEach(el => el.remove());
            return;
        }

        emptyDiv.style.display = 'none';
        // Clear existing bubbles
        historyDiv.querySelectorAll('.chat-bubble').forEach(el => el.remove());

        messages.forEach(msg => {
            if (msg.role === 'context') {
                // Render context as a trimmed snippet
                const lines = msg.content.split('\n');
                const trimmed = lines.slice(-4).map(l => l.length > 60 ? l.substring(0, 57) + '...' : l).join(' | ');
                const bubble = document.createElement('div');
                bubble.className = 'chat-bubble context';
                const contentDiv = document.createElement('div');
                contentDiv.className = 'chat-bubble-content';
                contentDiv.textContent = `📺 Twitch (${lines.length}): ${trimmed}`;
                bubble.appendChild(contentDiv);
                historyDiv.appendChild(bubble);
            } else {
                const bubble = document.createElement('div');
                bubble.className = `chat-bubble ${msg.role}`;

                const label = document.createElement('div');
                label.className = 'chat-bubble-label';
                label.textContent = msg.role === 'user' ? 'You' : characterName;

                const content = document.createElement('div');
                content.className = 'chat-bubble-content';

                // Handle interrupted messages - show spoken text normally, cut-off in strikethrough
                if (msg.interrupted && msg.generated_text) {
                    const spokenText = msg.content || '';
                    const generatedText = msg.generated_text || '';

                    // Show what was actually spoken
                    if (spokenText) {
                        const spokenSpan = document.createElement('span');
                        spokenSpan.textContent = spokenText;
                        content.appendChild(spokenSpan);
                    }

                    // Show what was cut off in strikethrough
                    // Try to find the cut-off portion by removing the spoken prefix
                    let cutOffText = '';
                    if (generatedText.startsWith(spokenText)) {
                        cutOffText = generatedText.substring(spokenText.length).trim();
                    } else if (generatedText.length > spokenText.length) {
                        // Fallback: just show the extra characters
                        cutOffText = generatedText.substring(spokenText.length).trim();
                    }

                    if (cutOffText) {
                        const cutOffSpan = document.createElement('span');
                        cutOffSpan.style.textDecoration = 'line-through';
                        cutOffSpan.style.opacity = '0.6';
                        cutOffSpan.textContent = ' ' + cutOffText;
                        content.appendChild(cutOffSpan);
                    }

                    // Add interrupted indicator
                    const interruptedBadge = document.createElement('span');
                    interruptedBadge.style.cssText = 'display: inline-block; margin-left: 8px; padding: 2px 6px; background: #ff6b6b33; color: #ff6b6b; border-radius: 4px; font-size: 0.7rem;';
                    interruptedBadge.textContent = '⚡ interrupted';
                    content.appendChild(interruptedBadge);
                } else {
                    content.textContent = msg.content;
                }

                bubble.appendChild(label);
                bubble.appendChild(content);
                historyDiv.appendChild(bubble);
            }
        });

        // Scroll to bottom
        historyDiv.scrollTop = historyDiv.scrollHeight;
    }

    function addChatBubble(role, content, characterName) {
        const historyDiv = document.getElementById('chat-history');
        const emptyDiv = document.getElementById('chat-history-empty');
        emptyDiv.style.display = 'none';

        const bubble = document.createElement('div');
        bubble.className = `chat-bubble ${role}`;

        const label = document.createElement('div');
        label.className = 'chat-bubble-label';
        label.textContent = role === 'user' ? 'You' : characterName;

        const contentDiv = document.createElement('div');
        contentDiv.className = 'chat-bubble-content';
        contentDiv.textContent = content;

        bubble.appendChild(label);
        bubble.appendChild(contentDiv);
        historyDiv.appendChild(bubble);

        // Scroll to bottom
        historyDiv.scrollTop = historyDiv.scrollHeight;
    }

    function addContextBubble(text) {
        const historyDiv = document.getElementById('chat-history');
        const emptyDiv = document.getElementById('chat-history-empty');
        emptyDiv.style.display = 'none';

        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble context';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'chat-bubble-content';
        contentDiv.textContent = text;

        bubble.appendChild(contentDiv);
        historyDiv.appendChild(bubble);

        // Scroll to bottom
        historyDiv.scrollTop = historyDiv.scrollHeight;
    }

    // =========================================================================
    // Character Text Style Preview
    // =========================================================================

    let characterPreviewAnimator: TextAnimator | null = null;
    let characterPreviewAnimationFrame: number | null = null;

    function previewCharacterTextStyle() {
        stopCharacterTextPreview();

        const canvas = $canvas('character-preview-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d')!;

        characterPreviewAnimator = new TextAnimator(ctx, canvas.width, canvas.height);
        const animator = characterPreviewAnimator; // Non-null reference for closure

        const config = {
            style: $input('character-text-style').value as AnimationStyle,
            fontFamily: $input('character-font-family').value,
            fontSize: parseInt($input('character-font-size').value),
            duration: parseInt($input('character-text-duration').value),
            color: $input('character-text-color').value,
            strokeColor: $input('character-stroke-color').value,
            strokeWidth: parseInt($input('character-stroke-width').value),
            positionX: parseInt($input('character-position-x').value) / 100,
            positionY: parseInt($input('character-position-y').value) / 100,
        };

        const scaleFactor = canvas.width / 800;

        animator.show({
            text: 'Sample Text',
            style: config.style,
            duration: config.duration,
            x: config.positionX,
            y: config.positionY,
            fontFamily: config.fontFamily,
            fontSize: Math.round(config.fontSize * scaleFactor),
            color: config.color,
            strokeColor: config.strokeWidth > 0 ? config.strokeColor : null,
            strokeWidth: Math.round(config.strokeWidth * scaleFactor),
        });

        function animate() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            animator.update();
            animator.draw();

            if (animator.isAnimating()) {
                characterPreviewAnimationFrame = requestAnimationFrame(animate);
            }
        }

        animate();
    }

    function stopCharacterTextPreview() {
        if (characterPreviewAnimationFrame) {
            cancelAnimationFrame(characterPreviewAnimationFrame);
            characterPreviewAnimationFrame = null;
        }
        if (characterPreviewAnimator) {
            characterPreviewAnimator.clear();
        }
        const canvas = $canvas('character-preview-canvas');
        if (canvas) {
            const ctx = canvas.getContext('2d');
            ctx?.clearRect(0, 0, canvas.width, canvas.height);
        }
    }

    // =========================================================================
    // Character Modal Functions
    // =========================================================================

    const characterModal = $('character-modal');
    const characterForm = $form('character-form');
    const characterModalTitle = $('character-modal-title');

    function openCreateCharacterModal() {
        editingCharacter = null;
        characterModalTitle.textContent = 'Create Character';
        characterForm.reset();
        $input('character-name').disabled = false;

        // Set defaults
        $input('character-color').value = '#e94560';
        $input('character-icon').value = '\uD83D\uDD0A';
        $input('character-stability').value = '50';
        $('character-stability-value').textContent = '0.50';
        $input('character-similarity').value = '75';
        $('character-similarity-value').textContent = '0.75';
        $input('character-voice-style').value = '0';
        $('character-style-value').textContent = '0.00';
        $input('character-voice-speed').value = '100';
        $('character-speed-value').textContent = '1.0';
        $input('character-volume').value = '100';
        $('character-volume-value').textContent = '100';
        $select('character-text-style').value = 'typewriter';
        $input('character-font-family').value = 'Arial';
        $input('character-font-size').value = '48';
        $input('character-text-duration').value = '3000';
        $input('character-text-color').value = '#ffffff';
        $input('character-stroke-color').value = '#000000';
        $input('character-stroke-width').value = '0';
        $('character-stroke-width-value').textContent = '0';
        $input('character-position-x').value = '50';
        $('character-pos-x-value').textContent = '50';
        $input('character-position-y').value = '50';
        $('character-pos-y-value').textContent = '50';
        $input('character-model').value = 'anthropic/claude-sonnet-4.5';
        $select('character-provider').innerHTML = '<option value="">Default (auto)</option>';
        $select('character-provider').value = '';
        $input('character-temperature').value = '70';
        $('character-temp-value').textContent = '0.7';
        $input('character-max-tokens').value = '1024';

        // TTS model default
        $select('character-tts-model').value = 'eleven_multilingual_v2';
        $('tts-model-info').textContent = '';
        updateModelInfo('eleven_multilingual_v2');

        // Memory & Twitch settings
        $input('character-memory-enabled').checked = false;
        $input('character-persist-memory').checked = false;
        $input('character-twitch-chat-enabled').checked = false;
        $input('character-twitch-chat-seconds').value = '60';
        $input('character-twitch-chat-max').value = '20';

        characterModal.classList.add('active');
    }

    function openEditCharacterModal(character: Character) {
        editingCharacter = character;
        characterModalTitle.textContent = 'Edit Character';

        // Basic info
        // Cast character to record for accessing extended properties
        const charData = character as unknown as Record<string, unknown>;

        $input('character-name').value = character.name;
        $input('character-name').disabled = true;
        $textarea('character-description').value = (charData.description as string) || '';
        $input('character-color').value = charData.color as string;
        $input('character-icon').value = charData.icon as string;

        // TTS Provider settings
        const ttsProvider = character.tts_provider || 'elevenlabs';
        $select('character-tts-provider').value = ttsProvider;
        toggleTTSProvider(ttsProvider);

        if (ttsProvider === 'cartesia' && character.tts_settings) {
            // Cartesia settings - need to load voices first, then select
            loadCartesiaVoices().then(() => {
                const settings = character.tts_settings as unknown as Record<string, unknown>;
                const voiceId = (settings.voice_id as string) || '';
                // Set the manual voice ID field
                $input('cartesia-voice-id').value = voiceId;
                // Try to select in dropdown if it exists
                const select = $select('cartesia-voice-select');
                if (select && voiceId) {
                    const option = Array.from(select.options).find(o => o.value === voiceId);
                    if (option) {
                        select.value = voiceId;
                    }
                }
                $input('cartesia-model-id').value = (settings.model_id as string) || 'sonic-2024-12-12';
                $select('cartesia-language').value = (settings.language as string) || 'en';
                // Clamp speed to valid Cartesia range (0.6-1.5)
                const rawSpeed = (settings.speed as number) || 1.0;
                const speed = Math.max(0.6, Math.min(1.5, rawSpeed));
                $input('cartesia-speed').value = String(Math.round(speed * 100));
                $('cartesia-speed-value').textContent = speed.toFixed(1);
                if (rawSpeed !== speed) {
                    console.warn(`Cartesia speed ${rawSpeed} was clamped to ${speed} (valid: 0.6-1.5)`);
                }
                updateCartesiaVoiceInfo(voiceId);
            });
        } else {
            // ElevenLabs settings (legacy or from tts_settings)
            const settings = (character.tts_settings || {}) as unknown as Record<string, unknown>;
            $input('character-voice-id').value = (settings.voice_id as string) || (charData.elevenlabs_voice_id as string);
            const modelId = (settings.model_id as string) || (charData.elevenlabs_model_id as string) || 'eleven_multilingual_v2';
            $select('character-tts-model').value = modelId;
            updateModelInfo(modelId);
            loadVoiceModels((settings.voice_id as string) || (charData.elevenlabs_voice_id as string));

            const stability = (settings.stability as number) ?? (charData.voice_stability as number);
            $input('character-stability').value = String(Math.round(stability * 100));
            $('character-stability-value').textContent = stability.toFixed(2);

            const similarity = (settings.similarity_boost as number) ?? (charData.voice_similarity_boost as number);
            $input('character-similarity').value = String(Math.round(similarity * 100));
            $('character-similarity-value').textContent = similarity.toFixed(2);

            const style = (settings.style as number) ?? (charData.voice_style as number);
            $input('character-voice-style').value = String(Math.round(style * 100));
            $('character-style-value').textContent = style.toFixed(2);

            const speed = (settings.speed as number) ?? (charData.voice_speed as number);
            $input('character-voice-speed').value = String(Math.round(speed * 100));
            $('character-speed-value').textContent = speed.toFixed(1);
        }

        // Audio settings
        $input('character-volume').value = String(Math.round((charData.default_volume as number) * 100));
        $('character-volume-value').textContent = String(Math.round((charData.default_volume as number) * 100));
        $input('character-muted').checked = charData.mute_state as boolean;

        // Text style settings
        $select('character-text-style').value = charData.default_text_style as string;
        $input('character-font-family').value = character.text_font_family || 'Arial';
        $input('character-font-size').value = String(character.text_font_size || 48);
        $input('character-text-duration').value = String(charData.text_duration as number);
        $input('character-text-color').value = character.text_color || '#ffffff';
        $input('character-stroke-color').value = character.text_stroke_color || '#000000';
        $input('character-stroke-width').value = String(character.text_stroke_width || 0);
        $('character-stroke-width-value').textContent = String(character.text_stroke_width || 0);
        $input('character-position-x').value = String(Math.round((character.text_position_x || 0.5) * 100));
        $('character-pos-x-value').textContent = String(Math.round((character.text_position_x || 0.5) * 100));
        $input('character-position-y').value = String(Math.round((character.text_position_y || 0.5) * 100));
        $('character-pos-y-value').textContent = String(Math.round((character.text_position_y || 0.5) * 100));

        // AI settings
        $textarea('character-prompt').value = character.system_prompt || '';
        $input('character-model').value = character.openrouter_model || '';
        // Fetch providers for this model and set current value
        updateProviderDropdown(character.openrouter_model || '').then(() => {
            $select('character-provider').value = (charData.provider as string) || '';
        });
        $input('character-temperature').value = String(Math.round((charData.temperature as number) * 100));
        $('character-temp-value').textContent = (charData.temperature as number).toFixed(1);
        $input('character-max-tokens').value = String(charData.max_tokens as number);

        // Memory & Twitch settings
        $input('character-memory-enabled').checked = (charData.memory_enabled as boolean) || false;
        $input('character-persist-memory').checked = character.persist_memory || false;
        $input('character-twitch-chat-enabled').checked = (charData.twitch_chat_enabled as boolean) || false;
        $input('character-twitch-chat-seconds').value = String((charData.twitch_chat_window_seconds as number) || 60);
        $input('character-twitch-chat-max').value = String((charData.twitch_chat_max_messages as number) || 20);

        characterModal.classList.add('active');
    }

    function closeCharacterModal() {
        characterModal.classList.remove('active');
        editingCharacter = null;
        stopCharacterTextPreview();
    }

    async function handleCharacterFormSubmit(e: Event) {
        e.preventDefault();

        const ttsProvider = $select('character-tts-provider').value;

        // Build TTS settings based on provider
        let ttsSettings: Record<string, unknown> | null = null;
        if (ttsProvider === 'cartesia') {
            ttsSettings = {
                voice_id: $input('cartesia-voice-id').value,
                model_id: $input('cartesia-model-id').value,
                language: $select('cartesia-language').value,
                speed: parseInt($input('cartesia-speed').value) / 100,
            };
        } else {
            // ElevenLabs - store in tts_settings for new abstraction
            ttsSettings = {
                voice_id: $input('character-voice-id').value,
                model_id: $select('character-tts-model').value,
                stability: parseInt($input('character-stability').value) / 100,
                similarity_boost: parseInt($input('character-similarity').value) / 100,
                style: parseInt($input('character-voice-style').value) / 100,
                speed: parseInt($input('character-voice-speed').value) / 100,
            };
        }

        const data = {
            name: $input('character-name').value,
            description: $textarea('character-description').value || null,
            color: $input('character-color').value,
            icon: $input('character-icon').value,
            // TTS provider abstraction
            tts_provider: ttsProvider,
            tts_settings: ttsSettings,
            // Legacy ElevenLabs fields (for backwards compatibility)
            elevenlabs_voice_id: $input('character-voice-id').value,
            elevenlabs_model_id: $select('character-tts-model').value,
            voice_stability: parseInt($input('character-stability').value) / 100,
            voice_similarity_boost: parseInt($input('character-similarity').value) / 100,
            voice_style: parseInt($input('character-voice-style').value) / 100,
            voice_speed: parseInt($input('character-voice-speed').value) / 100,
            default_volume: parseInt($input('character-volume').value) / 100,
            mute_state: $input('character-muted').checked,
            default_text_style: $select('character-text-style').value,
            text_font_family: $input('character-font-family').value,
            text_font_size: parseInt($input('character-font-size').value),
            text_duration: parseInt($input('character-text-duration').value),
            text_color: $input('character-text-color').value,
            text_stroke_color: parseInt($input('character-stroke-width').value) > 0
                ? $input('character-stroke-color').value : null,
            text_stroke_width: parseInt($input('character-stroke-width').value),
            text_position_x: parseInt($input('character-position-x').value) / 100,
            text_position_y: parseInt($input('character-position-y').value) / 100,
            system_prompt: $textarea('character-prompt').value || null,
            model: $input('character-model').value,
            provider: $select('character-provider').value || null,
            temperature: parseInt($input('character-temperature').value) / 100,
            max_tokens: parseInt($input('character-max-tokens').value),
            memory_enabled: $input('character-memory-enabled').checked,
            persist_memory: $input('character-persist-memory').checked,
            twitch_chat_enabled: $input('character-twitch-chat-enabled').checked,
            twitch_chat_window_seconds: parseInt($input('character-twitch-chat-seconds').value),
            twitch_chat_max_messages: parseInt($input('character-twitch-chat-max').value),
            // Optimistic concurrency control - send timestamp to detect conflicts
            expected_updated_at: editingCharacter?.updated_at || null,
        };

        try {
            if (editingCharacter) {
                const result = await updateCharacter(editingCharacter.name, data, false) as { status?: number } | null;
                // Handle 409 conflict - character was modified by another client
                if (result && result.status === 409) {
                    // Fetch fresh data and refresh the modal
                    const freshCharacter = await apiCall(`/api/characters/${encodeURIComponent(editingCharacter.name)}`, 'GET', null, false) as Character | { error: string } | null;
                    if (freshCharacter && !('error' in freshCharacter)) {
                        openEditCharacterModal(freshCharacter);
                        showToast('Someone else modified this character. Please review the updated values and try again.', 'warning');
                    } else {
                        closeCharacterModal();
                        showToast('Character was modified. Please try again.', 'warning');
                    }
                    return;
                }
            } else {
                await createCharacter(data);
            }
            closeCharacterModal();
        } catch (error) {
            console.error('Error saving character:', error);
            alert('Error saving character. Check console for details.');
        }
    }

    // =========================================================================
    // Speak Modal Functions
    // =========================================================================

    const speakModal = $('speak-modal');

    function openSpeakModal(characterName: string) {
        const character = characters.find(c => c.name === characterName);
        if (!character) return;

        speakCharacter = character;
        $('speak-modal-title').textContent = `Speak as ${character.name}`;
        $textarea('speak-text').value = '';
        $input('speak-show-text').checked = true;
        $('speak-status').style.display = 'none';
        $button('speak-send-btn').disabled = false;

        speakModal.classList.add('active');
    }

    function closeSpeakModal() {
        speakModal.classList.remove('active');
        speakCharacter = null;
    }

    async function sendSpeak() {
        if (!speakCharacter) return;

        const text = $textarea('speak-text').value.trim();
        const showText = $input('speak-show-text').checked;

        if (!text) {
            alert('Please enter text to speak');
            return;
        }

        const statusDiv = $('speak-status');
        const statusText = $('speak-status-text');
        const sendBtn = $button('speak-send-btn');
        const stopBtn = $button('speak-stop-btn');

        statusDiv.style.display = 'block';
        statusText.textContent = 'Speaking...';
        sendBtn.disabled = true;
        stopBtn.style.display = 'inline-block';

        // Track active generation so we can hide stop button when streaming ends
        activeGenerationCharacter = speakCharacter.name;
        activeGenerationModal = 'speak';
        sawStreamingStart = false;

        try {
            const result = await sendCharacterSpeak(speakCharacter.name, text, showText) as { error?: string; detail?: string };
            if (result.error || result.detail) {
                statusText.textContent = `Error: ${result.error || result.detail}`;
                // Error - hide stop button immediately
                stopBtn.style.display = 'none';
                activeGenerationCharacter = null;
                activeGenerationModal = null;
            } else {
                statusText.textContent = 'Playing audio...';
                $textarea('speak-text').value = '';
                loadHistory();
                // Stop button will be hidden by handleMessage when streaming ends
            }
        } catch (error) {
            console.error('Speak error:', error);
            statusText.textContent = `Error: ${(error as Error).message || 'Unknown error'}`;
            // Error - hide stop button immediately
            stopBtn.style.display = 'none';
            activeGenerationCharacter = null;
            activeGenerationModal = null;
        } finally {
            sendBtn.disabled = false;
        }
    }

    interface StopResult {
        was_active?: boolean;
    }

    interface MemoryInfo {
        message_count: number;
        messages: Array<{ role: string; content: string }>;
    }

    async function stopGeneration(modalType: 'speak' | 'chat') {
        const characterName = modalType === 'speak' ? speakCharacter?.name : chatCharacter?.name;
        if (!characterName) return;

        const statusText = document.getElementById(`${modalType}-status-text`);
        const stopBtn = document.getElementById(`${modalType}-stop-btn`) as HTMLButtonElement | null;

        if (statusText) statusText.textContent = 'Stopping...';
        if (stopBtn) stopBtn.disabled = true;

        try {
            const result = await apiCall(`/api/characters/${characterName}/stop`, 'POST') as StopResult;
            if (statusText) {
                if (result.was_active) {
                    statusText.textContent = 'Stopped';
                } else {
                    statusText.textContent = 'Nothing to stop';
                }
            }

            // Refresh chat history after a short delay (to let browser report actual spoken text)
            if (modalType === 'chat' && result.was_active) {
                setTimeout(async () => {
                    try {
                        const memoryInfo = await getCharacterMemory(characterName) as MemoryInfo;
                        $('chat-memory-count').textContent =
                            `Memory: ${memoryInfo.message_count} messages`;
                        renderChatHistory(memoryInfo.messages, characterName);
                    } catch (e) {
                        console.error('Error refreshing memory after stop:', e);
                    }
                }, 500);  // Wait for browser to send stream_stopped event
            }
        } catch (error) {
            console.error('Stop error:', error);
            if (statusText) statusText.textContent = `Stop failed: ${(error as Error).message}`;
        } finally {
            if (stopBtn) {
                stopBtn.disabled = false;
                stopBtn.style.display = 'none';
            }
            // Clear active generation tracking
            activeGenerationCharacter = null;
            activeGenerationModal = null;
            sawStreamingStart = false;
            // Re-enable send button
            const sendBtn = document.getElementById(`${modalType}-send-btn`) as HTMLButtonElement | null;
            if (sendBtn) sendBtn.disabled = false;
        }
    }

    // =========================================================================
    // Chat Modal Functions
    // =========================================================================

    const chatModal = document.getElementById('chat-modal');

    // -------------------------------------------------------------------------
    // Image Handling for Chat
    // -------------------------------------------------------------------------

    const MAX_IMAGE_SIZE_MB = 20;  // OpenRouter limit
    const MAX_IMAGES = 5;  // Reasonable limit per message

    function clearPendingImages() {
        pendingImages = [];
        const previewsDiv = document.getElementById('chat-image-previews');
        if (previewsDiv) {
            while (previewsDiv.firstChild) {
                previewsDiv.removeChild(previewsDiv.firstChild);
            }
        }
    }

    function addImagePreview(data: string, mediaType: string) {
        if (pendingImages.length >= MAX_IMAGES) {
            showToast(`Maximum ${MAX_IMAGES} images allowed`, 'warning');
            return;
        }

        pendingImages.push({ data, mediaType });

        const previewsDiv = $('chat-image-previews');
        const thumb = document.createElement('div');
        thumb.className = 'image-preview-thumb';
        thumb.dataset.index = String(pendingImages.length - 1);

        const img = document.createElement('img');
        img.src = `data:${mediaType};base64,${data}`;

        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-btn';
        removeBtn.textContent = '×';
        removeBtn.onclick = function() {
            const idx = parseInt(thumb.dataset.index || '0');
            pendingImages.splice(idx, 1);
            thumb.remove();
            // Re-index remaining thumbs
            document.querySelectorAll<HTMLElement>('#chat-image-previews .image-preview-thumb').forEach((t, i) => {
                t.dataset.index = String(i);
            });
        };

        thumb.appendChild(img);
        thumb.appendChild(removeBtn);
        previewsDiv.appendChild(thumb);
    }

    async function processImageFile(file: File) {
        // Validate file type
        if (!file.type.startsWith('image/')) {
            showToast('Only image files are supported', 'error');
            return;
        }

        // Validate size
        if (file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024) {
            showToast(`Image too large (max ${MAX_IMAGE_SIZE_MB}MB)`, 'error');
            return;
        }

        // Convert to base64
        return new Promise<void>((resolve) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                const result = e.target?.result as string;
                // Extract base64 data (remove data:image/xxx;base64, prefix)
                const base64 = result.split(',')[1];
                const mediaType = file.type || 'image/png';
                addImagePreview(base64, mediaType);
                resolve();
            };
            reader.readAsDataURL(file);
        });
    }

    // Attach Image button handler
    function attachImage() {
        $input('chat-image-input').click();
    }

    // File input change handler
    async function handleImageSelect(event: Event) {
        const input = event.target as HTMLInputElement;
        const files = input.files;
        if (files) {
            for (const file of files) {
                await processImageFile(file);
            }
        }
        input.value = '';  // Reset input for re-selection
    }

    // Screen capture handler
    async function captureScreen() {
        try {
            // Request screen capture permission
            const stream = await navigator.mediaDevices.getDisplayMedia({
                video: true
            });

            // Create video element to capture frame
            const video = document.createElement('video');
            video.srcObject = stream;
            await video.play();

            // Wait for video to be ready
            await new Promise<void>(resolve => {
                if (video.readyState >= 2) {
                    resolve();
                } else {
                    video.onloadeddata = () => resolve();
                }
            });

            // Capture frame to canvas
            const canvas = document.createElement('canvas');
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctx = canvas.getContext('2d')!;
            ctx.drawImage(video, 0, 0);

            // Stop stream (important!)
            stream.getTracks().forEach(track => track.stop());

            // Convert to base64
            const dataUrl = canvas.toDataURL('image/png');
            const base64 = dataUrl.split(',')[1];
            addImagePreview(base64, 'image/png');

            showToast('Screen captured!', 'success');
        } catch (err) {
            if (err.name === 'NotAllowedError') {
                showToast('Screen capture permission denied', 'warning');
            } else {
                console.error('Screen capture error:', err);
                showToast('Screen capture failed', 'error');
            }
        }
    }

    // Paste handler for chat textarea
    function handleChatPaste(event) {
        const items = event.clipboardData?.items;
        if (!items) return;

        for (const item of items) {
            if (item.type.startsWith('image/')) {
                event.preventDefault();  // Prevent pasting image as text
                const file = item.getAsFile();
                if (file) {
                    processImageFile(file);
                }
            }
        }
    }

    // Character data type for extended properties
    interface CharacterData extends Character {
        memory_enabled?: boolean;
    }

    // Chat API response type
    interface ChatResponse {
        error?: string;
        detail?: string;
        twitch_chat_context?: string;
        response_text?: string;
    }

    async function openChatModal(characterName: string) {
        const character = characters.find(c => c.name === characterName) as CharacterData | undefined;
        if (!character) return;

        // Check if character has system_prompt set
        if (!character.system_prompt) {
            alert('This character has no AI system prompt configured. Use "Speak" for direct TTS.');
            return;
        }

        chatCharacter = character;
        $('chat-modal-title').textContent = `Chat with ${character.name}`;
        $textarea('chat-message').value = '';
        $input('chat-show-text').checked = true;
        $input('chat-include-twitch').checked = true;
        $input('chat-twitch-seconds').value = '';
        $('chat-status').style.display = 'none';
        $('chat-twitch-details').style.display = 'none';
        $button('chat-send-btn').disabled = false;

        // Clear pending images from previous chat
        clearPendingImages();

        // Add paste listener for images
        const chatMessage = $textarea('chat-message');
        chatMessage.removeEventListener('paste', handleChatPaste);  // Remove if exists
        chatMessage.addEventListener('paste', handleChatPaste);

        // Load and display memory/history
        try {
            const memoryInfo = await getCharacterMemory(characterName) as MemoryInfo;
            $('chat-memory-count').textContent =
                `Memory: ${memoryInfo.message_count} messages${character.memory_enabled ? '' : ' (disabled)'}`;
            renderChatHistory(memoryInfo.messages, characterName);
        } catch (e) {
            $('chat-memory-count').textContent = 'Memory: 0 messages';
            renderChatHistory([], characterName);
        }

        chatModal.classList.add('active');
    }

    function closeChatModal() {
        chatModal.classList.remove('active');
        chatCharacter = null;
        clearPendingImages();
    }

    async function sendChat() {
        if (!chatCharacter) return;

        const message = $textarea('chat-message').value.trim();
        const showText = $input('chat-show-text').checked;
        const includeTwitch = $input('chat-include-twitch').checked;
        let twitchSeconds = $input('chat-twitch-seconds').value;

        // If Include Twitch is unchecked, force twitch_chat_seconds to 0
        if (!includeTwitch) {
            twitchSeconds = '0';
        }

        if (!message) {
            alert('Please enter a message');
            return;
        }

        const statusDiv = $('chat-status');
        const statusText = $('chat-status-text');
        const sendBtn = $button('chat-send-btn');
        const stopBtn = $button('chat-stop-btn');

        statusDiv.style.display = 'block';
        statusText.textContent = 'Generating...';
        sendBtn.disabled = true;
        stopBtn.style.display = 'inline-block';

        // Track active generation so we can hide stop button when streaming ends
        activeGenerationCharacter = chatCharacter.name;
        activeGenerationModal = 'chat';
        sawStreamingStart = false;

        try {
            // Add user message bubble immediately (with image indicator if images attached)
            const hasImages = pendingImages.length > 0;
            const displayMessage = hasImages ? `[${pendingImages.length} image(s)] ${message}` : message;
            addChatBubble('user', displayMessage, chatCharacter.name);
            $textarea('chat-message').value = '';

            // Capture images before clearing
            const imagesToSend = hasImages ? [...pendingImages] : null;
            clearPendingImages();

            const result = await sendCharacterChat(chatCharacter.name, message, showText, twitchSeconds, imagesToSend) as ChatResponse;
            if (result.error || result.detail) {
                statusText.textContent = `Error: ${result.error || result.detail}`;
                // Error - hide stop button immediately
                stopBtn.style.display = 'none';
                activeGenerationCharacter = null;
                activeGenerationModal = null;
            } else {
                // Add Twitch context bubble if present
                if (result.twitch_chat_context) {
                    const lines = result.twitch_chat_context.split('\n');
                    // Show trimmed version (last 3-5 messages)
                    const trimmed = lines.slice(-4).map(l => l.length > 60 ? l.substring(0, 57) + '...' : l).join(' | ');
                    addContextBubble(`📺 Twitch chat (${lines.length}): ${trimmed}`);
                }

                // Add assistant response bubble
                addChatBubble('assistant', result.response_text || '', chatCharacter.name);

                let statusMsg = 'Playing audio...';
                const twitchDetails = document.getElementById('chat-twitch-details');
                const twitchSummary = document.getElementById('chat-twitch-summary');
                const twitchContextText = document.getElementById('chat-twitch-context-text');

                if (result.twitch_chat_context) {
                    const lines = result.twitch_chat_context.split('\n').length;
                    statusMsg += ` (${lines} chat msgs)`;
                    twitchSummary.textContent = `Twitch Chat Context (${lines} messages)`;
                    twitchContextText.textContent = result.twitch_chat_context;
                    twitchDetails.style.display = 'block';
                } else {
                    twitchDetails.style.display = 'none';
                }
                statusText.textContent = statusMsg;
                loadHistory();
                // Update memory count
                const memoryInfo = await getCharacterMemory(chatCharacter.name) as MemoryInfo;
                const charData = chatCharacter as CharacterData;
                $('chat-memory-count').textContent =
                    `Memory: ${memoryInfo.message_count} messages${charData.memory_enabled ? '' : ' (not saving)'}`;
                // Stop button will be hidden by handleMessage when streaming ends
            }
        } catch (error) {
            console.error('Chat error:', error);
            statusText.textContent = `Error: ${error.message || 'Unknown error'}`;
            // Error - hide stop button immediately
            stopBtn.style.display = 'none';
            activeGenerationCharacter = null;
            activeGenerationModal = null;
        } finally {
            sendBtn.disabled = false;
        }
    }

    async function clearChatMemory() {
        if (!chatCharacter) return;

        if (!confirm(`Clear conversation memory for ${chatCharacter.name}?`)) {
            return;
        }

        try {
            await clearCharacterMemory(chatCharacter.name);
            document.getElementById('chat-memory-count').textContent = 'Memory: 0 messages';
            document.getElementById('chat-status').style.display = 'block';
            document.getElementById('chat-status-text').textContent = 'Memory cleared!';
            // Clear the chat history UI
            renderChatHistory([], chatCharacter.name);
            document.getElementById('chat-twitch-details').style.display = 'none';
        } catch (error) {
            console.error('Error clearing memory:', error);
            alert('Error clearing memory');
        }
    }

    // =========================================================================
    // Rendering
    // =========================================================================

    function renderHistory(history) {
        if (!history || history.length === 0) {
            historyList.innerHTML = '<div class="history-item"><span class="history-content">No history yet</span></div>';
            return;
        }

        historyList.innerHTML = history.map(item => {
            const time = new Date(item.timestamp).toLocaleTimeString();
            return `
                <div class="history-item">
                    <span class="history-channel">${escapeHtml(item.channel)}</span>
                    <span class="history-content">${escapeHtml(item.content)}</span>
                    <span class="history-time">${escapeHtml(time)}</span>
                </div>
            `;
        }).join('');
    }

    function renderCharacters() {
        if (!charactersContainer) return;

        if (characters.length === 0) {
            charactersContainer.innerHTML = `
                <div class="no-channels">
                    <p>No characters configured yet.</p>
                    <p>Click "Create Character" to add one.</p>
                </div>
            `;
            return;
        }

        charactersContainer.innerHTML = characters.map(ch => renderCharacterCard(ch)).join('');
    }

    function renderCharacterCard(character) {
        // Connection status
        let statusClass = '';
        let statusText = 'offline';
        if (!character.connected) {
            statusClass = '';
            statusText = 'offline';
        } else if (character.streaming) {
            statusClass = 'streaming';
            statusText = 'streaming';
        } else if (character.playing) {
            statusClass = 'playing';
            statusText = 'playing';
        } else {
            statusText = 'ready';
        }

        const connectedClass = character.connected ? '' : 'disconnected';
        const hasAI = character.system_prompt ? '<span class="voice-indicator">AI</span>' : '';

        // Show description or system_prompt preview (escaped)
        const descriptionText = escapeHtml(character.description ||
            (character.system_prompt ? character.system_prompt.substring(0, 80) + '...' : 'No description'));

        // Escape user-controlled values
        const safeName = escapeHtml(character.name);
        const safeIcon = escapeHtml(character.icon);
        const safeColor = sanitizeColor(character.color);
        const safeModel = escapeHtml(character.model ? character.model.split('/').pop() : '');
        const safeTtsModel = escapeHtml(character.tts_provider === 'cartesia'
            ? (character.tts_settings?.model_id || 'sonic').replace('sonic-', '')
            : (character.elevenlabs_model_id || 'multilingual_v2').replace('eleven_', '').replace('_', ' '));

        return `
            <div class="channel-card ${connectedClass}" data-character="${safeName}" style="border-left-color: ${safeColor}">
                <div class="channel-header">
                    <div class="channel-name">
                        <span class="channel-icon">${safeIcon}</span>
                        ${safeName}
                        ${hasAI}
                    </div>
                    <span class="channel-status ${statusClass}">${statusText}</span>
                </div>
                <p class="channel-description">${descriptionText}</p>
                <div class="channel-controls">
                    <div class="control-row" style="font-size: 0.75rem; color: var(--text-secondary);">
                        <span>TTS: ${character.tts_provider === 'cartesia' ? 'Cartesia' : 'ElevenLabs'}</span>
                        <span>${safeTtsModel}</span>
                    </div>
                    ${character.system_prompt ? `<div class="control-row" style="font-size: 0.75rem; color: var(--text-secondary);"><span>AI: ${safeModel}</span></div>` : ''}
                </div>
                <div class="channel-actions">
                    <button data-action="speak" data-character="${safeName}">Speak</button>
                    ${character.system_prompt
                        ? `<button data-action="chat" data-character="${safeName}">Chat</button>`
                        : ''}
                    <button data-action="copy-url" data-character="${safeName}" title="Copy browser source URL for OBS">Copy URL</button>
                    <button data-action="rotate-token" data-character="${safeName}" title="Invalidate old URL and generate new token">Rotate</button>
                    <button data-action="edit" data-character="${safeName}">Edit</button>
                    <button class="secondary" data-action="delete" data-character="${safeName}">Delete</button>
                </div>
            </div>
        `;
    }

    // =========================================================================
    // Global Functions (for onclick handlers)
    // =========================================================================

    // Character modal exports
    window.openCreateCharacterModal = openCreateCharacterModal;
    window.closeCharacterModal = closeCharacterModal;
    window.editCharacter = async function(characterName: string) {
        // Fetch fresh data from API to avoid stale cached data
        const character = await apiCall(`/api/characters/${encodeURIComponent(characterName)}`) as Character | { error: string } | null;
        if (character && !('error' in character)) {
            openEditCharacterModal(character);
        } else {
            showToast('Failed to load character', 'error');
        }
    };
    window.deleteCharacter = deleteCharacterAPI;

    // Speak modal exports
    window.openSpeakModal = openSpeakModal;
    window.closeSpeakModal = closeSpeakModal;
    window.sendSpeak = sendSpeak;
    window.stopGeneration = stopGeneration;

    // Chat modal exports
    window.openChatModal = openChatModal;
    window.closeChatModal = closeChatModal;
    window.sendChat = sendChat;
    window.clearChatMemory = clearChatMemory;

    // Image handling exports
    window.attachImage = attachImage;
    window.handleImageSelect = handleImageSelect;
    window.captureScreen = captureScreen;

    // Preview exports
    window.previewCharacterTextStyle = previewCharacterTextStyle;
    window.stopCharacterTextPreview = stopCharacterTextPreview;

    // Provider dropdown
    window.updateProviderDropdown = updateProviderDropdown;

    // ElevenLabs models
    window.loadVoiceModels = loadVoiceModels;
    window.updateModelInfo = updateModelInfo;

    // Cartesia TTS
    window.toggleTTSProvider = toggleTTSProvider;
    window.updateCartesiaVoiceInfo = updateCartesiaVoiceInfo;
    window.loadCartesiaVoices = loadCartesiaVoices;
    window.selectCartesiaVoice = selectCartesiaVoice;
    window.onCartesiaManualIdChange = onCartesiaManualIdChange;

    // Copy URL function (browser source URL with auth token)
    window.copyCharacterUrl = async function(characterName: string) {
        const character = characters.find(c => c.name === characterName);
        if (!character?.ws_token) {
            showToast('Character token not found', 'error');
            return;
        }
        const url = `${window.location.origin}/channel/${encodeURIComponent(characterName)}?token=${encodeURIComponent(character.ws_token)}`;
        try {
            await navigator.clipboard.writeText(url);
            // Brief visual feedback - find the button and flash it
            const card = document.querySelector(`[data-character="${CSS.escape(characterName)}"]`);
            if (card) {
                const btn = card.querySelector('button[data-action="copy-url"]');
                if (btn) {
                    const originalText = btn.textContent;
                    btn.textContent = 'Copied!';
                    setTimeout(() => { btn.textContent = originalText; }, 1500);
                }
            }
        } catch (err) {
            console.error('Failed to copy URL:', err);
            // Fallback: show the URL in an alert
            prompt('Copy this URL for OBS browser source:', url);
        }
    };

    // Rotate token function (invalidates existing browser source URLs)
    interface RotateTokenResult {
        success?: boolean;
        ws_token?: string;
        detail?: string;
    }

    window.rotateCharacterToken = async function(characterName: string) {
        if (!confirm(`Rotate token for "${characterName}"?\n\nThis will invalidate any existing OBS browser source URLs. You'll need to update your OBS sources with the new URL.`)) {
            return;
        }
        try {
            const result = await apiCall(`/api/characters/${encodeURIComponent(characterName)}/rotate-token`, 'POST') as RotateTokenResult | null;
            if (result?.success) {
                // Update local character data
                const character = characters.find(c => c.name === characterName);
                if (character && result.ws_token) {
                    character.ws_token = result.ws_token;
                }
                showToast('Token rotated. Copy new URL for OBS.', 'success');
            } else {
                showToast(result?.detail || 'Failed to rotate token', 'error');
            }
        } catch (err) {
            console.error('Failed to rotate token:', err);
            showToast('Failed to rotate token', 'error');
        }
    };

    // =========================================================================
    // Twitch Status
    // =========================================================================

    const twitchBtn = document.getElementById('twitch-btn');
    const twitchBtnText = document.getElementById('twitch-btn-text');

    async function checkTwitchStatus() {
        if (!twitchBtn || !twitchBtnText) return;

        try {
            const response = await fetch('/api/twitch/status');
            const data = await response.json();

            if (data.connected) {
                twitchBtn.classList.add('connected');
                twitchBtnText.textContent = `#${data.channel}`;
            } else {
                twitchBtn.classList.remove('connected');
                twitchBtnText.textContent = 'Twitch';
            }
        } catch (e) {
            console.error('Error checking Twitch status:', e);
        }
    }

    // =========================================================================
    // Initialize
    // =========================================================================

    // Character form submission
    if (characterForm) {
        characterForm.addEventListener('submit', handleCharacterFormSubmit);
    }

    // Close character modal on background click
    if (characterModal) {
        characterModal.addEventListener('click', (e) => {
            if (e.target === characterModal) {
                closeCharacterModal();
            }
        });
    }

    // Close speak modal on background click
    if (speakModal) {
        speakModal.addEventListener('click', (e) => {
            if (e.target === speakModal) {
                closeSpeakModal();
            }
        });
    }

    // Close chat modal on background click
    if (chatModal) {
        chatModal.addEventListener('click', (e) => {
            if (e.target === chatModal) {
                closeChatModal();
            }
        });
    }

    // Event delegation for character action buttons (prevents XSS via onclick)
    if (charactersContainer) {
        charactersContainer.addEventListener('click', (e) => {
            const target = e.target as HTMLElement;
            const button = target.closest('button[data-action]') as HTMLButtonElement | null;
            if (!button) return;

            const action = button.dataset.action;
            const characterName = button.dataset.character;
            if (!characterName) return;

            switch (action) {
                case 'speak':
                    window.openSpeakModal(characterName);
                    break;
                case 'chat':
                    window.openChatModal(characterName);
                    break;
                case 'copy-url':
                    window.copyCharacterUrl(characterName);
                    break;
                case 'rotate-token':
                    window.rotateCharacterToken(characterName);
                    break;
                case 'edit':
                    window.editCharacter(characterName);
                    break;
                case 'delete':
                    window.deleteCharacter(characterName);
                    break;
            }
        });
    }

    connect();
    getAllCharacters();
    loadPresets();
    loadHistory();
    checkTwitchStatus();
    loadElevenLabsModels();

// Refresh history periodically
setInterval(loadHistory, 10000);

// Refresh Twitch status periodically
setInterval(checkTwitchStatus, 15000);
