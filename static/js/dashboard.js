import { TextAnimator as $e } from "./text-animator.js";
let y = null, C = null, _ = 0;
const Te = 1e3, Me = 3e4, N = 10, oe = 6e4, Se = 3e4;
let F = Date.now(), S = null, M = null, ce = [], g = [], E = null, m = null, b = null, U = [], f = null, p = null, k = !1, B = [], X = null;
const re = document.getElementById("ws-status"), se = document.getElementById("ws-status-text"), L = document.getElementById("characters-container"), le = document.getElementById("history-list");
function w(e) {
  if (e == null) return "";
  const t = document.createElement("div");
  return t.textContent = String(e), t.innerHTML;
}
function Le(e, t = "#9146ff") {
  return e && /^#[0-9a-fA-F]{3,4}$|^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$/.test(e) ? e : t;
}
function Ae() {
  return X;
}
function ye() {
  const t = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/dashboard`;
  y = new WebSocket(t), y.onopen = () => {
    re.classList.add("connected"), se.textContent = "Connected", _ = 0, F = Date.now(), Ne(), C && (clearTimeout(C), C = null);
  }, y.onclose = () => {
    re.classList.remove("connected"), se.textContent = "Disconnected", Pe(), De();
  }, y.onerror = (n) => {
    console.error("Dashboard WebSocket error:", n);
  }, y.onmessage = (n) => {
    try {
      const a = JSON.parse(n.data);
      Re(a);
    } catch (a) {
      console.error("Error parsing message:", a);
    }
  };
}
function De() {
  if (!C) {
    if (_ >= N) {
      console.log(`[dashboard] Max reconnect attempts (${N}) reached, reloading page...`), location.reload();
      return;
    }
    const e = Math.min(
      Te * Math.pow(2, _),
      Me
    );
    _++, console.log(`[dashboard] Reconnecting in ${e}ms (attempt ${_}/${N})...`), C = setTimeout(() => {
      C = null, ye();
    }, e);
  }
}
function Pe() {
  S || (S = setInterval(async () => {
    if (!(y && y.readyState === WebSocket.OPEN))
      try {
        (await fetch("/health", { signal: AbortSignal.timeout(5e3) })).ok && _ >= N / 2 && (console.log("[dashboard] Server healthy but WebSocket failing, reloading page..."), location.reload());
      } catch {
      }
  }, Se));
}
function Ne() {
  S && (clearInterval(S), S = null);
}
setInterval(() => {
  y && y.readyState === WebSocket.OPEN && Date.now() - F > oe && (console.log(`[dashboard] No ping received in ${oe}ms, connection stale - reconnecting...`), F = Date.now(), y.close());
}, 1e4);
function Re(e) {
  if (e.type === "ping") {
    y && y.readyState === WebSocket.OPEN && y.send(JSON.stringify({ event: "pong", ts: e.ts })), F = Date.now();
    return;
  }
  if (e.type === "hello") {
    const t = e.build_id;
    if (e.tenant_id && (X = e.tenant_id, console.log(`[dashboard] Tenant ID: ${X}`)), M === null)
      M = t, console.log(`[dashboard] Server build ID: ${M}`);
    else if (M !== t) {
      console.log(`[dashboard] Server version changed (${M} -> ${t}), refreshing page...`), location.reload();
      return;
    } else
      console.log("[dashboard] Reconnected to same server version");
    return;
  }
  if (e.type === "characters") {
    const t = Ae(), n = new Map(e.characters.map((a) => [a.name, a]));
    if (g = g.map((a) => {
      var c, r;
      const o = `${t}:${a.name}`;
      return {
        ...a,
        connected: n.has(o),
        playing: ((c = n.get(o)) == null ? void 0 : c.playing) || !1,
        streaming: ((r = n.get(o)) == null ? void 0 : r.streaming) || !1
      };
    }), K(), f && p) {
      const a = `${t}:${f}`, o = n.get(a);
      if (o && (o.streaming && (k = !0), k && !o.streaming)) {
        const c = document.getElementById(`${p}-stop-btn`), r = document.getElementById(`${p}-status-text`);
        c && (c.style.display = "none"), r && (r.textContent = "Complete!"), f = null, p = null, k = !1;
      }
    }
  } else e.type === "character_sync" && (g = e.characters, K(), P || console.log("Character data synced from server"), P = !1);
}
let P = !1;
function u(e, t = "info", n = 4e3) {
  const a = document.querySelector(".toast-notification");
  a && a.remove();
  const o = document.createElement("div");
  o.className = `toast-notification toast-${t}`, o.textContent = e, document.body.appendChild(o), setTimeout(() => {
    o.classList.add("hiding"), setTimeout(() => o.remove(), 300);
  }, n);
}
async function i(e, t = "GET", n = null, a = !0) {
  const o = {
    method: t,
    headers: { "Content-Type": "application/json" }
  };
  n && (o.body = JSON.stringify(n));
  try {
    const c = await fetch(e, o), r = await c.json();
    if (!c.ok) {
      const s = r.detail || r.error || `HTTP ${c.status}`;
      return a && u(`API Error: ${s}`, "error"), console.error(`API Error [${t} ${e}]:`, s), { error: s, status: c.status };
    }
    return r;
  } catch (c) {
    const r = c.message || "Network error";
    return a && u(`Connection Error: ${r}`, "error"), console.error(`Fetch Error [${t} ${e}]:`, c), { error: r, networkError: !0 };
  }
}
async function Fe() {
  const e = await i("/api/presets");
  return Array.isArray(e) && (ce = e), ce;
}
async function z() {
  const e = await i("/api/history");
  Array.isArray(e) && lt(e);
}
async function q() {
  const e = await i("/api/characters");
  return Array.isArray(e) && (g = e, K()), g;
}
async function Ue(e) {
  P = !0;
  const t = await i("/api/characters", "POST", e);
  return await q(), t;
}
async function He(e, t, n = !0) {
  P = !0;
  const a = await i(`/api/characters/${e}`, "PUT", t, n);
  return await q(), a;
}
async function Oe(e) {
  if (!confirm(`Delete character "${e}"? This cannot be undone.`))
    return;
  P = !0;
  const t = await i(`/api/characters/${e}`, "DELETE");
  return await q(), t;
}
async function he(e) {
  const t = document.getElementById("character-provider");
  if (t) {
    if (t.innerHTML = '<option value="">Loading providers...</option>', t.disabled = !0, !e || e.trim() === "") {
      t.innerHTML = '<option value="">Default (auto)</option>', t.disabled = !1;
      return;
    }
    try {
      const n = await i(`/api/openrouter/models/${encodeURIComponent(e)}/providers`, "GET", null, !1);
      if (t.innerHTML = '<option value="">Default (auto)</option>', n.providers && n.providers.length > 0)
        for (const a of n.providers) {
          const o = document.createElement("option");
          o.value = a, o.textContent = a, t.appendChild(o);
        }
    } catch (n) {
      console.error("Error fetching providers:", n), t.innerHTML = '<option value="">Default (auto)</option>';
    } finally {
      t.disabled = !1;
    }
  }
}
async function Ge() {
  const e = document.getElementById("character-tts-model");
  if (e)
    try {
      const t = await i("/api/elevenlabs/models", "GET", null, !1);
      Array.isArray(t) && (U = t, e.innerHTML = t.map((n) => {
        const a = n.name || n.model_id;
        return `<option value="${n.model_id}">${a}</option>`;
      }).join(""));
    } catch (t) {
      console.error("Error fetching ElevenLabs models:", t);
    }
}
async function pe(e) {
  const t = document.getElementById("character-tts-model"), n = document.getElementById("tts-model-info");
  if (!(!t || !e)) {
    n && (n.textContent = "");
    try {
      const a = await i(`/api/elevenlabs/voices/${e}`, "GET", null, !1);
      if (a && a.high_quality_base_model_ids && a.high_quality_base_model_ids.length > 0) {
        const o = new Set(a.high_quality_base_model_ids);
        Array.from(t.options).forEach((c) => {
          if (o.has(c.value)) {
            const r = U.find((s) => s.model_id === c.value);
            c.textContent = `${(r == null ? void 0 : r.name) || c.value} (Recommended)`;
          } else {
            const r = U.find((s) => s.model_id === c.value);
            c.textContent = (r == null ? void 0 : r.name) || c.value;
          }
        }), n && (n.textContent = `Voice "${a.name}" is optimized for: ${a.high_quality_base_model_ids.join(", ")}`);
      }
    } catch (a) {
      console.error("Error fetching voice info:", a), n && (n.textContent = "Could not fetch voice info");
    }
  }
}
const ze = {
  eleven_v3: "Latest flagship model with emotionally rich, expressive speech. 70+ languages. Best for audiobooks & dramatic content. Not optimized for real-time.",
  eleven_multilingual_v2: "Advanced emotionally-aware synthesis. 29 languages. Most stable for long-form. Higher latency but best quality.",
  eleven_flash_v2_5: "Fastest model (~75ms latency). 32 languages. 50% lower cost. Best for real-time agents & bulk processing.",
  eleven_turbo_v2_5: "Balanced quality & speed (~250ms). 32 languages. Good middle-ground between Flash and Multilingual.",
  eleven_flash_v2: "Ultra-fast for real-time (~75ms). English only. Great for conversational agents.",
  eleven_turbo_v2: "Quality-focused with low latency (~250ms). English only. Good balance for English projects.",
  eleven_multilingual_v1: "Legacy multilingual model. Use v2 for better results.",
  eleven_monolingual_v1: "Legacy English model. Use newer models for better quality."
};
function Q(e) {
  const t = document.getElementById("tts-model-info"), n = document.getElementById("voice-style-row"), a = document.getElementById("voice-similarity-row"), o = U.find((c) => c.model_id === e);
  o && (n && (n.style.display = o.can_use_style ? "" : "none"), a && (a.style.display = o.can_use_speaker_boost ? "" : "none"), t && (t.textContent = ze[e] || ""));
}
let H = [];
async function Z() {
  try {
    H = await i("/api/cartesia/voices", "GET", null, !1);
    const e = document.getElementById("cartesia-voice-select");
    if (!e) return;
    e.innerHTML = '<option value="">-- Select a voice --</option>', H.forEach((t) => {
      const n = document.createElement("option");
      n.value = t.voice_id, n.textContent = `${t.name} (${t.language})`, e.appendChild(n);
    });
  } catch (e) {
    console.error("Error loading Cartesia voices:", e);
    const t = document.getElementById("cartesia-voice-select");
    t && (t.innerHTML = '<option value="">Failed to load voices</option>');
  }
}
function qe(e) {
  const t = document.getElementById("cartesia-voice-id");
  t && e && (t.value = e), W(e);
}
function We(e) {
  const t = document.getElementById("cartesia-voice-select");
  t && e && (Array.from(t.options).find((a) => a.value === e) ? (t.value = e, W(e)) : (t.value = "", document.getElementById("cartesia-voice-info").textContent = "Custom voice ID"));
}
function W(e) {
  const t = document.getElementById("cartesia-voice-info");
  if (!t) return;
  if (!e) {
    t.textContent = "";
    return;
  }
  const n = H.find((a) => a.voice_id === e);
  n && n.description ? t.textContent = n.description : t.textContent = "";
}
function ge(e) {
  const t = document.getElementById("elevenlabs-settings"), n = document.getElementById("cartesia-settings");
  e === "cartesia" ? (t.style.display = "none", n.style.display = "block", H.length === 0 && Z()) : (t.style.display = "block", n.style.display = "none");
}
async function je(e, t, n) {
  return i(`/api/characters/${e}/speak`, "POST", {
    text: t,
    show_text: n
  });
}
async function Ve(e, t, n, a = null, o = null) {
  const c = {
    message: t,
    show_text: n
  };
  return a !== null && a !== "" && (c.twitch_chat_seconds = parseInt(a)), o && o.length > 0 && (c.images = o.map((r) => ({
    data: r.data,
    media_type: r.mediaType
  }))), i(`/api/characters/${e}/chat`, "POST", c);
}
async function ee(e) {
  return i(`/api/characters/${e}/memory`);
}
async function Ye(e) {
  return i(`/api/characters/${e}/memory`, "DELETE");
}
function O(e, t) {
  const n = document.getElementById("chat-history"), a = document.getElementById("chat-history-empty");
  if (!e || e.length === 0) {
    a.style.display = "block", n.querySelectorAll(".chat-bubble").forEach((o) => o.remove());
    return;
  }
  a.style.display = "none", n.querySelectorAll(".chat-bubble").forEach((o) => o.remove()), e.forEach((o) => {
    if (o.role === "context") {
      const c = o.content.split(`
`), r = c.slice(-4).map((h) => h.length > 60 ? h.substring(0, 57) + "..." : h).join(" | "), s = document.createElement("div");
      s.className = "chat-bubble context";
      const l = document.createElement("div");
      l.className = "chat-bubble-content", l.textContent = `📺 Twitch (${c.length}): ${r}`, s.appendChild(l), n.appendChild(s);
    } else {
      const c = document.createElement("div");
      c.className = `chat-bubble ${o.role}`;
      const r = document.createElement("div");
      r.className = "chat-bubble-label", r.textContent = o.role === "user" ? "You" : t;
      const s = document.createElement("div");
      if (s.className = "chat-bubble-content", o.interrupted && o.generated_text) {
        const l = o.content || "", h = o.generated_text || "";
        if (l) {
          const v = document.createElement("span");
          v.textContent = l, s.appendChild(v);
        }
        let I = "";
        if ((h.startsWith(l) || h.length > l.length) && (I = h.substring(l.length).trim()), I) {
          const v = document.createElement("span");
          v.style.textDecoration = "line-through", v.style.opacity = "0.6", v.textContent = " " + I, s.appendChild(v);
        }
        const d = document.createElement("span");
        d.style.cssText = "display: inline-block; margin-left: 8px; padding: 2px 6px; background: #ff6b6b33; color: #ff6b6b; border-radius: 4px; font-size: 0.7rem;", d.textContent = "⚡ interrupted", s.appendChild(d);
      } else
        s.textContent = o.content;
      c.appendChild(r), c.appendChild(s), n.appendChild(c);
    }
  }), n.scrollTop = n.scrollHeight;
}
function ie(e, t, n) {
  const a = document.getElementById("chat-history"), o = document.getElementById("chat-history-empty");
  o.style.display = "none";
  const c = document.createElement("div");
  c.className = `chat-bubble ${e}`;
  const r = document.createElement("div");
  r.className = "chat-bubble-label", r.textContent = e === "user" ? "You" : n;
  const s = document.createElement("div");
  s.className = "chat-bubble-content", s.textContent = t, c.appendChild(r), c.appendChild(s), a.appendChild(c), a.scrollTop = a.scrollHeight;
}
function Xe(e) {
  const t = document.getElementById("chat-history"), n = document.getElementById("chat-history-empty");
  n.style.display = "none";
  const a = document.createElement("div");
  a.className = "chat-bubble context";
  const o = document.createElement("div");
  o.className = "chat-bubble-content", o.textContent = e, a.appendChild(o), t.appendChild(a), t.scrollTop = t.scrollHeight;
}
let x = null, R = null;
function Je() {
  te();
  const e = document.getElementById("character-preview-canvas");
  if (!e) return;
  const t = e.getContext("2d");
  x = new $e(t, e.width, e.height);
  const n = {
    style: document.getElementById("character-text-style").value,
    fontFamily: document.getElementById("character-font-family").value,
    fontSize: parseInt(document.getElementById("character-font-size").value),
    duration: parseInt(document.getElementById("character-text-duration").value),
    color: document.getElementById("character-text-color").value,
    strokeColor: document.getElementById("character-stroke-color").value,
    strokeWidth: parseInt(document.getElementById("character-stroke-width").value),
    positionX: parseInt(document.getElementById("character-position-x").value) / 100,
    positionY: parseInt(document.getElementById("character-position-y").value) / 100
  }, a = e.width / 800;
  x.show({
    text: "Sample Text",
    style: n.style,
    duration: n.duration,
    x: n.positionX,
    y: n.positionY,
    fontFamily: n.fontFamily,
    fontSize: Math.round(n.fontSize * a),
    color: n.color,
    strokeColor: n.strokeWidth > 0 ? n.strokeColor : null,
    strokeWidth: Math.round(n.strokeWidth * a)
  });
  function o() {
    t.clearRect(0, 0, e.width, e.height), x.update(), x.draw(), x.current && (R = requestAnimationFrame(o));
  }
  o();
}
function te() {
  R && (cancelAnimationFrame(R), R = null), x && x.clear();
  const e = document.getElementById("character-preview-canvas");
  e && e.getContext("2d").clearRect(0, 0, e.width, e.height);
}
const $ = document.getElementById("character-modal"), J = document.getElementById("character-form"), ve = document.getElementById("character-modal-title");
function Ke() {
  E = null, ve.textContent = "Create Character", J.reset(), document.getElementById("character-name").disabled = !1, document.getElementById("character-color").value = "#e94560", document.getElementById("character-icon").value = "🔊", document.getElementById("character-stability").value = 50, document.getElementById("character-stability-value").textContent = "0.50", document.getElementById("character-similarity").value = 75, document.getElementById("character-similarity-value").textContent = "0.75", document.getElementById("character-voice-style").value = 0, document.getElementById("character-style-value").textContent = "0.00", document.getElementById("character-voice-speed").value = 100, document.getElementById("character-speed-value").textContent = "1.0", document.getElementById("character-volume").value = 100, document.getElementById("character-volume-value").textContent = "100", document.getElementById("character-text-style").value = "typewriter", document.getElementById("character-font-family").value = "Arial", document.getElementById("character-font-size").value = 48, document.getElementById("character-text-duration").value = 3e3, document.getElementById("character-text-color").value = "#ffffff", document.getElementById("character-stroke-color").value = "#000000", document.getElementById("character-stroke-width").value = 0, document.getElementById("character-stroke-width-value").textContent = "0", document.getElementById("character-position-x").value = 50, document.getElementById("character-pos-x-value").textContent = "50", document.getElementById("character-position-y").value = 50, document.getElementById("character-pos-y-value").textContent = "50", document.getElementById("character-model").value = "anthropic/claude-sonnet-4.5", document.getElementById("character-provider").innerHTML = '<option value="">Default (auto)</option>', document.getElementById("character-provider").value = "", document.getElementById("character-temperature").value = 70, document.getElementById("character-temp-value").textContent = "0.7", document.getElementById("character-max-tokens").value = 1024, document.getElementById("character-tts-model").value = "eleven_multilingual_v2", document.getElementById("tts-model-info").textContent = "", Q("eleven_multilingual_v2"), document.getElementById("character-memory-enabled").checked = !1, document.getElementById("character-persist-memory").checked = !1, document.getElementById("character-twitch-chat-enabled").checked = !1, document.getElementById("character-twitch-chat-seconds").value = 60, document.getElementById("character-twitch-chat-max").value = 20, $.classList.add("active");
}
function fe(e) {
  E = e, ve.textContent = "Edit Character", document.getElementById("character-name").value = e.name, document.getElementById("character-name").disabled = !0, document.getElementById("character-description").value = e.description || "", document.getElementById("character-color").value = e.color, document.getElementById("character-icon").value = e.icon;
  const t = e.tts_provider || "elevenlabs";
  if (document.getElementById("character-tts-provider").value = t, ge(t), t === "cartesia" && e.tts_settings)
    Z().then(() => {
      const n = e.tts_settings, a = n.voice_id || "";
      document.getElementById("cartesia-voice-id").value = a;
      const o = document.getElementById("cartesia-voice-select");
      o && a && Array.from(o.options).find((l) => l.value === a) && (o.value = a), document.getElementById("cartesia-model-id").value = n.model_id || "sonic-2024-12-12", document.getElementById("cartesia-language").value = n.language || "en";
      const c = n.speed || 1, r = Math.max(0.6, Math.min(1.5, c));
      document.getElementById("cartesia-speed").value = Math.round(r * 100), document.getElementById("cartesia-speed-value").textContent = r.toFixed(1), c !== r && console.warn(`Cartesia speed ${c} was clamped to ${r} (valid: 0.6-1.5)`), W(a);
    });
  else {
    const n = e.tts_settings || {};
    document.getElementById("character-voice-id").value = n.voice_id || e.elevenlabs_voice_id;
    const a = n.model_id || e.elevenlabs_model_id || "eleven_multilingual_v2";
    document.getElementById("character-tts-model").value = a, Q(a), pe(n.voice_id || e.elevenlabs_voice_id);
    const o = n.stability ?? e.voice_stability;
    document.getElementById("character-stability").value = Math.round(o * 100), document.getElementById("character-stability-value").textContent = o.toFixed(2);
    const c = n.similarity_boost ?? e.voice_similarity_boost;
    document.getElementById("character-similarity").value = Math.round(c * 100), document.getElementById("character-similarity-value").textContent = c.toFixed(2);
    const r = n.style ?? e.voice_style;
    document.getElementById("character-voice-style").value = Math.round(r * 100), document.getElementById("character-style-value").textContent = r.toFixed(2);
    const s = n.speed ?? e.voice_speed;
    document.getElementById("character-voice-speed").value = Math.round(s * 100), document.getElementById("character-speed-value").textContent = s.toFixed(1);
  }
  document.getElementById("character-volume").value = Math.round(e.default_volume * 100), document.getElementById("character-volume-value").textContent = Math.round(e.default_volume * 100), document.getElementById("character-muted").checked = e.mute_state, document.getElementById("character-text-style").value = e.default_text_style, document.getElementById("character-font-family").value = e.text_font_family, document.getElementById("character-font-size").value = e.text_font_size, document.getElementById("character-text-duration").value = e.text_duration, document.getElementById("character-text-color").value = e.text_color, document.getElementById("character-stroke-color").value = e.text_stroke_color || "#000000", document.getElementById("character-stroke-width").value = e.text_stroke_width, document.getElementById("character-stroke-width-value").textContent = e.text_stroke_width, document.getElementById("character-position-x").value = Math.round(e.text_position_x * 100), document.getElementById("character-pos-x-value").textContent = Math.round(e.text_position_x * 100), document.getElementById("character-position-y").value = Math.round(e.text_position_y * 100), document.getElementById("character-pos-y-value").textContent = Math.round(e.text_position_y * 100), document.getElementById("character-prompt").value = e.system_prompt || "", document.getElementById("character-model").value = e.model, he(e.model).then(() => {
    document.getElementById("character-provider").value = e.provider || "";
  }), document.getElementById("character-temperature").value = Math.round(e.temperature * 100), document.getElementById("character-temp-value").textContent = e.temperature.toFixed(1), document.getElementById("character-max-tokens").value = e.max_tokens, document.getElementById("character-memory-enabled").checked = e.memory_enabled || !1, document.getElementById("character-persist-memory").checked = e.persist_memory || !1, document.getElementById("character-twitch-chat-enabled").checked = e.twitch_chat_enabled || !1, document.getElementById("character-twitch-chat-seconds").value = e.twitch_chat_window_seconds || 60, document.getElementById("character-twitch-chat-max").value = e.twitch_chat_max_messages || 20, $.classList.add("active");
}
function G() {
  $.classList.remove("active"), E = null, te();
}
async function Qe(e) {
  e.preventDefault();
  const t = document.getElementById("character-tts-provider").value;
  let n = null;
  t === "cartesia" ? n = {
    voice_id: document.getElementById("cartesia-voice-id").value,
    model_id: document.getElementById("cartesia-model-id").value,
    language: document.getElementById("cartesia-language").value,
    speed: parseInt(document.getElementById("cartesia-speed").value) / 100
  } : n = {
    voice_id: document.getElementById("character-voice-id").value,
    model_id: document.getElementById("character-tts-model").value,
    stability: parseInt(document.getElementById("character-stability").value) / 100,
    similarity_boost: parseInt(document.getElementById("character-similarity").value) / 100,
    style: parseInt(document.getElementById("character-voice-style").value) / 100,
    speed: parseInt(document.getElementById("character-voice-speed").value) / 100
  };
  const a = {
    name: document.getElementById("character-name").value,
    description: document.getElementById("character-description").value || null,
    color: document.getElementById("character-color").value,
    icon: document.getElementById("character-icon").value,
    // TTS provider abstraction
    tts_provider: t,
    tts_settings: n,
    // Legacy ElevenLabs fields (for backwards compatibility)
    elevenlabs_voice_id: document.getElementById("character-voice-id").value,
    elevenlabs_model_id: document.getElementById("character-tts-model").value,
    voice_stability: parseInt(document.getElementById("character-stability").value) / 100,
    voice_similarity_boost: parseInt(document.getElementById("character-similarity").value) / 100,
    voice_style: parseInt(document.getElementById("character-voice-style").value) / 100,
    voice_speed: parseInt(document.getElementById("character-voice-speed").value) / 100,
    default_volume: parseInt(document.getElementById("character-volume").value) / 100,
    mute_state: document.getElementById("character-muted").checked,
    default_text_style: document.getElementById("character-text-style").value,
    text_font_family: document.getElementById("character-font-family").value,
    text_font_size: parseInt(document.getElementById("character-font-size").value),
    text_duration: parseInt(document.getElementById("character-text-duration").value),
    text_color: document.getElementById("character-text-color").value,
    text_stroke_color: parseInt(document.getElementById("character-stroke-width").value) > 0 ? document.getElementById("character-stroke-color").value : null,
    text_stroke_width: parseInt(document.getElementById("character-stroke-width").value),
    text_position_x: parseInt(document.getElementById("character-position-x").value) / 100,
    text_position_y: parseInt(document.getElementById("character-position-y").value) / 100,
    system_prompt: document.getElementById("character-prompt").value || null,
    model: document.getElementById("character-model").value,
    provider: document.getElementById("character-provider").value || null,
    temperature: parseInt(document.getElementById("character-temperature").value) / 100,
    max_tokens: parseInt(document.getElementById("character-max-tokens").value),
    memory_enabled: document.getElementById("character-memory-enabled").checked,
    persist_memory: document.getElementById("character-persist-memory").checked,
    twitch_chat_enabled: document.getElementById("character-twitch-chat-enabled").checked,
    twitch_chat_window_seconds: parseInt(document.getElementById("character-twitch-chat-seconds").value),
    twitch_chat_max_messages: parseInt(document.getElementById("character-twitch-chat-max").value),
    // Optimistic concurrency control - send timestamp to detect conflicts
    expected_updated_at: (E == null ? void 0 : E.updated_at) || null
  };
  try {
    if (E) {
      const o = await He(E.name, a, !1);
      if (o && o.status === 409) {
        const c = await i(`/api/characters/${encodeURIComponent(E.name)}`, "GET", null, !1);
        c && !c.error ? (fe(c), u("Someone else modified this character. Please review the updated values and try again.", "warning")) : (G(), u("Character was modified. Please try again.", "warning"));
        return;
      }
    } else
      await Ue(a);
    G();
  } catch (o) {
    console.error("Error saving character:", o), alert("Error saving character. Check console for details.");
  }
}
const A = document.getElementById("speak-modal");
function Ze(e) {
  const t = g.find((n) => n.name === e);
  t && (b = t, document.getElementById("speak-modal-title").textContent = `Speak as ${t.name}`, document.getElementById("speak-text").value = "", document.getElementById("speak-show-text").checked = !0, document.getElementById("speak-status").style.display = "none", document.getElementById("speak-send-btn").disabled = !1, A.classList.add("active"));
}
function Ee() {
  A.classList.remove("active"), b = null;
}
async function et() {
  if (!b) return;
  const e = document.getElementById("speak-text").value.trim(), t = document.getElementById("speak-show-text").checked;
  if (!e) {
    alert("Please enter text to speak");
    return;
  }
  const n = document.getElementById("speak-status"), a = document.getElementById("speak-status-text"), o = document.getElementById("speak-send-btn"), c = document.getElementById("speak-stop-btn");
  n.style.display = "block", a.textContent = "Speaking...", o.disabled = !0, c.style.display = "inline-block", f = b.name, p = "speak", k = !1;
  try {
    const r = await je(b.name, e, t);
    r.error || r.detail ? (a.textContent = `Error: ${r.error || r.detail}`, c.style.display = "none", f = null, p = null) : (a.textContent = "Playing audio...", document.getElementById("speak-text").value = "", z());
  } catch (r) {
    console.error("Speak error:", r), a.textContent = `Error: ${r.message || "Unknown error"}`, c.style.display = "none", f = null, p = null;
  } finally {
    o.disabled = !1;
  }
}
async function tt(e) {
  const t = e === "speak" ? b == null ? void 0 : b.name : m == null ? void 0 : m.name;
  if (!t) return;
  const n = document.getElementById(`${e}-status-text`), a = document.getElementById(`${e}-stop-btn`);
  n && (n.textContent = "Stopping..."), a && (a.disabled = !0);
  try {
    const o = await i(`/api/characters/${t}/stop`, "POST");
    n && (o.was_active ? n.textContent = "Stopped" : n.textContent = "Nothing to stop"), e === "chat" && o.was_active && setTimeout(async () => {
      try {
        const c = await ee(t);
        document.getElementById("chat-memory-count").textContent = `Memory: ${c.message_count} messages`, O(c.messages, t);
      } catch (c) {
        console.error("Error refreshing memory after stop:", c);
      }
    }, 500);
  } catch (o) {
    console.error("Stop error:", o), n && (n.textContent = `Stop failed: ${o.message}`);
  } finally {
    a && (a.disabled = !1, a.style.display = "none"), f = null, p = null, k = !1;
    const o = document.getElementById(`${e}-send-btn`);
    o && (o.disabled = !1);
  }
}
const D = document.getElementById("chat-modal"), de = 20, me = 5;
function ne() {
  B = [];
  const e = document.getElementById("chat-image-previews");
  if (e)
    for (; e.firstChild; )
      e.removeChild(e.firstChild);
}
function Ie(e, t) {
  if (B.length >= me) {
    u(`Maximum ${me} images allowed`, "warning");
    return;
  }
  B.push({ data: e, mediaType: t });
  const n = document.getElementById("chat-image-previews"), a = document.createElement("div");
  a.className = "image-preview-thumb", a.dataset.index = B.length - 1;
  const o = document.createElement("img");
  o.src = `data:${t};base64,${e}`;
  const c = document.createElement("button");
  c.className = "remove-btn", c.textContent = "×", c.onclick = function() {
    const r = parseInt(a.dataset.index);
    B.splice(r, 1), a.remove(), document.querySelectorAll("#chat-image-previews .image-preview-thumb").forEach((s, l) => {
      s.dataset.index = l;
    });
  }, a.appendChild(o), a.appendChild(c), n.appendChild(a);
}
async function we(e) {
  if (!e.type.startsWith("image/")) {
    u("Only image files are supported", "error");
    return;
  }
  if (e.size > de * 1024 * 1024) {
    u(`Image too large (max ${de}MB)`, "error");
    return;
  }
  return new Promise((t) => {
    const n = new FileReader();
    n.onload = (a) => {
      const c = a.target.result.split(",")[1], r = e.type || "image/png";
      Ie(c, r), t();
    }, n.readAsDataURL(e);
  });
}
function nt() {
  document.getElementById("chat-image-input").click();
}
async function at(e) {
  const t = e.target.files;
  for (const n of t)
    await we(n);
  e.target.value = "";
}
async function ot() {
  try {
    const e = await navigator.mediaDevices.getDisplayMedia({
      video: { mediaSource: "screen" }
    }), t = document.createElement("video");
    t.srcObject = e, await t.play(), await new Promise((r) => {
      t.readyState >= 2 ? r() : t.onloadeddata = r;
    });
    const n = document.createElement("canvas");
    n.width = t.videoWidth, n.height = t.videoHeight, n.getContext("2d").drawImage(t, 0, 0), e.getTracks().forEach((r) => r.stop());
    const c = n.toDataURL("image/png").split(",")[1];
    Ie(c, "image/png"), u("Screen captured!", "success");
  } catch (e) {
    e.name === "NotAllowedError" ? u("Screen capture permission denied", "warning") : (console.error("Screen capture error:", e), u("Screen capture failed", "error"));
  }
}
function ue(e) {
  var n;
  const t = (n = e.clipboardData) == null ? void 0 : n.items;
  if (t) {
    for (const a of t)
      if (a.type.startsWith("image/")) {
        e.preventDefault();
        const o = a.getAsFile();
        o && we(o);
      }
  }
}
async function ct(e) {
  const t = g.find((a) => a.name === e);
  if (!t) return;
  if (!t.system_prompt) {
    alert('This character has no AI system prompt configured. Use "Speak" for direct TTS.');
    return;
  }
  m = t, document.getElementById("chat-modal-title").textContent = `Chat with ${t.name}`, document.getElementById("chat-message").value = "", document.getElementById("chat-show-text").checked = !0, document.getElementById("chat-include-twitch").checked = !0, document.getElementById("chat-twitch-seconds").value = "", document.getElementById("chat-status").style.display = "none", document.getElementById("chat-twitch-details").style.display = "none", document.getElementById("chat-send-btn").disabled = !1, ne();
  const n = document.getElementById("chat-message");
  n.removeEventListener("paste", ue), n.addEventListener("paste", ue);
  try {
    const a = await ee(e);
    document.getElementById("chat-memory-count").textContent = `Memory: ${a.message_count} messages${t.memory_enabled ? "" : " (disabled)"}`, O(a.messages, e);
  } catch {
    document.getElementById("chat-memory-count").textContent = "Memory: 0 messages", O([], e);
  }
  D.classList.add("active");
}
function Be() {
  D.classList.remove("active"), m = null, ne();
}
async function rt() {
  if (!m) return;
  const e = document.getElementById("chat-message").value.trim(), t = document.getElementById("chat-show-text").checked, n = document.getElementById("chat-include-twitch").checked;
  let a = document.getElementById("chat-twitch-seconds").value;
  if (n || (a = "0"), !e) {
    alert("Please enter a message");
    return;
  }
  const o = document.getElementById("chat-status"), c = document.getElementById("chat-status-text"), r = document.getElementById("chat-send-btn"), s = document.getElementById("chat-stop-btn");
  o.style.display = "block", c.textContent = "Generating...", r.disabled = !0, s.style.display = "inline-block", f = m.name, p = "chat", k = !1;
  try {
    const l = B.length > 0, h = l ? `[${B.length} image(s)] ${e}` : e;
    ie("user", h, m.name), document.getElementById("chat-message").value = "";
    const I = l ? [...B] : null;
    ne();
    const d = await Ve(m.name, e, t, a, I);
    if (d.error || d.detail)
      c.textContent = `Error: ${d.error || d.detail}`, s.style.display = "none", f = null, p = null;
    else {
      if (d.twitch_chat_context) {
        const T = d.twitch_chat_context.split(`
`), ke = T.slice(-4).map((j) => j.length > 60 ? j.substring(0, 57) + "..." : j).join(" | ");
        Xe(`📺 Twitch chat (${T.length}): ${ke}`);
      }
      ie("assistant", d.response_text, m.name);
      let v = "Playing audio...";
      const ae = document.getElementById("chat-twitch-details"), xe = document.getElementById("chat-twitch-summary"), _e = document.getElementById("chat-twitch-context-text");
      if (d.twitch_chat_context) {
        const T = d.twitch_chat_context.split(`
`).length;
        v += ` (${T} chat msgs)`, xe.textContent = `Twitch Chat Context (${T} messages)`, _e.textContent = d.twitch_chat_context, ae.style.display = "block";
      } else
        ae.style.display = "none";
      c.textContent = v, z();
      const Ce = await ee(m.name);
      document.getElementById("chat-memory-count").textContent = `Memory: ${Ce.message_count} messages${m.memory_enabled ? "" : " (not saving)"}`;
    }
  } catch (l) {
    console.error("Chat error:", l), c.textContent = `Error: ${l.message || "Unknown error"}`, s.style.display = "none", f = null, p = null;
  } finally {
    r.disabled = !1;
  }
}
async function st() {
  if (m && confirm(`Clear conversation memory for ${m.name}?`))
    try {
      await Ye(m.name), document.getElementById("chat-memory-count").textContent = "Memory: 0 messages", document.getElementById("chat-status").style.display = "block", document.getElementById("chat-status-text").textContent = "Memory cleared!", O([], m.name), document.getElementById("chat-twitch-details").style.display = "none";
    } catch (e) {
      console.error("Error clearing memory:", e), alert("Error clearing memory");
    }
}
function lt(e) {
  if (!e || e.length === 0) {
    le.innerHTML = '<div class="history-item"><span class="history-content">No history yet</span></div>';
    return;
  }
  le.innerHTML = e.map((t) => {
    const n = new Date(t.timestamp).toLocaleTimeString();
    return `
                <div class="history-item">
                    <span class="history-channel">${w(t.channel)}</span>
                    <span class="history-content">${w(t.content)}</span>
                    <span class="history-time">${w(n)}</span>
                </div>
            `;
  }).join("");
}
function K() {
  if (L) {
    if (g.length === 0) {
      L.innerHTML = `
                <div class="no-channels">
                    <p>No characters configured yet.</p>
                    <p>Click "Create Character" to add one.</p>
                </div>
            `;
      return;
    }
    L.innerHTML = g.map((e) => it(e)).join("");
  }
}
function it(e) {
  var d;
  let t = "", n = "offline";
  e.connected ? e.streaming ? (t = "streaming", n = "streaming") : e.playing ? (t = "playing", n = "playing") : n = "ready" : (t = "", n = "offline");
  const a = e.connected ? "" : "disconnected", o = e.system_prompt ? '<span class="voice-indicator">AI</span>' : "", c = w(e.description || (e.system_prompt ? e.system_prompt.substring(0, 80) + "..." : "No description")), r = w(e.name), s = w(e.icon), l = Le(e.color), h = w(e.model ? e.model.split("/").pop() : ""), I = w(e.tts_provider === "cartesia" ? (((d = e.tts_settings) == null ? void 0 : d.model_id) || "sonic").replace("sonic-", "") : (e.elevenlabs_model_id || "multilingual_v2").replace("eleven_", "").replace("_", " "));
  return `
            <div class="channel-card ${a}" data-character="${r}" style="border-left-color: ${l}">
                <div class="channel-header">
                    <div class="channel-name">
                        <span class="channel-icon">${s}</span>
                        ${r}
                        ${o}
                    </div>
                    <span class="channel-status ${t}">${n}</span>
                </div>
                <p class="channel-description">${c}</p>
                <div class="channel-controls">
                    <div class="control-row" style="font-size: 0.75rem; color: var(--text-secondary);">
                        <span>TTS: ${e.tts_provider === "cartesia" ? "Cartesia" : "ElevenLabs"}</span>
                        <span>${I}</span>
                    </div>
                    ${e.system_prompt ? `<div class="control-row" style="font-size: 0.75rem; color: var(--text-secondary);"><span>AI: ${h}</span></div>` : ""}
                </div>
                <div class="channel-actions">
                    <button data-action="speak" data-character="${r}">Speak</button>
                    ${e.system_prompt ? `<button data-action="chat" data-character="${r}">Chat</button>` : ""}
                    <button data-action="copy-url" data-character="${r}" title="Copy browser source URL for OBS">Copy URL</button>
                    <button data-action="rotate-token" data-character="${r}" title="Invalidate old URL and generate new token">Rotate</button>
                    <button data-action="edit" data-character="${r}">Edit</button>
                    <button class="secondary" data-action="delete" data-character="${r}">Delete</button>
                </div>
            </div>
        `;
}
window.openCreateCharacterModal = Ke;
window.closeCharacterModal = G;
window.editCharacter = async function(e) {
  const t = await i(`/api/characters/${encodeURIComponent(e)}`);
  t && !t.error ? fe(t) : u("Failed to load character", "error");
};
window.deleteCharacter = Oe;
window.openSpeakModal = Ze;
window.closeSpeakModal = Ee;
window.sendSpeak = et;
window.stopGeneration = tt;
window.openChatModal = ct;
window.closeChatModal = Be;
window.sendChat = rt;
window.clearChatMemory = st;
window.attachImage = nt;
window.handleImageSelect = at;
window.captureScreen = ot;
window.previewCharacterTextStyle = Je;
window.stopCharacterTextPreview = te;
window.updateProviderDropdown = he;
window.loadVoiceModels = pe;
window.updateModelInfo = Q;
window.toggleTTSProvider = ge;
window.updateCartesiaVoiceInfo = W;
window.loadCartesiaVoices = Z;
window.selectCartesiaVoice = qe;
window.onCartesiaManualIdChange = We;
window.copyCharacterUrl = async function(e) {
  const t = g.find((a) => a.name === e);
  if (!t || !t.ws_token) {
    u("Character token not found", "error");
    return;
  }
  const n = `${window.location.origin}/channel/${encodeURIComponent(e)}?token=${encodeURIComponent(t.ws_token)}`;
  try {
    await navigator.clipboard.writeText(n);
    const a = document.querySelector(`[data-character="${CSS.escape(e)}"]`);
    if (a) {
      const o = a.querySelector('button[data-action="copy-url"]');
      if (o) {
        const c = o.textContent;
        o.textContent = "Copied!", setTimeout(() => {
          o.textContent = c;
        }, 1500);
      }
    }
  } catch (a) {
    console.error("Failed to copy URL:", a), prompt("Copy this URL for OBS browser source:", n);
  }
};
window.rotateCharacterToken = async function(e) {
  if (confirm(`Rotate token for "${e}"?

This will invalidate any existing OBS browser source URLs. You'll need to update your OBS sources with the new URL.`))
    try {
      const t = await i(`/api/characters/${encodeURIComponent(e)}/rotate-token`, { method: "POST" });
      if (t && t.success) {
        const n = g.find((a) => a.name === e);
        n && (n.ws_token = t.ws_token), u("Token rotated. Copy new URL for OBS.", "success");
      } else
        u((t == null ? void 0 : t.detail) || "Failed to rotate token", "error");
    } catch (t) {
      console.error("Failed to rotate token:", t), u("Failed to rotate token", "error");
    }
};
const V = document.getElementById("twitch-btn"), Y = document.getElementById("twitch-btn-text");
async function be() {
  if (!(!V || !Y))
    try {
      const t = await (await fetch("/api/twitch/status")).json();
      t.connected ? (V.classList.add("connected"), Y.textContent = `#${t.channel}`) : (V.classList.remove("connected"), Y.textContent = "Twitch");
    } catch (e) {
      console.error("Error checking Twitch status:", e);
    }
}
J && J.addEventListener("submit", Qe);
$ && $.addEventListener("click", (e) => {
  e.target === $ && G();
});
A && A.addEventListener("click", (e) => {
  e.target === A && Ee();
});
D && D.addEventListener("click", (e) => {
  e.target === D && Be();
});
L && L.addEventListener("click", (e) => {
  const t = e.target.closest("button[data-action]");
  if (!t) return;
  const n = t.dataset.action, a = t.dataset.character;
  if (a)
    switch (n) {
      case "speak":
        window.openSpeakModal(a);
        break;
      case "chat":
        window.openChatModal(a);
        break;
      case "copy-url":
        window.copyCharacterUrl(a);
        break;
      case "rotate-token":
        window.rotateCharacterToken(a);
        break;
      case "edit":
        window.editCharacter(a);
        break;
      case "delete":
        window.deleteCharacter(a);
        break;
    }
});
ye();
q();
Fe();
z();
be();
Ge();
setInterval(z, 1e4);
setInterval(be, 15e3);
