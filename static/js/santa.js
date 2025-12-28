function r(h) {
  const e = document.createElement("div");
  return e.textContent = h, e.innerHTML;
}
class p {
  constructor() {
    this.ws = null, this.connected = !1, this.eventsubConnected = !1, this.sessionActive = !1, this.wsStatus = document.getElementById("wsStatus"), this.wsStatusText = document.getElementById("wsStatusText"), this.eventsubStatus = document.getElementById("eventsubStatus"), this.eventsubStatusText = document.getElementById("eventsubStatusText"), this.sessionStatusEl = document.getElementById("sessionStatus"), this.sessionState = document.getElementById("sessionState"), this.sessionVisitor = document.getElementById("sessionVisitor"), this.sessionWish = document.getElementById("sessionWish"), this.sessionFollowups = document.getElementById("sessionFollowups"), this.messageInput = document.getElementById("messageInput"), this.sendMessageBtn = document.getElementById("sendMessageBtn"), this.grantBtn = document.getElementById("grantBtn"), this.denyBtn = document.getElementById("denyBtn"), this.holdToggle = document.getElementById("holdToggle"), this.holdLabel = document.getElementById("holdLabel"), this.cancelBtn = document.getElementById("cancelBtn"), this.conversationArea = document.getElementById("conversationArea"), this.pastSessionsArea = document.getElementById("pastSessionsArea"), this.refreshSessionsBtn = document.getElementById("refreshSessionsBtn"), this.clearSessionsBtn = document.getElementById("clearSessionsBtn"), this.connectionBanner = document.getElementById("connectionBanner"), this.overallStatusIcon = document.getElementById("overallStatusIcon"), this.overallStatusText = document.getElementById("overallStatusText"), this.enabledToggle = document.getElementById("enabledToggle"), this.characterName = document.getElementById("characterName"), this.rewardId = document.getElementById("rewardId"), this.chatVoteSeconds = document.getElementById("chatVoteSeconds"), this.maxFollowups = document.getElementById("maxFollowups"), this.responseTimeout = document.getElementById("responseTimeout"), this.debounceSeconds = document.getElementById("debounceSeconds"), this.saveConfigBtn = document.getElementById("saveConfigBtn"), this.logArea = document.getElementById("logArea"), this.refreshRewardsDropdownBtn = document.getElementById("refreshRewardsDropdownBtn"), this.createRewardBtn = document.getElementById("createRewardBtn"), this.directorInput = document.getElementById("directorInput"), this.speakDirectBtn = document.getElementById("speakDirectBtn"), this.systemPrompt = document.getElementById("systemPrompt"), this.savePromptBtn = document.getElementById("savePromptBtn"), this.resetPromptBtn = document.getElementById("resetPromptBtn"), this.resetSantaBtn = document.getElementById("resetSantaBtn"), this.clearMemoryBtn = document.getElementById("clearMemoryBtn"), this.init();
  }
  init() {
    this.connectWebSocket(), this.loadConfig(), this.loadEventSubStatus(), this.loadCharacter(), this.loadPastSessions(), this.attachEventListeners(), setInterval(() => this.loadEventSubStatus(), 5e3);
  }
  // -------------------------------------------------------------------------
  // WebSocket Connection
  // -------------------------------------------------------------------------
  connectWebSocket() {
    const t = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/santa`;
    this.ws = new WebSocket(t), this.ws.onopen = () => {
      this.connected = !0, this.wsStatus.classList.add("connected"), this.wsStatusText.textContent = "Dashboard", this.log("WebSocket connected"), this.updateConnectionBanner();
    }, this.ws.onclose = () => {
      this.connected = !1, this.wsStatus.classList.remove("connected"), this.wsStatusText.textContent = "Dashboard", this.log("WebSocket disconnected, reconnecting..."), this.updateConnectionBanner(), setTimeout(() => this.connectWebSocket(), 3e3);
    }, this.ws.onerror = (n) => {
      this.log("WebSocket error"), console.error("WebSocket error:", n);
    }, this.ws.onmessage = (n) => {
      try {
        const s = JSON.parse(n.data);
        this.handleMessage(s);
      } catch (s) {
        console.error("Failed to parse WebSocket message:", s);
      }
    };
  }
  handleMessage(e) {
    switch (e.type) {
      case "santa_status":
        this.updateSessionStatus(e.status);
        break;
      case "ping":
        this.ws.send(JSON.stringify({ event: "pong" }));
        break;
      default:
        console.log("Unknown message type:", e.type);
    }
  }
  // -------------------------------------------------------------------------
  // Session Status
  // -------------------------------------------------------------------------
  updateSessionStatus(e) {
    this.sessionActive = e.active, this.sessionHeld = e.held || !1;
    const t = e.state || "idle";
    this.sessionState.textContent = t.replace("_", " ") + (this.sessionHeld ? " (HELD)" : ""), this.sessionState.className = `state-badge ${t}`, this.sessionVisitor.textContent = e.redeemer_display_name || "-", this.sessionWish.textContent = e.wish_text || "-", this.sessionFollowups.textContent = e.followup_count || "0", e.active ? (this.sessionStatusEl.classList.remove("idle"), this.sessionStatusEl.classList.add("active")) : (this.sessionStatusEl.classList.remove("active"), this.sessionStatusEl.classList.add("idle")), this.holdToggle.checked = this.sessionHeld, this.holdLabel.textContent = this.sessionHeld ? "On Hold" : "Hold", this.updateConversation(e.conversation || []), this.updateButtonStates(), e.state && e.state !== "idle" && this.log(`Session state: ${t}`);
  }
  updateConversation(e) {
    const t = this.conversationArea.querySelector("#conversation-empty");
    if (!e || e.length === 0) {
      t && (t.style.display = "block"), this.conversationArea.querySelectorAll(".chat-bubble").forEach((s) => s.remove());
      return;
    }
    t && (t.style.display = "none");
    const n = e.map((s) => {
      const d = s.role === "user" ? "👤 CHILD" : "🎅 SANTA";
      let o = s.content;
      if (s.role === "assistant")
        try {
          o = JSON.parse(o).speech || o;
        } catch {
        }
      return `<div class="chat-bubble ${s.role}">
                <div class="chat-bubble-label">${d}</div>
                <div class="chat-bubble-content">${r(o)}</div>
            </div>`;
    }).join("");
    this.conversationArea.querySelectorAll(".chat-bubble").forEach((s) => s.remove()), this.conversationArea.insertAdjacentHTML("beforeend", n), this.conversationArea.scrollTop = this.conversationArea.scrollHeight;
  }
  async loadPastSessions() {
    try {
      const t = await (await fetch("/api/santa/sessions?limit=10")).json();
      if (!t.sessions || t.sessions.length === 0) {
        this.pastSessionsArea.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 2rem;">No past sessions</div>';
        return;
      }
      const n = t.sessions.map((s) => {
        var m;
        const a = s.outcome || "unknown", d = s.outcome ? s.outcome.toUpperCase() : "IN PROGRESS", o = s.started_at ? new Date(s.started_at).toLocaleString() : "Unknown";
        let i = "";
        return s.conversation && s.conversation.length > 0 ? i = s.conversation.map((l) => {
          const g = l.role === "user" ? "👤 CHILD" : "🎅 SANTA";
          let c = l.content;
          if (l.role === "assistant")
            try {
              c = JSON.parse(c).speech || c;
            } catch {
            }
          return `<div class="chat-bubble ${l.role}">
                            <div class="chat-bubble-label">${g}</div>
                            <div class="chat-bubble-content">${r(c)}</div>
                        </div>`;
        }).join("") : i = '<div style="color: var(--text-secondary); font-size: 0.8rem;">No conversation recorded</div>', `<div class="session-card">
                    <div class="session-card-header">
                        <div>
                            <strong>${r(s.redeemer_display_name)}</strong>
                            <span style="color: var(--text-secondary); font-size: 0.75rem; margin-left: 0.5rem;">${o}</span>
                        </div>
                        <span class="session-outcome ${a}">${d}</span>
                    </div>
                    <div style="color: var(--text-secondary); font-size: 0.8rem; margin-bottom: 0.5rem;">
                        Wish: "${r(s.wish_text || "No wish")}"
                    </div>
                    <details>
                        <summary style="cursor: pointer; font-size: 0.8rem; color: var(--text-secondary);">Show conversation (${((m = s.conversation) == null ? void 0 : m.length) || 0} messages)</summary>
                        <div style="margin-top: 0.5rem; padding: 0.5rem; background: var(--bg-primary); border-radius: 4px; max-height: 200px; overflow-y: auto;">
                            ${i}
                        </div>
                    </details>
                </div>`;
      }).join("");
      this.pastSessionsArea.innerHTML = n;
    } catch (e) {
      this.pastSessionsArea.innerHTML = '<div style="color: var(--text-secondary);">Failed to load past sessions</div>', console.error("Failed to load past sessions:", e);
    }
  }
  updateButtonStates() {
    const e = this.sessionActive;
    this.sendMessageBtn.disabled = !e, this.grantBtn.disabled = !e, this.denyBtn.disabled = !e, this.cancelBtn.disabled = !e;
  }
  // -------------------------------------------------------------------------
  // API Calls
  // -------------------------------------------------------------------------
  async loadConfig() {
    try {
      const t = await (await fetch("/api/santa/config")).json();
      this.enabledToggle.checked = t.enabled, this.characterName.value = t.character_name, this.configuredRewardId = t.reward_id || "", this.rewardId.value = this.configuredRewardId, this.chatVoteSeconds.value = t.chat_vote_seconds, this.maxFollowups.value = t.max_followups, this.responseTimeout.value = t.response_timeout_seconds, this.debounceSeconds.value = t.debounce_seconds, this.log("Configuration loaded");
    } catch (e) {
      this.log("Failed to load config: " + e.message);
    }
  }
  async saveConfig() {
    try {
      const e = {
        enabled: this.enabledToggle.checked,
        reward_id: this.rewardId.value || null,
        chat_vote_seconds: parseInt(this.chatVoteSeconds.value),
        max_followups: parseInt(this.maxFollowups.value),
        response_timeout_seconds: parseInt(this.responseTimeout.value),
        debounce_seconds: parseInt(this.debounceSeconds.value)
      }, t = await fetch("/api/santa/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(e)
      });
      if (t.ok)
        this.log("Configuration saved");
      else {
        const n = await t.json();
        this.log("Failed to save config: " + n.detail);
      }
    } catch (e) {
      this.log("Failed to save config: " + e.message);
    }
  }
  async loadEventSubStatus() {
    try {
      const t = await (await fetch("/api/santa/eventsub/status")).json();
      this.eventsubConnected = t.connected, t.connected ? (this.eventsubStatus.classList.add("connected"), this.eventsubStatusText.textContent = "EventSub", this.loadRewards()) : (this.eventsubStatus.classList.remove("connected"), this.eventsubStatusText.textContent = "EventSub"), this.updateConnectionBanner();
    } catch {
      this.eventsubConnected = !1, this.updateConnectionBanner();
    }
  }
  updateConnectionBanner() {
    const e = this.connected, t = this.eventsubConnected, n = e && t, s = !e && !t;
    this.connectionBanner.classList.remove("connected", "error"), n ? (this.connectionBanner.classList.add("connected"), this.overallStatusIcon.textContent = "🎅", this.overallStatusText.textContent = "Santa Ready") : s ? (this.connectionBanner.classList.add("error"), this.overallStatusIcon.textContent = "❌", this.overallStatusText.textContent = "Disconnected") : (this.overallStatusIcon.textContent = "⚠️", t ? this.overallStatusText.textContent = "Dashboard reconnecting..." : this.overallStatusText.textContent = "EventSub not connected - use Reset Santa");
  }
  async loadRewards() {
    try {
      const t = await (await fetch("/api/santa/rewards")).json(), n = this.rewardId.value || this.configuredRewardId || "";
      t.rewards && t.rewards.length > 0 ? (this.rewardId.innerHTML = '<option value="">All rewards</option>' + t.rewards.map(
        (s) => `<option value="${s.id}">${r(s.title)} (${s.cost} pts)${s.is_paused ? " [PAUSED]" : ""}</option>`
      ).join(""), this.rewardId.value = n, this.log(`Loaded ${t.rewards.length} rewards`)) : (this.rewardId.innerHTML = '<option value="">All rewards</option>', this.log("No rewards found"));
    } catch (e) {
      this.log("Failed to load rewards: " + e.message);
    }
  }
  async sendMessage() {
    const e = this.messageInput.value.trim();
    if (e)
      try {
        const t = await fetch("/api/santa/session/message", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: e })
        });
        if (t.ok)
          this.log("Message sent: " + e), this.messageInput.value = "";
        else {
          const n = await t.json();
          this.log("Failed to send message: " + n.detail);
        }
      } catch (t) {
        this.log("Failed to send message: " + t.message);
      }
  }
  async forceVerdict(e) {
    try {
      const t = await fetch("/api/santa/session/verdict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ verdict: e })
      });
      if (t.ok)
        this.log("Verdict forced: " + e);
      else {
        const n = await t.json();
        this.log("Failed to force verdict: " + n.detail);
      }
    } catch (t) {
      this.log("Failed to force verdict: " + t.message);
    }
  }
  async cancelSession() {
    try {
      const e = await fetch("/api/santa/session/cancel", { method: "POST" });
      if (e.ok)
        this.log("Session cancelled");
      else {
        const t = await e.json();
        this.log("Failed to cancel session: " + t.detail);
      }
    } catch (e) {
      this.log("Failed to cancel session: " + e.message);
    }
  }
  async toggleHold() {
    try {
      const e = await fetch("/api/santa/session/hold", { method: "POST" }), t = await e.json();
      e.ok ? this.log(t.held ? "⏸ Session on hold" : "▶ Session resumed") : this.log("Failed to toggle hold: " + t.detail);
    } catch (e) {
      this.log("Failed to toggle hold: " + e.message);
    }
  }
  // -------------------------------------------------------------------------
  // Character / System Prompt
  // -------------------------------------------------------------------------
  async loadCharacter() {
    try {
      const e = await fetch("/api/characters/santa_timmy");
      if (e.ok) {
        const t = await e.json();
        this.systemPrompt.value = t.system_prompt || "", this.log("Character settings loaded");
      }
    } catch (e) {
      this.log("Failed to load character: " + e.message);
    }
  }
  async saveSystemPrompt() {
    try {
      const e = await fetch("/api/characters/santa_timmy", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          system_prompt: this.systemPrompt.value
        })
      });
      if (e.ok)
        this.log("System prompt saved");
      else {
        const t = await e.json();
        this.log("Failed to save prompt: " + t.detail);
      }
    } catch (e) {
      this.log("Failed to save prompt: " + e.message);
    }
  }
  async resetSystemPrompt() {
    const e = `You are Timmy, a jolly mall penguin Santa with magical wish-granting powers!

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
    this.systemPrompt.value = e, this.log("Reset to default prompt (not saved yet)");
  }
  async speakDirect() {
    const e = this.directorInput.value.trim();
    if (e)
      try {
        this.speakDirectBtn.disabled = !0, this.log("Mall Director interrupting: " + e);
        const t = `[MALL DIRECTOR INTERRUPTION]: ${e}`, n = await fetch("/api/santa/interrupt", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: t })
        });
        if (n.ok)
          this.directorInput.value = "", this.log("Director message sent to Santa");
        else {
          const s = await n.json();
          this.log("Failed to send: " + s.detail);
        }
      } catch (t) {
        this.log("Failed to send: " + t.message);
      } finally {
        this.speakDirectBtn.disabled = !1;
      }
  }
  async resetSanta() {
    if (confirm("Reset Santa completely? This will clear sessions, memory, and restart EventSub."))
      try {
        this.resetSantaBtn.disabled = !0, this.log("🔄 Resetting Santa...");
        const e = await fetch("/api/santa/reset", { method: "POST" }), t = await e.json();
        e.ok ? (this.log("✅ Reset complete: " + t.results.join(", ")), this.loadEventSubStatus(), this.loadPastSessions()) : this.log("Failed to reset: " + t.detail);
      } catch (e) {
        this.log("Failed to reset: " + e.message);
      } finally {
        this.resetSantaBtn.disabled = !1;
      }
  }
  async clearMemory() {
    if (confirm("Clear Santa Timmy's memory? This will forget all past conversations."))
      try {
        this.clearMemoryBtn.disabled = !0;
        const e = await fetch("/api/characters/santa_timmy/memory", {
          method: "DELETE"
        });
        if (e.ok)
          this.log("🧹 Santa's memory cleared");
        else {
          const t = await e.json();
          this.log("Failed to clear memory: " + t.detail);
        }
      } catch (e) {
        this.log("Failed to clear memory: " + e.message);
      } finally {
        this.clearMemoryBtn.disabled = !1;
      }
  }
  async clearSessions() {
    if (confirm("Clear ALL past Santa sessions? This will delete session history but NOT Santa's memory."))
      try {
        this.clearSessionsBtn.disabled = !0;
        const e = await fetch("/api/santa/sessions", {
          method: "DELETE"
        });
        if (e.ok)
          this.log("🗑️ All sessions cleared"), this.loadPastSessions();
        else {
          const t = await e.json();
          this.log("Failed to clear sessions: " + t.detail);
        }
      } catch (e) {
        this.log("Failed to clear sessions: " + e.message);
      } finally {
        this.clearSessionsBtn.disabled = !1;
      }
  }
  async createReward() {
    const e = prompt("Reward title:", "Talk to Santa");
    if (!e) return;
    const t = prompt("Cost in channel points:", "100");
    if (!t) return;
    const n = parseInt(t);
    if (isNaN(n) || n < 1) {
      this.log("Invalid cost");
      return;
    }
    try {
      this.createRewardBtn.disabled = !0, this.log("Creating reward...");
      const s = await fetch("/api/santa/reward/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: e,
          cost: n,
          prompt: "Tell Santa your Christmas wish!"
        })
      });
      if (s.ok) {
        const a = await s.json();
        this.log(`✅ Created reward: ${a.reward.title} (${a.reward.cost} pts)`), await this.loadRewards(), this.rewardId.value = a.reward.id, await this.saveConfig();
      } else {
        const a = await s.json();
        this.log("Failed to create reward: " + a.detail);
      }
    } catch (s) {
      this.log("Failed to create reward: " + s.message);
    } finally {
      this.createRewardBtn.disabled = !1;
    }
  }
  // -------------------------------------------------------------------------
  // Event Listeners
  // -------------------------------------------------------------------------
  attachEventListeners() {
    this.saveConfigBtn.addEventListener("click", () => this.saveConfig()), this.refreshRewardsDropdownBtn.addEventListener("click", () => this.loadRewards()), this.createRewardBtn.addEventListener("click", () => this.createReward()), this.sendMessageBtn.addEventListener("click", () => this.sendMessage()), this.messageInput.addEventListener("keypress", (e) => {
      e.key === "Enter" && !this.sendMessageBtn.disabled && this.sendMessage();
    }), this.grantBtn.addEventListener("click", () => this.forceVerdict("grant")), this.denyBtn.addEventListener("click", () => this.forceVerdict("deny")), this.holdToggle.addEventListener("change", () => this.toggleHold()), this.cancelBtn.addEventListener("click", () => this.cancelSession()), this.refreshSessionsBtn.addEventListener("click", () => this.loadPastSessions()), this.clearSessionsBtn.addEventListener("click", () => this.clearSessions()), this.speakDirectBtn.addEventListener("click", () => this.speakDirect()), this.directorInput.addEventListener("keypress", (e) => {
      e.key === "Enter" && this.speakDirect();
    }), this.savePromptBtn.addEventListener("click", () => this.saveSystemPrompt()), this.resetPromptBtn.addEventListener("click", () => this.resetSystemPrompt()), this.resetSantaBtn.addEventListener("click", () => this.resetSanta()), this.clearMemoryBtn.addEventListener("click", () => this.clearMemory()), this.enabledToggle.addEventListener("change", () => this.toggleEnabled());
  }
  async toggleEnabled() {
    try {
      const e = await fetch("/api/santa/toggle", { method: "POST" }), t = await e.json();
      e.ok ? (this.enabledToggle.checked = t.enabled, this.log(t.enabled ? "✅ Santa enabled" : "⏸️ Santa disabled"), this.loadRewards()) : (this.enabledToggle.checked = !this.enabledToggle.checked, this.log("Failed to toggle: " + t.detail));
    } catch (e) {
      this.enabledToggle.checked = !this.enabledToggle.checked, this.log("Failed to toggle: " + e.message);
    }
  }
  // -------------------------------------------------------------------------
  // Logging
  // -------------------------------------------------------------------------
  log(e) {
    const t = (/* @__PURE__ */ new Date()).toLocaleTimeString(), n = document.createElement("div");
    for (n.className = "log-entry", n.innerHTML = `<span class="log-time">[${t}]</span> ${e}`, this.logArea.appendChild(n), this.logArea.scrollTop = this.logArea.scrollHeight; this.logArea.children.length > 100; )
      this.logArea.removeChild(this.logArea.firstChild);
  }
}
document.addEventListener("DOMContentLoaded", () => {
  window.santaDashboard = new p();
});
export {
  p as SantaDashboard,
  r as escapeHtml
};
