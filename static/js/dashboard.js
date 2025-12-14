/**
 * OBS Harness Dashboard
 * Real-time monitoring and control of audio channels
 */

(function() {
    'use strict';

    // WebSocket connection
    let ws = null;
    let reconnectTimeout = null;
    const reconnectDelay = 2000;

    // State
    let channels = [];
    let presets = [];
    let editingChannel = null;

    // DOM elements
    const wsStatus = document.getElementById('ws-status');
    const wsStatusText = document.getElementById('ws-status-text');
    const channelsContainer = document.getElementById('channels-container');
    const historyList = document.getElementById('history-list');
    const channelModal = document.getElementById('channel-modal');
    const channelForm = document.getElementById('channel-form');
    const modalTitle = document.getElementById('modal-title');

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
        if (msg.type === 'channels') {
            // Merge connection status into full channel list
            const connectedNames = new Set(msg.channels.map(c => c.name));
            channels = channels.map(ch => ({
                ...ch,
                connected: connectedNames.has(ch.name),
                playing: msg.channels.find(c => c.name === ch.name)?.playing || false,
                streaming: msg.channels.find(c => c.name === ch.name)?.streaming || false,
            }));
            renderChannels();
        }
    }

    // =========================================================================
    // API Calls
    // =========================================================================

    async function apiCall(endpoint, method = 'GET', body = null) {
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body) {
            options.body = JSON.stringify(body);
        }
        const response = await fetch(endpoint, options);
        return response.json();
    }

    // Channel CRUD
    async function getAllChannels() {
        const result = await apiCall('/api/channels/all');
        if (Array.isArray(result)) {
            channels = result;
            renderChannels();
        }
        return channels;
    }

    async function createChannel(data) {
        const result = await apiCall('/api/channels', 'POST', data);
        await getAllChannels();
        return result;
    }

    async function updateChannel(name, data) {
        const result = await apiCall(`/api/channels/${name}`, 'PUT', data);
        await getAllChannels();
        return result;
    }

    async function deleteChannel(name) {
        if (!confirm(`Delete channel "${name}"? This cannot be undone.`)) {
            return;
        }
        const result = await apiCall(`/api/channels/${name}`, 'DELETE');
        await getAllChannels();
        return result;
    }

    // Audio/Text controls
    async function playAudio(channel, file, volume) {
        return apiCall(`/api/channel/${channel}/play`, 'POST', { file, volume });
    }

    async function stopAudio(channel) {
        return apiCall(`/api/channel/${channel}/stop`, 'POST');
    }

    async function setVolume(channel, level) {
        return apiCall(`/api/channel/${channel}/volume`, 'POST', { level });
    }

    async function showText(channel, text, style, duration) {
        return apiCall(`/api/channel/${channel}/text`, 'POST', { text, style, duration });
    }

    async function clearText(channel) {
        return apiCall(`/api/channel/${channel}/text/clear`, 'POST');
    }

    async function sendTTS(channel, text, showText = true) {
        return apiCall(`/api/channel/${channel}/tts`, 'POST', { text, show_text: showText });
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

    // =========================================================================
    // Modal Functions
    // =========================================================================

    function openCreateChannelModal() {
        editingChannel = null;
        modalTitle.textContent = 'Create Channel';
        channelForm.reset();
        document.getElementById('channel-name').disabled = false;
        document.getElementById('channel-volume').value = 100;
        document.getElementById('volume-value').textContent = '100';
        document.getElementById('channel-color').value = '#e94560';
        document.getElementById('channel-icon').value = '\uD83D\uDD0A';
        channelModal.classList.add('active');
    }

    function openEditChannelModal(channel) {
        editingChannel = channel;
        modalTitle.textContent = 'Edit Channel';
        document.getElementById('channel-name').value = channel.name;
        document.getElementById('channel-name').disabled = true;
        document.getElementById('channel-description').value = channel.description || '';
        document.getElementById('channel-volume').value = Math.round(channel.default_volume * 100);
        document.getElementById('volume-value').textContent = Math.round(channel.default_volume * 100);
        document.getElementById('channel-text-style').value = channel.default_text_style;
        document.getElementById('channel-voice-id').value = channel.elevenlabs_voice_id || '';
        document.getElementById('channel-color').value = channel.color;
        document.getElementById('channel-icon').value = channel.icon;
        document.getElementById('channel-muted').checked = channel.mute_state;
        channelModal.classList.add('active');
    }

    function closeChannelModal() {
        channelModal.classList.remove('active');
        editingChannel = null;
    }

    async function handleChannelFormSubmit(e) {
        e.preventDefault();

        const data = {
            name: document.getElementById('channel-name').value,
            description: document.getElementById('channel-description').value || null,
            default_volume: parseInt(document.getElementById('channel-volume').value) / 100,
            default_text_style: document.getElementById('channel-text-style').value,
            elevenlabs_voice_id: document.getElementById('channel-voice-id').value || null,
            color: document.getElementById('channel-color').value,
            icon: document.getElementById('channel-icon').value,
            mute_state: document.getElementById('channel-muted').checked,
        };

        try {
            if (editingChannel) {
                await updateChannel(editingChannel.name, data);
            } else {
                await createChannel(data);
            }
            closeChannelModal();
        } catch (error) {
            console.error('Error saving channel:', error);
            alert('Error saving channel. Check console for details.');
        }
    }

    // =========================================================================
    // Rendering
    // =========================================================================

    function renderChannels() {
        if (channels.length === 0) {
            channelsContainer.innerHTML = `
                <div class="no-channels">
                    <p>No channels configured yet.</p>
                    <p>Click "Create Channel" to add one.</p>
                </div>
            `;
            return;
        }

        channelsContainer.innerHTML = channels.map(ch => renderChannelCard(ch)).join('');

        // Attach event listeners
        channels.forEach(ch => {
            attachChannelEvents(ch.name);
        });
    }

    function renderChannelCard(channel) {
        let statusClass = '';
        let statusText = 'offline';
        if (!channel.connected) {
            statusClass = '';
            statusText = 'offline';
        } else if (channel.streaming) {
            statusClass = 'streaming';
            statusText = 'streaming';
        } else if (channel.playing) {
            statusClass = 'playing';
            statusText = 'playing';
        } else {
            statusText = 'ready';
        }

        const connectedClass = channel.connected ? '' : 'disconnected';
        const voiceIndicator = channel.elevenlabs_voice_id
            ? '<span class="voice-indicator">TTS</span>'
            : '';

        // TTS channels get simplified controls - just text input and generate button
        // Non-TTS channels get audio file controls and separate text display controls
        const channelControls = channel.elevenlabs_voice_id ? `
            <div class="channel-controls">
                <div class="control-row">
                    <input type="text" placeholder="Text to generate..." id="tts-${channel.name}">
                    <button onclick="window.dashboardSendTTS('${channel.name}')">Generate</button>
                </div>
            </div>
        ` : `
            <div class="channel-controls">
                <div class="control-row">
                    <input type="text" placeholder="audio-file.mp3" id="audio-${channel.name}">
                    <button onclick="window.dashboardPlayAudio('${channel.name}')">Play</button>
                    <button class="secondary" onclick="window.dashboardStopAudio('${channel.name}')">Stop</button>
                </div>
                <div class="control-row">
                    <label style="font-size: 0.75rem; color: var(--text-secondary);">Volume</label>
                    <input type="range" min="0" max="100" value="${Math.round(channel.default_volume * 100)}" id="volume-${channel.name}"
                           onchange="window.dashboardSetVolume('${channel.name}', this.value)">
                </div>
                <div class="text-controls">
                    <div class="control-row">
                        <input type="text" placeholder="Text to display" id="text-${channel.name}">
                        <select id="style-${channel.name}">
                            <option value="typewriter" ${channel.default_text_style === 'typewriter' ? 'selected' : ''}>Typewriter</option>
                            <option value="fade" ${channel.default_text_style === 'fade' ? 'selected' : ''}>Fade</option>
                            <option value="slide" ${channel.default_text_style === 'slide' ? 'selected' : ''}>Slide</option>
                            <option value="bounce" ${channel.default_text_style === 'bounce' ? 'selected' : ''}>Bounce</option>
                            <option value="wave" ${channel.default_text_style === 'wave' ? 'selected' : ''}>Wave</option>
                        </select>
                    </div>
                    <div class="control-row">
                        <button onclick="window.dashboardShowText('${channel.name}')">Show Text</button>
                        <button class="secondary" onclick="window.dashboardClearText('${channel.name}')">Clear</button>
                    </div>
                </div>
            </div>
        `;

        return `
            <div class="channel-card ${connectedClass}" data-channel="${channel.name}" style="border-left-color: ${channel.color}">
                <div class="channel-header">
                    <div class="channel-name">
                        <span class="channel-icon">${channel.icon}</span>
                        ${channel.name}
                        ${voiceIndicator}
                    </div>
                    <span class="channel-status ${statusClass}">${statusText}</span>
                </div>
                ${channel.description ? `<p class="channel-description">${channel.description}</p>` : ''}
                ${channelControls}
                <div class="channel-actions">
                    <button onclick="window.editChannel('${channel.name}')">Edit</button>
                    <button class="secondary" onclick="window.deleteChannel('${channel.name}')">Delete</button>
                </div>
            </div>
        `;
    }

    function attachChannelEvents(channelName) {
        // Audio file input - play on enter
        const audioInput = document.getElementById(`audio-${channelName}`);
        if (audioInput) {
            audioInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    window.dashboardPlayAudio(channelName);
                }
            });
        }

        // Text input - show on enter
        const textInput = document.getElementById(`text-${channelName}`);
        if (textInput) {
            textInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    window.dashboardShowText(channelName);
                }
            });
        }

        // TTS input - speak on enter
        const ttsInput = document.getElementById(`tts-${channelName}`);
        if (ttsInput) {
            ttsInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    window.dashboardSendTTS(channelName);
                }
            });
        }
    }

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

    // =========================================================================
    // Global Functions (for onclick handlers)
    // =========================================================================

    window.openCreateChannelModal = openCreateChannelModal;
    window.closeChannelModal = closeChannelModal;

    window.editChannel = function(channelName) {
        const channel = channels.find(c => c.name === channelName);
        if (channel) {
            openEditChannelModal(channel);
        }
    };

    window.deleteChannel = deleteChannel;

    window.dashboardPlayAudio = async function(channel) {
        const input = document.getElementById(`audio-${channel}`);
        const volumeInput = document.getElementById(`volume-${channel}`);
        if (input && input.value) {
            const volume = volumeInput ? parseInt(volumeInput.value) / 100 : 1;
            await playAudio(channel, input.value, volume);
            loadHistory();
        }
    };

    window.dashboardStopAudio = async function(channel) {
        await stopAudio(channel);
    };

    window.dashboardSetVolume = async function(channel, value) {
        const level = parseInt(value) / 100;
        await setVolume(channel, level);
    };

    window.dashboardShowText = async function(channel) {
        const textInput = document.getElementById(`text-${channel}`);
        const styleSelect = document.getElementById(`style-${channel}`);
        if (textInput && textInput.value) {
            const style = styleSelect ? styleSelect.value : 'typewriter';
            await showText(channel, textInput.value, style, 3000);
            loadHistory();
        }
    };

    window.dashboardClearText = async function(channel) {
        await clearText(channel);
    };

    window.dashboardSendTTS = async function(channel) {
        const ttsInput = document.getElementById(`tts-${channel}`);
        if (ttsInput && ttsInput.value) {
            try {
                await sendTTS(channel, ttsInput.value, true);
                loadHistory();
                ttsInput.value = '';
            } catch (error) {
                console.error('TTS error:', error);
                alert('TTS failed. Check if ELEVENLABS_API_KEY is set.');
            }
        }
    };

    // =========================================================================
    // Initialize
    // =========================================================================

    // Form submission
    if (channelForm) {
        channelForm.addEventListener('submit', handleChannelFormSubmit);
    }

    // Close modal on background click
    if (channelModal) {
        channelModal.addEventListener('click', (e) => {
            if (e.target === channelModal) {
                closeChannelModal();
            }
        });
    }

    connect();
    getAllChannels();
    loadPresets();
    loadHistory();

    // Refresh history periodically
    setInterval(loadHistory, 10000);
})();
