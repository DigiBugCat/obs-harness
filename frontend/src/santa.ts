/**
 * Santa Timmy Dashboard JavaScript
 * Handles WebSocket connection, session status, and configuration management.
 */

// HTML escape helper to prevent XSS
function escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Type definitions for Santa dashboard
interface SessionStatus {
    active: boolean;
    held?: boolean;
    state?: string;
    redeemer_display_name?: string;
    wish_text?: string;
    followup_count?: number;
    conversation?: Array<{ role: string; content: string }>;
}

interface SantaSession {
    id: number;
    redeemer_display_name: string;
    wish_text?: string;
    outcome?: string;
    started_at?: string;
    ended_at?: string;
    conversation?: Array<{ role: string; content: string }>;
}

interface SantaConfig {
    enabled: boolean;
    character_name: string;
    reward_id?: string;
    chat_vote_seconds?: number;
    max_followups?: number;
    response_timeout?: number;
    debounce_seconds?: number;
}

interface TwitchReward {
    id: string;
    title: string;
    cost: number;
    is_enabled: boolean;
    is_paused: boolean;
}

interface AccessibleChannel {
    tenant_id: string;
    username: string;
    is_own: boolean;
}


class SantaDashboard {
    // WebSocket state
    private ws: WebSocket | null = null;
    private connected: boolean = false;
    private eventsubConnected: boolean = false;
    private sessionActive: boolean = false;
    private sessionHeld: boolean = false;
    private configuredRewardId: string | null = null;

    // Channel switching state (for moderator access)
    private isOwner: boolean = true;
    private currentChannel: string | null = null;
    private accessibleChannels: AccessibleChannel[] = [];

    // DOM Elements - Status indicators
    private wsStatus: HTMLElement | null;
    private wsStatusText: HTMLElement | null;
    private eventsubStatus: HTMLElement | null;
    private eventsubStatusText: HTMLElement | null;

    // Session status elements
    private sessionStatusEl: HTMLElement | null;
    private sessionState: HTMLElement | null;
    private sessionVisitor: HTMLElement | null;
    private sessionWish: HTMLElement | null;
    private sessionFollowups: HTMLElement | null;

    // Control elements
    private messageInput: HTMLTextAreaElement | null;
    private sendMessageBtn: HTMLButtonElement | null;
    private grantBtn: HTMLButtonElement | null;
    private denyBtn: HTMLButtonElement | null;
    private holdToggle: HTMLInputElement | null;
    private holdLabel: HTMLElement | null;
    private cancelBtn: HTMLButtonElement | null;
    private conversationArea: HTMLElement | null;
    private pastSessionsArea: HTMLElement | null;
    private refreshSessionsBtn: HTMLButtonElement | null;
    private clearSessionsBtn: HTMLButtonElement | null;

    // Connection banner
    private connectionBanner: HTMLElement | null;
    private overallStatusIcon: HTMLElement | null;
    private overallStatusText: HTMLElement | null;

    // Config elements
    private enabledToggle: HTMLInputElement | null;
    private characterName: HTMLInputElement | null;
    private rewardId: HTMLSelectElement | null;
    private chatVoteSeconds: HTMLInputElement | null;
    private maxFollowups: HTMLInputElement | null;
    private responseTimeout: HTMLInputElement | null;
    private debounceSeconds: HTMLInputElement | null;
    private saveConfigBtn: HTMLButtonElement | null;

    // Log and reward elements
    private logArea: HTMLElement | null;
    private refreshRewardsDropdownBtn: HTMLButtonElement | null;
    private createRewardBtn: HTMLButtonElement | null;

    // Director speak elements
    private directorInput: HTMLTextAreaElement | null;
    private speakDirectBtn: HTMLButtonElement | null;

    // System prompt elements
    private systemPrompt: HTMLTextAreaElement | null;
    private savePromptBtn: HTMLButtonElement | null;
    private resetPromptBtn: HTMLButtonElement | null;

    // Quick action buttons
    private resetSantaBtn: HTMLButtonElement | null;
    private clearMemoryBtn: HTMLButtonElement | null;

    // Channel switcher elements (moderator access)
    private channelSwitcher: HTMLElement | null;
    private channelSelect: HTMLSelectElement | null;

    // Owner-only UI elements
    private createRewardContainer: HTMLElement | null;

    constructor() {
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

        this.messageInput = document.getElementById('messageInput') as HTMLTextAreaElement | null;
        this.sendMessageBtn = document.getElementById('sendMessageBtn') as HTMLButtonElement | null;
        this.grantBtn = document.getElementById('grantBtn') as HTMLButtonElement | null;
        this.denyBtn = document.getElementById('denyBtn') as HTMLButtonElement | null;
        this.holdToggle = document.getElementById('holdToggle') as HTMLInputElement | null;
        this.holdLabel = document.getElementById('holdLabel');
        this.cancelBtn = document.getElementById('cancelBtn') as HTMLButtonElement | null;
        this.conversationArea = document.getElementById('conversationArea');
        this.pastSessionsArea = document.getElementById('pastSessionsArea');
        this.refreshSessionsBtn = document.getElementById('refreshSessionsBtn') as HTMLButtonElement | null;
        this.clearSessionsBtn = document.getElementById('clearSessionsBtn') as HTMLButtonElement | null;

        // Connection banner
        this.connectionBanner = document.getElementById('connectionBanner');
        this.overallStatusIcon = document.getElementById('overallStatusIcon');
        this.overallStatusText = document.getElementById('overallStatusText');

        this.enabledToggle = document.getElementById('enabledToggle') as HTMLInputElement | null;
        this.characterName = document.getElementById('characterName') as HTMLInputElement | null;
        this.rewardId = document.getElementById('rewardId') as HTMLSelectElement | null;
        this.chatVoteSeconds = document.getElementById('chatVoteSeconds') as HTMLInputElement | null;
        this.maxFollowups = document.getElementById('maxFollowups') as HTMLInputElement | null;
        this.responseTimeout = document.getElementById('responseTimeout') as HTMLInputElement | null;
        this.debounceSeconds = document.getElementById('debounceSeconds') as HTMLInputElement | null;
        this.saveConfigBtn = document.getElementById('saveConfigBtn') as HTMLButtonElement | null;

        this.logArea = document.getElementById('logArea');
        this.refreshRewardsDropdownBtn = document.getElementById('refreshRewardsDropdownBtn') as HTMLButtonElement | null;
        this.createRewardBtn = document.getElementById('createRewardBtn') as HTMLButtonElement | null;

        // Director speak
        this.directorInput = document.getElementById('directorInput') as HTMLTextAreaElement | null;
        this.speakDirectBtn = document.getElementById('speakDirectBtn') as HTMLButtonElement | null;

        // System prompt
        this.systemPrompt = document.getElementById('systemPrompt') as HTMLTextAreaElement | null;
        this.savePromptBtn = document.getElementById('savePromptBtn') as HTMLButtonElement | null;
        this.resetPromptBtn = document.getElementById('resetPromptBtn') as HTMLButtonElement | null;

        // Quick actions
        this.resetSantaBtn = document.getElementById('resetSantaBtn') as HTMLButtonElement | null;
        this.clearMemoryBtn = document.getElementById('clearMemoryBtn') as HTMLButtonElement | null;

        // Channel switcher (moderator access)
        this.channelSwitcher = document.getElementById('channelSwitcher');
        this.channelSelect = document.getElementById('channelSelect') as HTMLSelectElement | null;

        // Owner-only UI elements
        this.createRewardContainer = document.getElementById('createRewardContainer');

        this.init();
    }

    async init() {
        // Load accessible channels first to determine current channel
        await this.loadAccessibleChannels();

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
        let wsUrl = `${protocol}//${window.location.host}/ws/santa`;

        // Include channel parameter if viewing another channel
        if (this.currentChannel) {
            wsUrl += `?channel=${encodeURIComponent(this.currentChannel)}`;
        }

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.connected = true;
            this.wsStatus?.classList.add('connected');
            if (this.wsStatusText) this.wsStatusText.textContent = 'Dashboard';
            this.log('WebSocket connected');
            this.updateConnectionBanner();
        };

        this.ws.onclose = () => {
            this.connected = false;
            this.wsStatus?.classList.remove('connected');
            if (this.wsStatusText) this.wsStatusText.textContent = 'Dashboard';
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
            } catch (e: unknown) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };
    }

    handleMessage(data: { type: string; status?: SessionStatus }) {
        switch (data.type) {
            case 'santa_status':
                if (data.status) this.updateSessionStatus(data.status);
                break;
            case 'ping':
                this.ws?.send(JSON.stringify({ event: 'pong' }));
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }

    // -------------------------------------------------------------------------
    // Session Status
    // -------------------------------------------------------------------------

    updateSessionStatus(status: SessionStatus) {
        this.sessionActive = status.active;
        this.sessionHeld = status.held || false;

        // Update state badge
        const state = status.state || 'idle';
        if (this.sessionState) {
            this.sessionState.textContent = state.replace('_', ' ') + (this.sessionHeld ? ' (HELD)' : '');
            this.sessionState.className = `state-badge ${state}`;
        }

        // Update session info
        if (this.sessionVisitor) this.sessionVisitor.textContent = status.redeemer_display_name || '-';
        if (this.sessionWish) this.sessionWish.textContent = status.wish_text || '-';
        if (this.sessionFollowups) this.sessionFollowups.textContent = String(status.followup_count || '0');

        // Update status container
        if (status.active) {
            this.sessionStatusEl?.classList.remove('idle');
            this.sessionStatusEl?.classList.add('active');
        } else {
            this.sessionStatusEl?.classList.remove('active');
            this.sessionStatusEl?.classList.add('idle');
        }

        // Update hold toggle
        if (this.holdToggle) this.holdToggle.checked = this.sessionHeld;
        if (this.holdLabel) this.holdLabel.textContent = this.sessionHeld ? 'On Hold' : 'Hold';

        // Update conversation display
        this.updateConversation(status.conversation || []);

        // Update button states
        this.updateButtonStates();

        if (status.state && status.state !== 'idle') {
            this.log(`Session state: ${state}`);
        }
    }

    updateConversation(conversation: Array<{ role: string; content: string }> | null) {
        const emptyDiv = this.conversationArea?.querySelector('#conversation-empty') as HTMLElement | null;

        if (!conversation || conversation.length === 0) {
            if (emptyDiv) emptyDiv.style.display = 'block';
            this.conversationArea?.querySelectorAll('.chat-bubble').forEach(el => el.remove());
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
                } catch (e: unknown) {
                    // Not JSON, use as-is
                }
            }

            return `<div class="chat-bubble ${msg.role}">
                <div class="chat-bubble-label">${label}</div>
                <div class="chat-bubble-content">${escapeHtml(content)}</div>
            </div>`;
        }).join('');

        // Keep empty div, replace only bubbles
        this.conversationArea?.querySelectorAll('.chat-bubble').forEach(el => el.remove());
        this.conversationArea?.insertAdjacentHTML('beforeend', html);
        if (this.conversationArea) this.conversationArea.scrollTop = this.conversationArea.scrollHeight;
    }

    async loadPastSessions() {
        try {
            const response = await fetch(`/api/santa/sessions?limit=10${this.getChannelParam(true)}`);
            const data = await response.json();

            if (!data.sessions || data.sessions.length === 0) {
                this.pastSessionsArea.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 2rem;">No past sessions</div>';
                return;
            }

            const html = data.sessions.map((session: SantaSession) => {
                const outcomeClass = session.outcome || 'unknown';
                const outcomeLabel = session.outcome ? session.outcome.toUpperCase() : 'IN PROGRESS';
                const date = session.started_at ? new Date(session.started_at).toLocaleString() : 'Unknown';

                // Render conversation bubbles
                let convoHtml = '';
                if (session.conversation && session.conversation.length > 0) {
                    convoHtml = session.conversation.map((msg: { role: string; content: string }) => {
                        const isUser = msg.role === 'user';
                        const label = isUser ? '👤 CHILD' : '🎅 SANTA';
                        let content = msg.content;

                        if (msg.role === 'assistant') {
                            try {
                                const parsed = JSON.parse(content);
                                content = parsed.speech || content;
                            } catch (e: unknown) {}
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
        } catch (e: unknown) {
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
    // Channel Switching (Moderator Access)
    // -------------------------------------------------------------------------

    private getCookie(name: string): string | null {
        const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
        return match ? decodeURIComponent(match[2]) : null;
    }

    private setCookie(name: string, value: string, days: number = 30) {
        const expires = new Date(Date.now() + days * 24 * 60 * 60 * 1000).toUTCString();
        document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/`;
    }

    async loadAccessibleChannels() {
        try {
            const response = await fetch('/api/moderators/accessible-channels');
            if (!response.ok) {
                console.error('Failed to load accessible channels');
                return;
            }

            const data = await response.json();
            this.accessibleChannels = data.channels || [];

            // Determine current channel from URL param → cookie → own channel
            const urlParams = new URLSearchParams(window.location.search);
            const urlChannel = urlParams.get('channel');
            const cookieChannel = this.getCookie('effective_channel');

            // Find own channel
            const ownChannel = this.accessibleChannels.find(c => c.is_own);
            const ownChannelId = ownChannel?.tenant_id || null;

            // Determine effective channel
            if (urlChannel && this.accessibleChannels.some(c => c.tenant_id === urlChannel)) {
                this.currentChannel = urlChannel;
            } else if (cookieChannel && this.accessibleChannels.some(c => c.tenant_id === cookieChannel)) {
                this.currentChannel = cookieChannel;
            } else {
                this.currentChannel = ownChannelId;
            }

            // Update isOwner flag
            this.isOwner = this.currentChannel === ownChannelId;

            // Save to cookie
            if (this.currentChannel) {
                this.setCookie('effective_channel', this.currentChannel);
            }

            // Update UI
            this.updateChannelSwitcher();
            this.updateOwnerOnlyUI();
        } catch (e: unknown) {
            console.error('Failed to load accessible channels:', e);
        }
    }

    updateChannelSwitcher() {
        if (!this.channelSwitcher || !this.channelSelect) return;

        // Only show switcher if user has access to multiple channels
        if (this.accessibleChannels.length <= 1) {
            this.channelSwitcher.style.display = 'none';
            return;
        }

        this.channelSwitcher.style.display = 'flex';

        // Populate dropdown
        this.channelSelect.innerHTML = this.accessibleChannels.map(channel => {
            const label = channel.is_own
                ? `${escapeHtml(channel.username)} (You)`
                : escapeHtml(channel.username);
            return `<option value="${channel.tenant_id}" ${channel.tenant_id === this.currentChannel ? 'selected' : ''}>${label}</option>`;
        }).join('');
    }

    switchChannel(channelId: string) {
        if (channelId === this.currentChannel) return;

        // Update cookie and reload page
        this.setCookie('effective_channel', channelId);

        // Update URL without full reload - just update query param
        const url = new URL(window.location.href);
        url.searchParams.set('channel', channelId);
        window.location.href = url.toString();
    }

    updateOwnerOnlyUI() {
        // Show/hide create reward button (owner only)
        if (this.createRewardContainer) {
            this.createRewardContainer.style.display = this.isOwner ? 'block' : 'none';
        }

        // Disable character settings for moderators (these use tenant-scoped endpoints)
        // TODO: Update character routes to support cross-tenant moderator access
        if (this.savePromptBtn) this.savePromptBtn.disabled = !this.isOwner;
        if (this.resetPromptBtn) this.resetPromptBtn.disabled = !this.isOwner;
        if (this.clearMemoryBtn) this.clearMemoryBtn.disabled = !this.isOwner;
        if (this.systemPrompt) this.systemPrompt.disabled = !this.isOwner;
    }

    // -------------------------------------------------------------------------
    // API Calls
    // -------------------------------------------------------------------------

    private getChannelParam(hasExistingParams: boolean = false): string {
        if (!this.currentChannel) return '';
        const prefix = hasExistingParams ? '&' : '?';
        return `${prefix}channel=${encodeURIComponent(this.currentChannel)}`;
    }

    async loadConfig() {
        try {
            const response = await fetch(`/api/santa/config${this.getChannelParam()}`);
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
        } catch (e: unknown) {
            this.log('Failed to load config: ' + (e instanceof Error ? e.message : String(e)));
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

            const response = await fetch(`/api/santa/config${this.getChannelParam()}`, {
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
        } catch (e: unknown) {
            this.log('Failed to save config: ' + (e instanceof Error ? e.message : String(e)));
        }
    }

    async loadEventSubStatus() {
        try {
            const response = await fetch(`/api/santa/eventsub/status${this.getChannelParam()}`);
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
        } catch (e: unknown) {
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
            const response = await fetch(`/api/santa/rewards${this.getChannelParam()}`);
            const data = await response.json();

            // Store current selection (prefer configured value on first load)
            const currentValue = this.rewardId.value || this.configuredRewardId || '';

            if (data.rewards && data.rewards.length > 0) {
                // Update dropdown
                this.rewardId.innerHTML = '<option value="">All rewards</option>' +
                    data.rewards.map((r: TwitchReward) =>
                        `<option value="${r.id}">${escapeHtml(r.title)} (${r.cost} pts)${r.is_paused ? ' [PAUSED]' : ''}</option>`
                    ).join('');

                // Restore selection
                this.rewardId.value = currentValue;

                this.log(`Loaded ${data.rewards.length} rewards`);
            } else {
                this.rewardId.innerHTML = '<option value="">All rewards</option>';
                this.log('No rewards found');
            }
        } catch (e: unknown) {
            this.log('Failed to load rewards: ' + (e instanceof Error ? e.message : String(e)));
        }
    }

    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message) return;

        try {
            const response = await fetch(`/api/santa/session/message${this.getChannelParam()}`, {
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
        } catch (e: unknown) {
            this.log('Failed to send message: ' + (e instanceof Error ? e.message : String(e)));
        }
    }

    async forceVerdict(verdict: string) {
        try {
            const response = await fetch(`/api/santa/session/verdict${this.getChannelParam()}`, {
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
        } catch (e: unknown) {
            this.log('Failed to force verdict: ' + (e instanceof Error ? e.message : String(e)));
        }
    }

    async cancelSession() {
        try {
            const response = await fetch(`/api/santa/session/cancel${this.getChannelParam()}`, { method: 'POST' });

            if (response.ok) {
                this.log('Session cancelled');
            } else {
                const error = await response.json();
                this.log('Failed to cancel session: ' + error.detail);
            }
        } catch (e: unknown) {
            this.log('Failed to cancel session: ' + (e instanceof Error ? e.message : String(e)));
        }
    }

    async toggleHold() {
        try {
            const response = await fetch(`/api/santa/session/hold${this.getChannelParam()}`, { method: 'POST' });
            const result = await response.json();

            if (response.ok) {
                this.log(result.held ? '⏸ Session on hold' : '▶ Session resumed');
            } else {
                this.log('Failed to toggle hold: ' + result.detail);
            }
        } catch (e: unknown) {
            this.log('Failed to toggle hold: ' + (e instanceof Error ? e.message : String(e)));
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
        } catch (e: unknown) {
            this.log('Failed to load character: ' + (e instanceof Error ? e.message : String(e)));
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
        } catch (e: unknown) {
            this.log('Failed to save prompt: ' + (e instanceof Error ? e.message : String(e)));
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

            const response = await fetch(`/api/santa/interrupt${this.getChannelParam()}`, {
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
        } catch (e: unknown) {
            this.log('Failed to send: ' + (e instanceof Error ? e.message : String(e)));
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

            const response = await fetch(`/api/santa/reset${this.getChannelParam()}`, { method: 'POST' });
            const result = await response.json();

            if (response.ok) {
                this.log('✅ Reset complete: ' + result.results.join(', '));
                // Refresh everything
                this.loadEventSubStatus();
                this.loadPastSessions();
            } else {
                this.log('Failed to reset: ' + result.detail);
            }
        } catch (e: unknown) {
            this.log('Failed to reset: ' + (e instanceof Error ? e.message : String(e)));
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
        } catch (e: unknown) {
            this.log('Failed to clear memory: ' + (e instanceof Error ? e.message : String(e)));
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
            const response = await fetch(`/api/santa/sessions${this.getChannelParam()}`, {
                method: 'DELETE',
            });

            if (response.ok) {
                this.log('🗑️ All sessions cleared');
                this.loadPastSessions();
            } else {
                const error = await response.json();
                this.log('Failed to clear sessions: ' + error.detail);
            }
        } catch (e: unknown) {
            this.log('Failed to clear sessions: ' + (e instanceof Error ? e.message : String(e)));
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

            const response = await fetch(`/api/santa/reward/create${this.getChannelParam()}`, {
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
        } catch (e: unknown) {
            this.log('Failed to create reward: ' + (e instanceof Error ? e.message : String(e)));
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

        // Channel switcher
        this.channelSelect?.addEventListener('change', (e) => {
            const select = e.target as HTMLSelectElement;
            this.switchChannel(select.value);
        });
    }

    async toggleEnabled() {
        try {
            const response = await fetch(`/api/santa/toggle${this.getChannelParam()}`, { method: 'POST' });
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
        } catch (e: unknown) {
            // Revert checkbox on error
            this.enabledToggle.checked = !this.enabledToggle.checked;
            this.log('Failed to toggle: ' + (e instanceof Error ? e.message : String(e)));
        }
    }

    // -------------------------------------------------------------------------
    // Logging
    // -------------------------------------------------------------------------

    log(message: string) {
        const time = new Date().toLocaleTimeString();
        const entry = document.createElement('div');
        entry.className = 'log-entry';
        entry.innerHTML = `<span class="log-time">[${time}]</span> ${escapeHtml(message)}`;
        this.logArea.appendChild(entry);
        this.logArea.scrollTop = this.logArea.scrollHeight;

        // Keep only last 100 entries
        while (this.logArea.children.length > 100) {
            this.logArea.removeChild(this.logArea.firstChild);
        }
    }
}

// ES Module export
export { SantaDashboard, escapeHtml };

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    (window as any).santaDashboard = new SantaDashboard();
});
