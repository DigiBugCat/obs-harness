/**
 * OBS Harness Dashboard
 * Real-time monitoring and control of characters
 */

(function() {
    'use strict';

    // WebSocket connection
    let ws = null;
    let reconnectTimeout = null;
    const reconnectDelay = 2000;

    // State
    let presets = [];
    let characters = [];
    let editingCharacter = null;
    let chatCharacter = null;
    let speakCharacter = null;
    let elevenlabsModels = [];  // Cached ElevenLabs models

    // DOM elements
    const wsStatus = document.getElementById('ws-status');
    const wsStatusText = document.getElementById('ws-status-text');
    const charactersContainer = document.getElementById('characters-container');
    const historyList = document.getElementById('history-list');

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
            if (reconnectTimeout) {
                clearTimeout(reconnectTimeout);
                reconnectTimeout = null;
            }
        };

        ws.onclose = () => {
            wsStatus.classList.remove('connected');
            wsStatusText.textContent = 'Disconnected';
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
            reconnectTimeout = setTimeout(() => {
                connect();
            }, reconnectDelay);
        }
    }

    function handleMessage(msg) {
        if (msg.type === 'characters') {
            // Merge connection status into character list
            const statusMap = new Map(msg.characters.map(c => [c.name, c]));
            characters = characters.map(ch => ({
                ...ch,
                connected: statusMap.has(ch.name),
                playing: statusMap.get(ch.name)?.playing || false,
                streaming: statusMap.get(ch.name)?.streaming || false,
            }));
            renderCharacters();
        }
    }

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
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 6px;
            color: white;
            font-size: 0.875rem;
            z-index: 10000;
            animation: slideIn 0.3s ease;
            max-width: 400px;
            word-wrap: break-word;
        `;

        // Set background color based on type
        const colors = {
            success: '#4ecca3',
            error: '#e94560',
            warning: '#ffc107',
            info: '#3498db'
        };
        toast.style.background = colors[type] || colors.info;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    // Add toast animation styles
    const toastStyles = document.createElement('style');
    toastStyles.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
    `;
    document.head.appendChild(toastStyles);

    // =========================================================================
    // API Calls
    // =========================================================================

    async function apiCall(endpoint, method = 'GET', body = null, showErrors = true) {
        const options = {
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
            const errorMsg = error.message || 'Network error';
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
        const result = await apiCall('/api/characters', 'POST', data);
        await getAllCharacters();
        return result;
    }

    async function updateCharacter(name, data) {
        const result = await apiCall(`/api/characters/${name}`, 'PUT', data);
        await getAllCharacters();
        return result;
    }

    async function deleteCharacterAPI(name) {
        if (!confirm(`Delete character "${name}"? This cannot be undone.`)) {
            return;
        }
        const result = await apiCall(`/api/characters/${name}`, 'DELETE');
        await getAllCharacters();
        return result;
    }

    // Provider dropdown
    async function updateProviderDropdown(model) {
        const select = document.getElementById('character-provider');
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
            const result = await apiCall(`/api/openrouter/models/${encodeURIComponent(model)}/providers`, 'GET', null, false);
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

    async function loadVoiceModels(voiceId) {
        const select = document.getElementById('character-tts-model');
        const infoEl = document.getElementById('tts-model-info');
        if (!select || !voiceId) return;

        // Clear info
        if (infoEl) infoEl.textContent = '';

        try {
            const voice = await apiCall(`/api/elevenlabs/voices/${voiceId}`, 'GET', null, false);
            if (voice && voice.high_quality_base_model_ids && voice.high_quality_base_model_ids.length > 0) {
                // Highlight compatible models
                const compatibleIds = new Set(voice.high_quality_base_model_ids);
                Array.from(select.options).forEach(option => {
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

    function updateModelInfo(modelId) {
        const infoEl = document.getElementById('tts-model-info');
        if (!infoEl) return;

        const model = elevenlabsModels.find(m => m.model_id === modelId);
        if (model) {
            const features = [];
            if (model.can_use_style) features.push('style');
            if (model.can_use_speaker_boost) features.push('speaker boost');
            if (model.can_be_finetuned) features.push('finetunable');

            infoEl.textContent = features.length > 0
                ? `Features: ${features.join(', ')}`
                : '';
        }
    }

    // Character actions
    async function sendCharacterSpeak(characterName, text, showText) {
        return apiCall(`/api/characters/${characterName}/speak`, 'POST', {
            text,
            show_text: showText,
        });
    }

    async function sendCharacterChat(characterName, message, showText, twitchChatSeconds = null) {
        const body = {
            message,
            show_text: showText,
        };
        if (twitchChatSeconds !== null && twitchChatSeconds !== '') {
            body.twitch_chat_seconds = parseInt(twitchChatSeconds);
        }
        return apiCall(`/api/characters/${characterName}/chat`, 'POST', body);
    }

    async function getCharacterMemory(characterName) {
        return apiCall(`/api/characters/${characterName}/memory`);
    }

    async function clearCharacterMemory(characterName) {
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
                content.textContent = msg.content;

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

    let characterPreviewAnimator = null;
    let characterPreviewAnimationFrame = null;

    function previewCharacterTextStyle() {
        stopCharacterTextPreview();

        const canvas = document.getElementById('character-preview-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        characterPreviewAnimator = new TextAnimator(ctx, canvas.width, canvas.height);

        const config = {
            style: document.getElementById('character-text-style').value,
            fontFamily: document.getElementById('character-font-family').value,
            fontSize: parseInt(document.getElementById('character-font-size').value),
            duration: parseInt(document.getElementById('character-text-duration').value),
            color: document.getElementById('character-text-color').value,
            strokeColor: document.getElementById('character-stroke-color').value,
            strokeWidth: parseInt(document.getElementById('character-stroke-width').value),
            positionX: parseInt(document.getElementById('character-position-x').value) / 100,
            positionY: parseInt(document.getElementById('character-position-y').value) / 100,
        };

        const scaleFactor = canvas.width / 800;

        characterPreviewAnimator.show({
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
            characterPreviewAnimator.update();
            characterPreviewAnimator.draw();

            if (characterPreviewAnimator.current) {
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
        const canvas = document.getElementById('character-preview-canvas');
        if (canvas) {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    }

    // =========================================================================
    // Character Modal Functions
    // =========================================================================

    const characterModal = document.getElementById('character-modal');
    const characterForm = document.getElementById('character-form');
    const characterModalTitle = document.getElementById('character-modal-title');

    function openCreateCharacterModal() {
        editingCharacter = null;
        characterModalTitle.textContent = 'Create Character';
        characterForm.reset();
        document.getElementById('character-name').disabled = false;

        // Set defaults
        document.getElementById('character-color').value = '#e94560';
        document.getElementById('character-icon').value = '\uD83D\uDD0A';
        document.getElementById('character-stability').value = 50;
        document.getElementById('character-stability-value').textContent = '0.50';
        document.getElementById('character-similarity').value = 75;
        document.getElementById('character-similarity-value').textContent = '0.75';
        document.getElementById('character-voice-style').value = 0;
        document.getElementById('character-style-value').textContent = '0.00';
        document.getElementById('character-voice-speed').value = 100;
        document.getElementById('character-speed-value').textContent = '1.0';
        document.getElementById('character-volume').value = 100;
        document.getElementById('character-volume-value').textContent = '100';
        document.getElementById('character-text-style').value = 'typewriter';
        document.getElementById('character-font-family').value = 'Arial';
        document.getElementById('character-font-size').value = 48;
        document.getElementById('character-text-duration').value = 3000;
        document.getElementById('character-text-color').value = '#ffffff';
        document.getElementById('character-stroke-color').value = '#000000';
        document.getElementById('character-stroke-width').value = 0;
        document.getElementById('character-stroke-width-value').textContent = '0';
        document.getElementById('character-position-x').value = 50;
        document.getElementById('character-pos-x-value').textContent = '50';
        document.getElementById('character-position-y').value = 50;
        document.getElementById('character-pos-y-value').textContent = '50';
        document.getElementById('character-model').value = 'anthropic/claude-sonnet-4.5';
        document.getElementById('character-provider').innerHTML = '<option value="">Default (auto)</option>';
        document.getElementById('character-provider').value = '';
        document.getElementById('character-temperature').value = 70;
        document.getElementById('character-temp-value').textContent = '0.7';
        document.getElementById('character-max-tokens').value = 1024;

        // TTS model default
        document.getElementById('character-tts-model').value = 'eleven_multilingual_v2';
        document.getElementById('tts-model-info').textContent = '';

        // Memory & Twitch settings
        document.getElementById('character-memory-enabled').checked = false;
        document.getElementById('character-twitch-chat-enabled').checked = false;
        document.getElementById('character-twitch-chat-seconds').value = 60;
        document.getElementById('character-twitch-chat-max').value = 20;

        characterModal.classList.add('active');
    }

    function openEditCharacterModal(character) {
        editingCharacter = character;
        characterModalTitle.textContent = 'Edit Character';

        // Basic info
        document.getElementById('character-name').value = character.name;
        document.getElementById('character-name').disabled = true;
        document.getElementById('character-description').value = character.description || '';
        document.getElementById('character-color').value = character.color;
        document.getElementById('character-icon').value = character.icon;

        // Voice settings
        document.getElementById('character-voice-id').value = character.elevenlabs_voice_id;
        document.getElementById('character-tts-model').value = character.elevenlabs_model_id || 'eleven_multilingual_v2';
        // Load voice info to show compatible models
        loadVoiceModels(character.elevenlabs_voice_id);
        document.getElementById('character-stability').value = Math.round(character.voice_stability * 100);
        document.getElementById('character-stability-value').textContent = character.voice_stability.toFixed(2);
        document.getElementById('character-similarity').value = Math.round(character.voice_similarity_boost * 100);
        document.getElementById('character-similarity-value').textContent = character.voice_similarity_boost.toFixed(2);
        document.getElementById('character-voice-style').value = Math.round(character.voice_style * 100);
        document.getElementById('character-style-value').textContent = character.voice_style.toFixed(2);
        document.getElementById('character-voice-speed').value = Math.round(character.voice_speed * 100);
        document.getElementById('character-speed-value').textContent = character.voice_speed.toFixed(1);

        // Audio settings
        document.getElementById('character-volume').value = Math.round(character.default_volume * 100);
        document.getElementById('character-volume-value').textContent = Math.round(character.default_volume * 100);
        document.getElementById('character-muted').checked = character.mute_state;

        // Text style settings
        document.getElementById('character-text-style').value = character.default_text_style;
        document.getElementById('character-font-family').value = character.text_font_family;
        document.getElementById('character-font-size').value = character.text_font_size;
        document.getElementById('character-text-duration').value = character.text_duration;
        document.getElementById('character-text-color').value = character.text_color;
        document.getElementById('character-stroke-color').value = character.text_stroke_color || '#000000';
        document.getElementById('character-stroke-width').value = character.text_stroke_width;
        document.getElementById('character-stroke-width-value').textContent = character.text_stroke_width;
        document.getElementById('character-position-x').value = Math.round(character.text_position_x * 100);
        document.getElementById('character-pos-x-value').textContent = Math.round(character.text_position_x * 100);
        document.getElementById('character-position-y').value = Math.round(character.text_position_y * 100);
        document.getElementById('character-pos-y-value').textContent = Math.round(character.text_position_y * 100);

        // AI settings
        document.getElementById('character-prompt').value = character.system_prompt || '';
        document.getElementById('character-model').value = character.model;
        // Fetch providers for this model and set current value
        updateProviderDropdown(character.model).then(() => {
            document.getElementById('character-provider').value = character.provider || '';
        });
        document.getElementById('character-temperature').value = Math.round(character.temperature * 100);
        document.getElementById('character-temp-value').textContent = character.temperature.toFixed(1);
        document.getElementById('character-max-tokens').value = character.max_tokens;

        // Memory & Twitch settings
        document.getElementById('character-memory-enabled').checked = character.memory_enabled || false;
        document.getElementById('character-twitch-chat-enabled').checked = character.twitch_chat_enabled || false;
        document.getElementById('character-twitch-chat-seconds').value = character.twitch_chat_window_seconds || 60;
        document.getElementById('character-twitch-chat-max').value = character.twitch_chat_max_messages || 20;

        characterModal.classList.add('active');
    }

    function closeCharacterModal() {
        characterModal.classList.remove('active');
        editingCharacter = null;
        stopCharacterTextPreview();
    }

    async function handleCharacterFormSubmit(e) {
        e.preventDefault();

        const data = {
            name: document.getElementById('character-name').value,
            description: document.getElementById('character-description').value || null,
            color: document.getElementById('character-color').value,
            icon: document.getElementById('character-icon').value,
            elevenlabs_voice_id: document.getElementById('character-voice-id').value,
            elevenlabs_model_id: document.getElementById('character-tts-model').value,
            voice_stability: parseInt(document.getElementById('character-stability').value) / 100,
            voice_similarity_boost: parseInt(document.getElementById('character-similarity').value) / 100,
            voice_style: parseInt(document.getElementById('character-voice-style').value) / 100,
            voice_speed: parseInt(document.getElementById('character-voice-speed').value) / 100,
            default_volume: parseInt(document.getElementById('character-volume').value) / 100,
            mute_state: document.getElementById('character-muted').checked,
            default_text_style: document.getElementById('character-text-style').value,
            text_font_family: document.getElementById('character-font-family').value,
            text_font_size: parseInt(document.getElementById('character-font-size').value),
            text_duration: parseInt(document.getElementById('character-text-duration').value),
            text_color: document.getElementById('character-text-color').value,
            text_stroke_color: parseInt(document.getElementById('character-stroke-width').value) > 0
                ? document.getElementById('character-stroke-color').value : null,
            text_stroke_width: parseInt(document.getElementById('character-stroke-width').value),
            text_position_x: parseInt(document.getElementById('character-position-x').value) / 100,
            text_position_y: parseInt(document.getElementById('character-position-y').value) / 100,
            system_prompt: document.getElementById('character-prompt').value || null,
            model: document.getElementById('character-model').value,
            provider: document.getElementById('character-provider').value || null,
            temperature: parseInt(document.getElementById('character-temperature').value) / 100,
            max_tokens: parseInt(document.getElementById('character-max-tokens').value),
            memory_enabled: document.getElementById('character-memory-enabled').checked,
            twitch_chat_enabled: document.getElementById('character-twitch-chat-enabled').checked,
            twitch_chat_window_seconds: parseInt(document.getElementById('character-twitch-chat-seconds').value),
            twitch_chat_max_messages: parseInt(document.getElementById('character-twitch-chat-max').value),
        };

        try {
            if (editingCharacter) {
                await updateCharacter(editingCharacter.name, data);
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

    const speakModal = document.getElementById('speak-modal');

    function openSpeakModal(characterName) {
        const character = characters.find(c => c.name === characterName);
        if (!character) return;

        speakCharacter = character;
        document.getElementById('speak-modal-title').textContent = `Speak as ${character.name}`;
        document.getElementById('speak-text').value = '';
        document.getElementById('speak-show-text').checked = true;
        document.getElementById('speak-status').style.display = 'none';
        document.getElementById('speak-send-btn').disabled = false;

        speakModal.classList.add('active');
    }

    function closeSpeakModal() {
        speakModal.classList.remove('active');
        speakCharacter = null;
    }

    async function sendSpeak() {
        if (!speakCharacter) return;

        const text = document.getElementById('speak-text').value.trim();
        const showText = document.getElementById('speak-show-text').checked;

        if (!text) {
            alert('Please enter text to speak');
            return;
        }

        const statusDiv = document.getElementById('speak-status');
        const statusText = document.getElementById('speak-status-text');
        const sendBtn = document.getElementById('speak-send-btn');

        statusDiv.style.display = 'block';
        statusText.textContent = 'Speaking...';
        sendBtn.disabled = true;

        try {
            const result = await sendCharacterSpeak(speakCharacter.name, text, showText);
            if (result.error || result.detail) {
                statusText.textContent = `Error: ${result.error || result.detail}`;
            } else {
                statusText.textContent = 'Complete!';
                document.getElementById('speak-text').value = '';
                loadHistory();
            }
        } catch (error) {
            console.error('Speak error:', error);
            statusText.textContent = `Error: ${error.message || 'Unknown error'}`;
        } finally {
            sendBtn.disabled = false;
        }
    }

    // =========================================================================
    // Chat Modal Functions
    // =========================================================================

    const chatModal = document.getElementById('chat-modal');

    async function openChatModal(characterName) {
        const character = characters.find(c => c.name === characterName);
        if (!character) return;

        // Check if character has system_prompt set
        if (!character.system_prompt) {
            alert('This character has no AI system prompt configured. Use "Speak" for direct TTS.');
            return;
        }

        chatCharacter = character;
        document.getElementById('chat-modal-title').textContent = `Chat with ${character.name}`;
        document.getElementById('chat-message').value = '';
        document.getElementById('chat-show-text').checked = true;
        document.getElementById('chat-include-twitch').checked = true;
        document.getElementById('chat-twitch-seconds').value = '';
        document.getElementById('chat-status').style.display = 'none';
        document.getElementById('chat-twitch-details').style.display = 'none';
        document.getElementById('chat-send-btn').disabled = false;

        // Load and display memory/history
        try {
            const memoryInfo = await getCharacterMemory(characterName);
            document.getElementById('chat-memory-count').textContent =
                `Memory: ${memoryInfo.message_count} messages${character.memory_enabled ? '' : ' (disabled)'}`;
            renderChatHistory(memoryInfo.messages, characterName);
        } catch (e) {
            document.getElementById('chat-memory-count').textContent = 'Memory: 0 messages';
            renderChatHistory([], characterName);
        }

        chatModal.classList.add('active');
    }

    function closeChatModal() {
        chatModal.classList.remove('active');
        chatCharacter = null;
    }

    async function sendChat() {
        if (!chatCharacter) return;

        const message = document.getElementById('chat-message').value.trim();
        const showText = document.getElementById('chat-show-text').checked;
        const includeTwitch = document.getElementById('chat-include-twitch').checked;
        let twitchSeconds = document.getElementById('chat-twitch-seconds').value;

        // If Include Twitch is unchecked, force twitch_chat_seconds to 0
        if (!includeTwitch) {
            twitchSeconds = '0';
        }

        if (!message) {
            alert('Please enter a message');
            return;
        }

        const statusDiv = document.getElementById('chat-status');
        const statusText = document.getElementById('chat-status-text');
        const sendBtn = document.getElementById('chat-send-btn');

        statusDiv.style.display = 'block';
        statusText.textContent = 'Sending...';
        sendBtn.disabled = true;

        try {
            // Add user message bubble immediately
            addChatBubble('user', message, chatCharacter.name);
            document.getElementById('chat-message').value = '';

            const result = await sendCharacterChat(chatCharacter.name, message, showText, twitchSeconds);
            if (result.error || result.detail) {
                statusText.textContent = `Error: ${result.error || result.detail}`;
            } else {
                // Add Twitch context bubble if present
                if (result.twitch_chat_context) {
                    const lines = result.twitch_chat_context.split('\n');
                    // Show trimmed version (last 3-5 messages)
                    const trimmed = lines.slice(-4).map(l => l.length > 60 ? l.substring(0, 57) + '...' : l).join(' | ');
                    addContextBubble(`📺 Twitch chat (${lines.length}): ${trimmed}`);
                }

                // Add assistant response bubble
                addChatBubble('assistant', result.response_text, chatCharacter.name);

                let statusMsg = 'Response complete!';
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
                const memoryInfo = await getCharacterMemory(chatCharacter.name);
                document.getElementById('chat-memory-count').textContent =
                    `Memory: ${memoryInfo.message_count} messages${chatCharacter.memory_enabled ? '' : ' (not saving)'}`;
            }
        } catch (error) {
            console.error('Chat error:', error);
            statusText.textContent = `Error: ${error.message || 'Unknown error'}`;
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
                    <span class="history-channel">${item.channel}</span>
                    <span class="history-content">${item.content}</span>
                    <span class="history-time">${time}</span>
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

        // Show description or system_prompt preview
        const descriptionText = character.description ||
            (character.system_prompt ? character.system_prompt.substring(0, 80) + '...' : 'No description');

        return `
            <div class="channel-card ${connectedClass}" data-character="${character.name}" style="border-left-color: ${character.color}">
                <div class="channel-header">
                    <div class="channel-name">
                        <span class="channel-icon">${character.icon}</span>
                        ${character.name}
                        ${hasAI}
                    </div>
                    <span class="channel-status ${statusClass}">${statusText}</span>
                </div>
                <p class="channel-description">${descriptionText}</p>
                <div class="channel-controls">
                    <div class="control-row" style="font-size: 0.75rem; color: var(--text-secondary);">
                        <span>Voice: ${character.elevenlabs_voice_id.substring(0, 12)}...</span>
                        <span>TTS: ${(character.elevenlabs_model_id || 'eleven_multilingual_v2').replace('eleven_', '').replace('_', ' ')}</span>
                    </div>
                    ${character.system_prompt ? `<div class="control-row" style="font-size: 0.75rem; color: var(--text-secondary);"><span>AI: ${character.model.split('/').pop()}</span></div>` : ''}
                </div>
                <div class="channel-actions">
                    <button onclick="window.openSpeakModal('${character.name}')">Speak</button>
                    ${character.system_prompt
                        ? `<button onclick="window.openChatModal('${character.name}')">Chat</button>`
                        : ''}
                    <button onclick="window.copyCharacterUrl('${character.name}')">Copy URL</button>
                    <button onclick="window.editCharacter('${character.name}')">Edit</button>
                    <button class="secondary" onclick="window.deleteCharacter('${character.name}')">Delete</button>
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
    window.editCharacter = function(characterName) {
        const character = characters.find(c => c.name === characterName);
        if (character) {
            openEditCharacterModal(character);
        }
    };
    window.deleteCharacter = deleteCharacterAPI;

    // Speak modal exports
    window.openSpeakModal = openSpeakModal;
    window.closeSpeakModal = closeSpeakModal;
    window.sendSpeak = sendSpeak;

    // Chat modal exports
    window.openChatModal = openChatModal;
    window.closeChatModal = closeChatModal;
    window.sendChat = sendChat;
    window.clearChatMemory = clearChatMemory;

    // Preview exports
    window.previewCharacterTextStyle = previewCharacterTextStyle;
    window.stopCharacterTextPreview = stopCharacterTextPreview;

    // Provider dropdown
    window.updateProviderDropdown = updateProviderDropdown;

    // ElevenLabs models
    window.loadVoiceModels = loadVoiceModels;
    window.updateModelInfo = updateModelInfo;

    // Copy URL function
    window.copyCharacterUrl = async function(characterName) {
        const url = `${window.location.origin}/channel/${characterName}`;
        try {
            await navigator.clipboard.writeText(url);
            // Brief visual feedback - find the button and flash it
            const card = document.querySelector(`[data-character="${characterName}"]`);
            if (card) {
                const btn = Array.from(card.querySelectorAll('button')).find(b => b.textContent === 'Copy URL');
                if (btn) {
                    const originalText = btn.textContent;
                    btn.textContent = 'Copied!';
                    setTimeout(() => { btn.textContent = originalText; }, 1500);
                }
            }
        } catch (err) {
            console.error('Failed to copy URL:', err);
            // Fallback: show the URL in an alert
            prompt('Copy this URL:', url);
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
})();
