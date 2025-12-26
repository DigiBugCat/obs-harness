/**
 * Santa Timmy Dashboard JavaScript
 * Handles WebSocket connection, session status, and configuration management.
 */

// HTML escape helper to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

class SantaDashboard {
    constructor() {
        this.ws = null;
        this.connected = false;
        this.eventsubConnected = false;
        this.sessionActive = false;

        // DOM Elements
        this.wsStatus = document.getElementById('wsStatus');
        this.wsStatusText = document.getElementById('wsStatusText');
        this.eventsubStatus = document.getElementById('eventsubStatus');
        this.eventsubStatusText = document.getElementById('eventsubStatusText');

        this.sessionStatusEl = document.getElementById('sessionStatus');
        this.sessionState = document.getElementById('sessionState');
        this.sessionVisitor = document.getElementById('sessionVisitor');
        this.sessionWish = document.getElementById('sessionWish');
        this.sessionFollowups = document.getElementById('sessionFollowups');

        this.messageInput = document.getElementById('messageInput');
        this.sendMessageBtn = document.getElementById('sendMessageBtn');
        this.grantBtn = document.getElementById('grantBtn');
        this.denyBtn = document.getElementById('denyBtn');
        this.holdToggle = document.getElementById('holdToggle');
        this.holdLabel = document.getElementById('holdLabel');
        this.cancelBtn = document.getElementById('cancelBtn');
        this.conversationArea = document.getElementById('conversationArea');
        this.pastSessionsArea = document.getElementById('pastSessionsArea');
        this.refreshSessionsBtn = document.getElementById('refreshSessionsBtn');
        this.clearSessionsBtn = document.getElementById('clearSessionsBtn');

        // Connection banner
        this.connectionBanner = document.getElementById('connectionBanner');
        this.overallStatusIcon = document.getElementById('overallStatusIcon');
        this.overallStatusText = document.getElementById('overallStatusText');

        this.enabledToggle = document.getElementById('enabledToggle');
        this.characterName = document.getElementById('characterName');
        this.rewardId = document.getElementById('rewardId');
        this.chatVoteSeconds = document.getElementById('chatVoteSeconds');
        this.maxFollowups = document.getElementById('maxFollowups');
        this.responseTimeout = document.getElementById('responseTimeout');
        this.debounceSeconds = document.getElementById('debounceSeconds');
        this.saveConfigBtn = document.getElementById('saveConfigBtn');

        this.logArea = document.getElementById('logArea');
        this.refreshRewardsDropdownBtn = document.getElementById('refreshRewardsDropdownBtn');
        this.createRewardBtn = document.getElementById('createRewardBtn');

        // Director speak
        this.directorInput = document.getElementById('directorInput');
        this.speakDirectBtn = document.getElementById('speakDirectBtn');

        // System prompt
        this.systemPrompt = document.getElementById('systemPrompt');
        this.savePromptBtn = document.getElementById('savePromptBtn');
        this.resetPromptBtn = document.getElementById('resetPromptBtn');

        // Quick actions
        this.resetSantaBtn = document.getElementById('resetSantaBtn');
        this.clearMemoryBtn = document.getElementById('clearMemoryBtn');

        this.init();
    }

    init() {
        this.connectWebSocket();
        this.loadConfig();
        this.loadEventSubStatus();
        this.loadCharacter();
        this.loadPastSessions();
        this.attachEventListeners();

        // Poll EventSub status every 5 seconds to keep banner updated
        setInterval(() => this.loadEventSubStatus(), 5000);
    }

    // -------------------------------------------------------------------------
    // WebSocket Connection
    // -------------------------------------------------------------------------

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/santa`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.connected = true;
            this.wsStatus.classList.add('connected');
            this.wsStatusText.textContent = 'Dashboard';
            this.log('WebSocket connected');
            this.updateConnectionBanner();
        };

        this.ws.onclose = () => {
            this.connected = false;
            this.wsStatus.classList.remove('connected');
            this.wsStatusText.textContent = 'Dashboard';
            this.log('WebSocket disconnected, reconnecting...');
            this.updateConnectionBanner();
            setTimeout(() => this.connectWebSocket(), 3000);
        };

        this.ws.onerror = (error) => {
            this.log('WebSocket error');
            console.error('WebSocket error:', error);
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };
    }

    handleMessage(data) {
        switch (data.type) {
            case 'santa_status':
                this.updateSessionStatus(data.status);
                break;
            case 'ping':
                this.ws.send(JSON.stringify({ event: 'pong' }));
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }

    // -------------------------------------------------------------------------
    // Session Status
    // -------------------------------------------------------------------------

    updateSessionStatus(status) {
        this.sessionActive = status.active;
        this.sessionHeld = status.held || false;

        // Update state badge
        const state = status.state || 'idle';
        this.sessionState.textContent = state.replace('_', ' ') + (this.sessionHeld ? ' (HELD)' : '');
        this.sessionState.className = `state-badge ${state}`;

        // Update session info
        this.sessionVisitor.textContent = status.redeemer_display_name || '-';
        this.sessionWish.textContent = status.wish_text || '-';
        this.sessionFollowups.textContent = status.followup_count || '0';

        // Update status container
        if (status.active) {
            this.sessionStatusEl.classList.remove('idle');
            this.sessionStatusEl.classList.add('active');
        } else {
            this.sessionStatusEl.classList.remove('active');
            this.sessionStatusEl.classList.add('idle');
        }

        // Update hold toggle
        this.holdToggle.checked = this.sessionHeld;
        this.holdLabel.textContent = this.sessionHeld ? 'On Hold' : 'Hold';

        // Update conversation display
        this.updateConversation(status.conversation || []);

        // Update button states
        this.updateButtonStates();

        if (status.state && status.state !== 'idle') {
            this.log(`Session state: ${state}`);
        }
    }

    updateConversation(conversation) {
        const emptyDiv = this.conversationArea.querySelector('#conversation-empty');

        if (!conversation || conversation.length === 0) {
            if (emptyDiv) emptyDiv.style.display = 'block';
            this.conversationArea.querySelectorAll('.chat-bubble').forEach(el => el.remove());
            return;
        }

        if (emptyDiv) emptyDiv.style.display = 'none';

        const html = conversation.map(msg => {
            const isUser = msg.role === 'user';
            const label = isUser ? '👤 CHILD' : '🎅 SANTA';
            let content = msg.content;

            // Try to parse assistant JSON responses
            if (msg.role === 'assistant') {
                try {
                    const parsed = JSON.parse(content);
                    content = parsed.speech || content;
                } catch (e) {
                    // Not JSON, use as-is
                }
            }

            return `<div class="chat-bubble ${msg.role}">
                <div class="chat-bubble-label">${label}</div>
                <div class="chat-bubble-content">${escapeHtml(content)}</div>
            </div>`;
        }).join('');

        // Keep empty div, replace only bubbles
        this.conversationArea.querySelectorAll('.chat-bubble').forEach(el => el.remove());
        this.conversationArea.insertAdjacentHTML('beforeend', html);
        this.conversationArea.scrollTop = this.conversationArea.scrollHeight;
    }

    async loadPastSessions() {
        try {
            const response = await fetch('/api/santa/sessions?limit=10');
            const data = await response.json();

            if (!data.sessions || data.sessions.length === 0) {
                this.pastSessionsArea.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 2rem;">No past sessions</div>';
                return;
            }

            const html = data.sessions.map(session => {
                const outcomeClass = session.outcome || 'unknown';
                const outcomeLabel = session.outcome ? session.outcome.toUpperCase() : 'IN PROGRESS';
                const date = session.started_at ? new Date(session.started_at).toLocaleString() : 'Unknown';

                // Render conversation bubbles
                let convoHtml = '';
                if (session.conversation && session.conversation.length > 0) {
                    convoHtml = session.conversation.map(msg => {
                        const isUser = msg.role === 'user';
                        const label = isUser ? '👤 CHILD' : '🎅 SANTA';
                        let content = msg.content;

                        if (msg.role === 'assistant') {
                            try {
                                const parsed = JSON.parse(content);
                                content = parsed.speech || content;
                            } catch (e) {}
                        }

                        return `<div class="chat-bubble ${msg.role}">
                            <div class="chat-bubble-label">${label}</div>
                            <div class="chat-bubble-content">${escapeHtml(content)}</div>
                        </div>`;
                    }).join('');
                } else {
                    convoHtml = '<div style="color: var(--text-secondary); font-size: 0.8rem;">No conversation recorded</div>';
                }

                return `<div class="session-card">
                    <div class="session-card-header">
                        <div>
                            <strong>${escapeHtml(session.redeemer_display_name)}</strong>
                            <span style="color: var(--text-secondary); font-size: 0.75rem; margin-left: 0.5rem;">${date}</span>
                        </div>
                        <span class="session-outcome ${outcomeClass}">${outcomeLabel}</span>
                    </div>
                    <div style="color: var(--text-secondary); font-size: 0.8rem; margin-bottom: 0.5rem;">
                        Wish: "${escapeHtml(session.wish_text || 'No wish')}"
                    </div>
                    <details>
                        <summary style="cursor: pointer; font-size: 0.8rem; color: var(--text-secondary);">Show conversation (${session.conversation?.length || 0} messages)</summary>
                        <div style="margin-top: 0.5rem; padding: 0.5rem; background: var(--bg-primary); border-radius: 4px; max-height: 200px; overflow-y: auto;">
                            ${convoHtml}
                        </div>
                    </details>
                </div>`;
            }).join('');

            this.pastSessionsArea.innerHTML = html;
        } catch (e) {
            this.pastSessionsArea.innerHTML = '<div style="color: var(--text-secondary);">Failed to load past sessions</div>';
            console.error('Failed to load past sessions:', e);
        }
    }

    updateButtonStates() {
        const active = this.sessionActive;
        this.sendMessageBtn.disabled = !active;
        this.grantBtn.disabled = !active;
        this.denyBtn.disabled = !active;
        this.cancelBtn.disabled = !active;
    }

    // -------------------------------------------------------------------------
    // API Calls
    // -------------------------------------------------------------------------

    async loadConfig() {
        try {
            const response = await fetch('/api/santa/config');
            const config = await response.json();

            this.enabledToggle.checked = config.enabled;
            this.characterName.value = config.character_name;
            this.configuredRewardId = config.reward_id || '';  // Store for later
            this.rewardId.value = this.configuredRewardId;
            this.chatVoteSeconds.value = config.chat_vote_seconds;
            this.maxFollowups.value = config.max_followups;
            this.responseTimeout.value = config.response_timeout_seconds;
            this.debounceSeconds.value = config.debounce_seconds;

            this.log('Configuration loaded');
        } catch (e) {
            this.log('Failed to load config: ' + e.message);
        }
    }

    async saveConfig() {
        try {
            const config = {
                enabled: this.enabledToggle.checked,
                reward_id: this.rewardId.value || null,
                chat_vote_seconds: parseInt(this.chatVoteSeconds.value),
                max_followups: parseInt(this.maxFollowups.value),
                response_timeout_seconds: parseInt(this.responseTimeout.value),
                debounce_seconds: parseInt(this.debounceSeconds.value),
            };

            const response = await fetch('/api/santa/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
            });

            if (response.ok) {
                this.log('Configuration saved');
            } else {
                const error = await response.json();
                this.log('Failed to save config: ' + error.detail);
            }
        } catch (e) {
            this.log('Failed to save config: ' + e.message);
        }
    }

    async loadEventSubStatus() {
        try {
            const response = await fetch('/api/santa/eventsub/status');
            const status = await response.json();

            this.eventsubConnected = status.connected;

            if (status.connected) {
                this.eventsubStatus.classList.add('connected');
                this.eventsubStatusText.textContent = 'EventSub';
                // Auto-load rewards when connected
                this.loadRewards();
            } else {
                this.eventsubStatus.classList.remove('connected');
                this.eventsubStatusText.textContent = 'EventSub';
            }

            this.updateConnectionBanner();
        } catch (e) {
            this.eventsubConnected = false;
            this.updateConnectionBanner();
        }
    }

    updateConnectionBanner() {
        const wsOk = this.connected;
        const eventsubOk = this.eventsubConnected;
        const allConnected = wsOk && eventsubOk;
        const noneConnected = !wsOk && !eventsubOk;

        // Update banner class
        this.connectionBanner.classList.remove('connected', 'error');
        if (allConnected) {
            this.connectionBanner.classList.add('connected');
            this.overallStatusIcon.textContent = '🎅';
            this.overallStatusText.textContent = 'Santa Ready';
        } else if (noneConnected) {
            this.connectionBanner.classList.add('error');
            this.overallStatusIcon.textContent = '❌';
            this.overallStatusText.textContent = 'Disconnected';
        } else {
            // Partial connection
            this.overallStatusIcon.textContent = '⚠️';
            if (!eventsubOk) {
                this.overallStatusText.textContent = 'EventSub not connected - use Reset Santa';
            } else {
                this.overallStatusText.textContent = 'Dashboard reconnecting...';
            }
        }
    }

    async loadRewards() {
        try {
            const response = await fetch('/api/santa/rewards');
            const data = await response.json();

            // Store current selection (prefer configured value on first load)
            const currentValue = this.rewardId.value || this.configuredRewardId || '';

            if (data.rewards && data.rewards.length > 0) {
                // Update dropdown
                this.rewardId.innerHTML = '<option value="">All rewards</option>' +
                    data.rewards.map(r =>
                        `<option value="${r.id}">${escapeHtml(r.title)} (${r.cost} pts)${r.is_paused ? ' [PAUSED]' : ''}</option>`
                    ).join('');

                // Restore selection
                this.rewardId.value = currentValue;

                this.log(`Loaded ${data.rewards.length} rewards`);
            } else {
                this.rewardId.innerHTML = '<option value="">All rewards</option>';
                this.log('No rewards found');
            }
        } catch (e) {
            this.log('Failed to load rewards: ' + e.message);
        }
    }

    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message) return;

        try {
            const response = await fetch('/api/santa/session/message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message }),
            });

            if (response.ok) {
                this.log('Message sent: ' + message);
                this.messageInput.value = '';
            } else {
                const error = await response.json();
                this.log('Failed to send message: ' + error.detail);
            }
        } catch (e) {
            this.log('Failed to send message: ' + e.message);
        }
    }

    async forceVerdict(verdict) {
        try {
            const response = await fetch('/api/santa/session/verdict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ verdict }),
            });

            if (response.ok) {
                this.log('Verdict forced: ' + verdict);
            } else {
                const error = await response.json();
                this.log('Failed to force verdict: ' + error.detail);
            }
        } catch (e) {
            this.log('Failed to force verdict: ' + e.message);
        }
    }

    async cancelSession() {
        try {
            const response = await fetch('/api/santa/session/cancel', { method: 'POST' });

            if (response.ok) {
                this.log('Session cancelled');
            } else {
                const error = await response.json();
                this.log('Failed to cancel session: ' + error.detail);
            }
        } catch (e) {
            this.log('Failed to cancel session: ' + e.message);
        }
    }

    async toggleHold() {
        try {
            const response = await fetch('/api/santa/session/hold', { method: 'POST' });
            const result = await response.json();

            if (response.ok) {
                this.log(result.held ? '⏸ Session on hold' : '▶ Session resumed');
            } else {
                this.log('Failed to toggle hold: ' + result.detail);
            }
        } catch (e) {
            this.log('Failed to toggle hold: ' + e.message);
        }
    }

    // -------------------------------------------------------------------------
    // Character / System Prompt
    // -------------------------------------------------------------------------

    async loadCharacter() {
        try {
            const response = await fetch('/api/characters/santa_timmy');
            if (response.ok) {
                const char = await response.json();
                this.systemPrompt.value = char.system_prompt || '';
                this.log('Character settings loaded');
            }
        } catch (e) {
            this.log('Failed to load character: ' + e.message);
        }
    }

    async saveSystemPrompt() {
        try {
            const response = await fetch('/api/characters/santa_timmy', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    system_prompt: this.systemPrompt.value
                }),
            });

            if (response.ok) {
                this.log('System prompt saved');
            } else {
                const error = await response.json();
                this.log('Failed to save prompt: ' + error.detail);
            }
        } catch (e) {
            this.log('Failed to save prompt: ' + e.message);
        }
    }

    async resetSystemPrompt() {
        // Default Santa prompt
        const defaultPrompt = `You are Timmy, a jolly mall penguin Santa with magical wish-granting powers!

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

You remember everything from this stream. Reference past visitors, chat's previous judgments, wishes granted or denied. Chat is your elf council.`;

        this.systemPrompt.value = defaultPrompt;
        this.log('Reset to default prompt (not saved yet)');
    }

    async speakDirect() {
        const text = this.directorInput.value.trim();
        if (!text) return;

        try {
            this.speakDirectBtn.disabled = true;
            this.log('Mall Director interrupting: ' + text);

            // Send through Santa's interrupt endpoint (uses speech lock)
            const message = `[MALL DIRECTOR INTERRUPTION]: ${text}`;

            const response = await fetch('/api/santa/interrupt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message }),
            });

            if (response.ok) {
                this.directorInput.value = '';
                this.log('Director message sent to Santa');
            } else {
                const error = await response.json();
                this.log('Failed to send: ' + error.detail);
            }
        } catch (e) {
            this.log('Failed to send: ' + e.message);
        } finally {
            this.speakDirectBtn.disabled = false;
        }
    }

    async resetSanta() {
        if (!confirm('Reset Santa completely? This will clear sessions, memory, and restart EventSub.')) {
            return;
        }

        try {
            this.resetSantaBtn.disabled = true;
            this.log('🔄 Resetting Santa...');

            const response = await fetch('/api/santa/reset', { method: 'POST' });
            const result = await response.json();

            if (response.ok) {
                this.log('✅ Reset complete: ' + result.results.join(', '));
                // Refresh everything
                this.loadEventSubStatus();
                this.loadPastSessions();
            } else {
                this.log('Failed to reset: ' + result.detail);
            }
        } catch (e) {
            this.log('Failed to reset: ' + e.message);
        } finally {
            this.resetSantaBtn.disabled = false;
        }
    }

    async clearMemory() {
        if (!confirm('Clear Santa Timmy\'s memory? This will forget all past conversations.')) {
            return;
        }

        try {
            this.clearMemoryBtn.disabled = true;
            const response = await fetch('/api/characters/santa_timmy/memory', {
                method: 'DELETE',
            });

            if (response.ok) {
                this.log('🧹 Santa\'s memory cleared');
            } else {
                const error = await response.json();
                this.log('Failed to clear memory: ' + error.detail);
            }
        } catch (e) {
            this.log('Failed to clear memory: ' + e.message);
        } finally {
            this.clearMemoryBtn.disabled = false;
        }
    }

    async clearSessions() {
        if (!confirm('Clear ALL past Santa sessions? This will delete session history but NOT Santa\'s memory.')) {
            return;
        }

        try {
            this.clearSessionsBtn.disabled = true;
            const response = await fetch('/api/santa/sessions', {
                method: 'DELETE',
            });

            if (response.ok) {
                this.log('🗑️ All sessions cleared');
                this.loadPastSessions();
            } else {
                const error = await response.json();
                this.log('Failed to clear sessions: ' + error.detail);
            }
        } catch (e) {
            this.log('Failed to clear sessions: ' + e.message);
        } finally {
            this.clearSessionsBtn.disabled = false;
        }
    }

    async createReward() {
        const title = prompt('Reward title:', 'Talk to Santa');
        if (!title) return;

        const costStr = prompt('Cost in channel points:', '100');
        if (!costStr) return;

        const cost = parseInt(costStr);
        if (isNaN(cost) || cost < 1) {
            this.log('Invalid cost');
            return;
        }

        try {
            this.createRewardBtn.disabled = true;
            this.log('Creating reward...');

            const response = await fetch('/api/santa/reward/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title,
                    cost,
                    prompt: 'Tell Santa your Christmas wish!',
                }),
            });

            if (response.ok) {
                const result = await response.json();
                this.log(`✅ Created reward: ${result.reward.title} (${result.reward.cost} pts)`);
                // Refresh rewards and select the new one
                await this.loadRewards();
                this.rewardId.value = result.reward.id;
                // Save config with new reward
                await this.saveConfig();
            } else {
                const error = await response.json();
                this.log('Failed to create reward: ' + error.detail);
            }
        } catch (e) {
            this.log('Failed to create reward: ' + e.message);
        } finally {
            this.createRewardBtn.disabled = false;
        }
    }

    // -------------------------------------------------------------------------
    // Event Listeners
    // -------------------------------------------------------------------------

    attachEventListeners() {
        this.saveConfigBtn.addEventListener('click', () => this.saveConfig());
        this.refreshRewardsDropdownBtn.addEventListener('click', () => this.loadRewards());
        this.createRewardBtn.addEventListener('click', () => this.createReward());

        this.sendMessageBtn.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !this.sendMessageBtn.disabled) {
                this.sendMessage();
            }
        });

        this.grantBtn.addEventListener('click', () => this.forceVerdict('grant'));
        this.denyBtn.addEventListener('click', () => this.forceVerdict('deny'));
        this.holdToggle.addEventListener('change', () => this.toggleHold());
        this.cancelBtn.addEventListener('click', () => this.cancelSession());
        this.refreshSessionsBtn.addEventListener('click', () => this.loadPastSessions());
        this.clearSessionsBtn.addEventListener('click', () => this.clearSessions());

        // Director speak
        this.speakDirectBtn.addEventListener('click', () => this.speakDirect());
        this.directorInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.speakDirect();
            }
        });

        // System prompt
        this.savePromptBtn.addEventListener('click', () => this.saveSystemPrompt());
        this.resetPromptBtn.addEventListener('click', () => this.resetSystemPrompt());

        // Quick actions
        this.resetSantaBtn.addEventListener('click', () => this.resetSanta());
        this.clearMemoryBtn.addEventListener('click', () => this.clearMemory());

        // Enabled toggle - immediate action
        this.enabledToggle.addEventListener('change', () => this.toggleEnabled());
    }

    async toggleEnabled() {
        try {
            const response = await fetch('/api/santa/toggle', { method: 'POST' });
            const result = await response.json();

            if (response.ok) {
                // Update checkbox to match server state
                this.enabledToggle.checked = result.enabled;
                this.log(result.enabled ? '✅ Santa enabled' : '⏸️ Santa disabled');
                // Refresh rewards to show updated status
                this.loadRewards();
            } else {
                // Revert checkbox on error
                this.enabledToggle.checked = !this.enabledToggle.checked;
                this.log('Failed to toggle: ' + result.detail);
            }
        } catch (e) {
            // Revert checkbox on error
            this.enabledToggle.checked = !this.enabledToggle.checked;
            this.log('Failed to toggle: ' + e.message);
        }
    }

    // -------------------------------------------------------------------------
    // Logging
    // -------------------------------------------------------------------------

    log(message) {
        const time = new Date().toLocaleTimeString();
        const entry = document.createElement('div');
        entry.className = 'log-entry';
        entry.innerHTML = `<span class="log-time">[${time}]</span> ${message}`;
        this.logArea.appendChild(entry);
        this.logArea.scrollTop = this.logArea.scrollHeight;

        // Keep only last 100 entries
        while (this.logArea.children.length > 100) {
            this.logArea.removeChild(this.logArea.firstChild);
        }
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.santaDashboard = new SantaDashboard();
});
