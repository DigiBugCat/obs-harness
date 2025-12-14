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

    // DOM elements
    const wsStatus = document.getElementById('ws-status');
    const wsStatusText = document.getElementById('ws-status-text');
    const channelsContainer = document.getElementById('channels-container');
    const historyList = document.getElementById('history-list');
    const channelUrl = document.getElementById('channel-url');

    // Set correct channel URL based on current host
    if (channelUrl) {
        channelUrl.textContent = `${window.location.origin}/channel/your-channel-name`;
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
            channels = msg.channels;
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
    // Rendering
    // =========================================================================

    function renderChannels() {
        if (channels.length === 0) {
            channelsContainer.innerHTML = `
                <div class="no-channels">
                    <p>No channels connected yet.</p>
                    <p>Add a Browser Source in OBS with URL:</p>
                    <code>${window.location.origin}/channel/your-channel-name</code>
                </div>
            `;
            return;
        }

        channelsContainer.innerHTML = `
            <div class="channels-grid">
                ${channels.map(ch => renderChannelCard(ch)).join('')}
            </div>
        `;

        // Attach event listeners
        channels.forEach(ch => {
            attachChannelEvents(ch.name);
        });
    }

    function renderChannelCard(channel) {
        let statusClass = '';
        let statusText = 'idle';
        if (channel.streaming) {
            statusClass = 'streaming';
            statusText = 'streaming';
        } else if (channel.playing) {
            statusClass = 'playing';
            statusText = 'playing';
        }

        return `
            <div class="channel-card" data-channel="${channel.name}">
                <div class="channel-header">
                    <div class="channel-name">
                        <div class="status-dot connected"></div>
                        ${channel.name}
                    </div>
                    <span class="channel-status ${statusClass}">${statusText}</span>
                </div>
                <div class="channel-controls">
                    <div class="control-row">
                        <input type="text" placeholder="audio-file.mp3" id="audio-${channel.name}">
                        <button onclick="window.dashboardPlayAudio('${channel.name}')">Play</button>
                        <button class="secondary" onclick="window.dashboardStopAudio('${channel.name}')">Stop</button>
                    </div>
                    <div class="control-row">
                        <label style="font-size: 0.75rem; color: var(--text-secondary);">Volume</label>
                        <input type="range" min="0" max="100" value="100" id="volume-${channel.name}"
                               onchange="window.dashboardSetVolume('${channel.name}', this.value)">
                    </div>
                    <div class="text-controls">
                        <div class="control-row">
                            <input type="text" placeholder="Text to display" id="text-${channel.name}">
                            <select id="style-${channel.name}">
                                <option value="typewriter">Typewriter</option>
                                <option value="fade">Fade</option>
                                <option value="slide">Slide</option>
                                <option value="bounce">Bounce</option>
                                <option value="wave">Wave</option>
                            </select>
                        </div>
                        <div class="control-row">
                            <button onclick="window.dashboardShowText('${channel.name}')">Show Text</button>
                            <button class="secondary" onclick="window.dashboardClearText('${channel.name}')">Clear</button>
                        </div>
                    </div>
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

    // =========================================================================
    // Initialize
    // =========================================================================

    connect();
    loadPresets();
    loadHistory();

    // Refresh history periodically
    setInterval(loadHistory, 10000);
})();
