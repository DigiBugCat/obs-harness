import { TextAnimator as De } from "./text-animator.js";
function l(e) {
  return document.getElementById(e);
}
function o(e) {
  return document.getElementById(e);
}
function m(e) {
  return document.getElementById(e);
}
function A(e) {
  return document.getElementById(e);
}
function b(e) {
  return document.getElementById(e);
}
function be(e) {
  return document.getElementById(e);
}
function Ne(e) {
  return document.getElementById(e);
}
let y = null, M = null, T = 0;
const Re = 1e3, Fe = 3e4, O = 10, ue = 6e4, Ue = 3e4;
let z = Date.now(), N = null, D = null, he = [], w = [], C = null, p = null, $ = null, q = [], x = null, g = null, B = !1, S = [], te = null;
const me = document.getElementById("ws-status"), pe = document.getElementById("ws-status-text"), R = document.getElementById("characters-container"), fe = document.getElementById("history-list");
function I(e) {
  if (e == null) return "";
  const t = document.createElement("div");
  return t.textContent = String(e), t.innerHTML;
}
function He(e, t = "#9146ff") {
  return e && /^#[0-9a-fA-F]{3,4}$|^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$/.test(e) ? e : t;
}
function Oe() {
  return te;
}
function _e() {
  const t = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/dashboard`;
  y = new WebSocket(t), y.onopen = () => {
    me.classList.add("connected"), pe.textContent = "Connected", T = 0, z = Date.now(), qe(), M && (clearTimeout(M), M = null);
  }, y.onclose = () => {
    me.classList.remove("connected"), pe.textContent = "Disconnected", ze(), Ge();
  }, y.onerror = (n) => {
    console.error("Dashboard WebSocket error:", n);
  }, y.onmessage = (n) => {
    try {
      const a = JSON.parse(n.data);
      We(a);
    } catch (a) {
      console.error("Error parsing message:", a);
    }
  };
}
function Ge() {
  if (!M) {
    if (T >= O) {
      console.log(`[dashboard] Max reconnect attempts (${O}) reached, reloading page...`), location.reload();
      return;
    }
    const e = Math.min(
      Re * Math.pow(2, T),
      Fe
    );
    T++, console.log(`[dashboard] Reconnecting in ${e}ms (attempt ${T}/${O})...`), M = setTimeout(() => {
      M = null, _e();
    }, e);
  }
}
function ze() {
  N || (N = setInterval(async () => {
    if (!(y && y.readyState === WebSocket.OPEN))
      try {
        (await fetch("/health", { signal: AbortSignal.timeout(5e3) })).ok && T >= O / 2 && (console.log("[dashboard] Server healthy but WebSocket failing, reloading page..."), location.reload());
      } catch {
      }
  }, Ue));
}
function qe() {
  N && (clearInterval(N), N = null);
}
setInterval(() => {
  y && y.readyState === WebSocket.OPEN && Date.now() - z > ue && (console.log(`[dashboard] No ping received in ${ue}ms, connection stale - reconnecting...`), z = Date.now(), y.close());
}, 1e4);
function We(e) {
  if (e.type === "ping") {
    y && y.readyState === WebSocket.OPEN && y.send(JSON.stringify({ event: "pong", ts: e.ts })), z = Date.now();
    return;
  }
  if (e.type === "hello") {
    const t = e.build_id;
    if (e.tenant_id && (te = e.tenant_id, console.log(`[dashboard] Tenant ID: ${te}`)), D === null)
      D = t ?? null, console.log(`[dashboard] Server build ID: ${D}`);
    else if (D !== t) {
      console.log(`[dashboard] Server version changed (${D} -> ${t}), refreshing page...`), location.reload();
      return;
    } else
      console.log("[dashboard] Reconnected to same server version");
    return;
  }
  if (e.type === "characters") {
    const t = Oe(), n = e.characters, a = new Map(n.map((r) => [r.name, r]));
    if (w = w.map((r) => {
      var s, i;
      const c = `${t}:${r.name}`;
      return {
        ...r,
        connected: a.has(c),
        playing: ((s = a.get(c)) == null ? void 0 : s.playing) || !1,
        streaming: ((i = a.get(c)) == null ? void 0 : i.streaming) || !1
      };
    }), ne(), x && g) {
      const r = `${t}:${x}`, c = a.get(r);
      if (c && (c.streaming && (B = !0), B && !c.streaming)) {
        const s = document.getElementById(`${g}-stop-btn`), i = document.getElementById(`${g}-status-text`);
        s && (s.style.display = "none"), i && (i.textContent = "Complete!"), x = null, g = null, B = !1;
      }
    }
  } else e.type === "character_sync" && (w = e.characters, ne(), U || console.log("Character data synced from server"), U = !1);
}
let U = !1;
function f(e, t = "info", n = 4e3) {
  const a = document.querySelector(".toast-notification");
  a && a.remove();
  const r = document.createElement("div");
  r.className = `toast-notification toast-${t}`, r.textContent = e, document.body.appendChild(r), setTimeout(() => {
    r.classList.add("hiding"), setTimeout(() => r.remove(), 300);
  }, n);
}
async function u(e, t = "GET", n = null, a = !0) {
  const r = {
    method: t,
    headers: { "Content-Type": "application/json" }
  };
  n && (r.body = JSON.stringify(n));
  try {
    const c = await fetch(e, r), s = await c.json();
    if (!c.ok) {
      const i = s.detail || s.error || `HTTP ${c.status}`;
      return a && f(`API Error: ${i}`, "error"), console.error(`API Error [${t} ${e}]:`, i), { error: i, status: c.status };
    }
    return s;
  } catch (c) {
    const s = c.message || "Network error";
    return a && f(`Connection Error: ${s}`, "error"), console.error(`Fetch Error [${t} ${e}]:`, c), { error: s, networkError: !0 };
  }
}
async function je() {
  const e = await u("/api/presets");
  return Array.isArray(e) && (he = e), he;
}
async function X() {
  const e = await u("/api/history");
  Array.isArray(e) && vt(e);
}
async function J() {
  const e = await u("/api/characters");
  return Array.isArray(e) && (w = e, ne()), w;
}
async function Ve(e) {
  U = !0;
  const t = await u("/api/characters", "POST", e);
  return await J(), t;
}
async function Ye(e, t, n = !0) {
  U = !0;
  const a = await u(`/api/characters/${e}`, "PUT", t, n);
  return await J(), a;
}
async function Xe(e) {
  confirm(`Delete character "${e}"? This cannot be undone.`) && (U = !0, await u(`/api/characters/${e}`, "DELETE"), await J());
}
async function xe(e) {
  const t = document.getElementById("character-provider");
  if (t) {
    if (t.innerHTML = '<option value="">Loading providers...</option>', t.disabled = !0, !e || e.trim() === "") {
      t.innerHTML = '<option value="">Default (auto)</option>', t.disabled = !1;
      return;
    }
    try {
      const n = await u(`/api/openrouter/models/${encodeURIComponent(e)}/providers`, "GET", null, !1);
      if (t.innerHTML = '<option value="">Default (auto)</option>', n.providers && n.providers.length > 0)
        for (const a of n.providers) {
          const r = document.createElement("option");
          r.value = a, r.textContent = a, t.appendChild(r);
        }
    } catch (n) {
      console.error("Error fetching providers:", n), t.innerHTML = '<option value="">Default (auto)</option>';
    } finally {
      t.disabled = !1;
    }
  }
}
async function Je() {
  const e = document.getElementById("character-tts-model");
  if (e)
    try {
      const t = await u("/api/elevenlabs/models", "GET", null, !1);
      Array.isArray(t) && (q = t, e.innerHTML = t.map((n) => {
        const a = n.name || n.model_id;
        return `<option value="${n.model_id}">${a}</option>`;
      }).join(""));
    } catch (t) {
      console.error("Error fetching ElevenLabs models:", t);
    }
}
async function Ce(e) {
  const t = m("character-tts-model"), n = document.getElementById("tts-model-info");
  if (!(!t || !e)) {
    n && (n.textContent = "");
    try {
      const a = await u(`/api/elevenlabs/voices/${e}`, "GET", null, !1);
      if (a != null && a.high_quality_base_model_ids && a.high_quality_base_model_ids.length > 0) {
        const r = new Set(a.high_quality_base_model_ids);
        Array.from(t.options).forEach((c) => {
          if (r.has(c.value)) {
            const s = q.find((i) => i.model_id === c.value);
            c.textContent = `${(s == null ? void 0 : s.name) || c.value} (Recommended)`;
          } else {
            const s = q.find((i) => i.model_id === c.value);
            c.textContent = (s == null ? void 0 : s.name) || c.value;
          }
        }), n && (n.textContent = `Voice "${a.name}" is optimized for: ${a.high_quality_base_model_ids.join(", ")}`);
      }
    } catch (a) {
      console.error("Error fetching voice info:", a), n && (n.textContent = "Could not fetch voice info");
    }
  }
}
const Ke = {
  eleven_v3: "Latest flagship model with emotionally rich, expressive speech. 70+ languages. Best for audiobooks & dramatic content. Not optimized for real-time.",
  eleven_multilingual_v2: "Advanced emotionally-aware synthesis. 29 languages. Most stable for long-form. Higher latency but best quality.",
  eleven_flash_v2_5: "Fastest model (~75ms latency). 32 languages. 50% lower cost. Best for real-time agents & bulk processing.",
  eleven_turbo_v2_5: "Balanced quality & speed (~250ms). 32 languages. Good middle-ground between Flash and Multilingual.",
  eleven_flash_v2: "Ultra-fast for real-time (~75ms). English only. Great for conversational agents.",
  eleven_turbo_v2: "Quality-focused with low latency (~250ms). English only. Good balance for English projects.",
  eleven_multilingual_v1: "Legacy multilingual model. Use v2 for better results.",
  eleven_monolingual_v1: "Legacy English model. Use newer models for better quality."
};
function oe(e) {
  const t = document.getElementById("tts-model-info"), n = document.getElementById("voice-style-row"), a = document.getElementById("voice-similarity-row"), r = q.find((c) => c.model_id === e);
  r && (n && (n.style.display = r.can_use_style ? "" : "none"), a && (a.style.display = r.can_use_speaker_boost ? "" : "none"), t && (t.textContent = Ke[e] || ""));
}
let W = [];
async function re() {
  try {
    W = await u("/api/cartesia/voices", "GET", null, !1);
    const e = document.getElementById("cartesia-voice-select");
    if (!e) return;
    e.innerHTML = '<option value="">-- Select a voice --</option>', W.forEach((t) => {
      const n = document.createElement("option");
      n.value = t.voice_id, n.textContent = `${t.name} (${t.language})`, e.appendChild(n);
    });
  } catch (e) {
    console.error("Error loading Cartesia voices:", e);
    const t = document.getElementById("cartesia-voice-select");
    t && (t.innerHTML = '<option value="">Failed to load voices</option>');
  }
}
function Qe(e) {
  const t = document.getElementById("cartesia-voice-id");
  t && e && (t.value = e), K(e);
}
function Ze(e) {
  const t = document.getElementById("cartesia-voice-select");
  if (t && e)
    if (Array.from(t.options).find((a) => a.value === e))
      t.value = e, K(e);
    else {
      t.value = "";
      const a = document.getElementById("cartesia-voice-info");
      a && (a.textContent = "Custom voice ID");
    }
}
function K(e) {
  const t = document.getElementById("cartesia-voice-info");
  if (!t) return;
  if (!e) {
    t.textContent = "";
    return;
  }
  const n = W.find((a) => a.voice_id === e);
  n && n.description ? t.textContent = n.description : t.textContent = "";
}
function Ee(e) {
  const t = document.getElementById("elevenlabs-settings"), n = document.getElementById("cartesia-settings");
  e === "cartesia" ? (t && (t.style.display = "none"), n && (n.style.display = "block"), W.length === 0 && re()) : (t && (t.style.display = "block"), n && (n.style.display = "none"));
}
async function et(e, t, n) {
  return u(`/api/characters/${e}/speak`, "POST", {
    text: t,
    show_text: n
  });
}
async function tt(e, t, n, a = null, r = null) {
  const c = {
    message: t,
    show_text: n
  };
  return a !== null && a !== "" && (c.twitch_chat_seconds = parseInt(a)), r && r.length > 0 && (c.images = r.map((s) => ({
    data: s.data,
    media_type: s.mediaType
  }))), u(`/api/characters/${e}/chat`, "POST", c);
}
async function ce(e) {
  return u(`/api/characters/${e}/memory`);
}
async function at(e) {
  return u(`/api/characters/${e}/memory`, "DELETE");
}
function j(e, t) {
  const n = document.getElementById("chat-history"), a = document.getElementById("chat-history-empty");
  if (!e || e.length === 0) {
    a && (a.style.display = "block"), n == null || n.querySelectorAll(".chat-bubble").forEach((r) => r.remove());
    return;
  }
  a && (a.style.display = "none"), n == null || n.querySelectorAll(".chat-bubble").forEach((r) => r.remove()), e.forEach((r) => {
    if (r.role === "context") {
      const c = r.content.split(`
`), s = c.slice(-4).map((v) => v.length > 60 ? v.substring(0, 57) + "..." : v).join(" | "), i = document.createElement("div");
      i.className = "chat-bubble context";
      const d = document.createElement("div");
      d.className = "chat-bubble-content", d.textContent = `📺 Twitch (${c.length}): ${s}`, i.appendChild(d), n == null || n.appendChild(i);
    } else {
      const c = document.createElement("div");
      c.className = `chat-bubble ${r.role}`;
      const s = document.createElement("div");
      s.className = "chat-bubble-label", s.textContent = r.role === "user" ? "You" : t;
      const i = document.createElement("div");
      if (i.className = "chat-bubble-content", r.interrupted && r.generated_text) {
        const d = r.content || "", v = r.generated_text || "";
        if (d) {
          const _ = document.createElement("span");
          _.textContent = d, i.appendChild(_);
        }
        let k = "";
        if ((v.startsWith(d) || v.length > d.length) && (k = v.substring(d.length).trim()), k) {
          const _ = document.createElement("span");
          _.style.textDecoration = "line-through", _.style.opacity = "0.6", _.textContent = " " + k, i.appendChild(_);
        }
        const h = document.createElement("span");
        h.style.cssText = "display: inline-block; margin-left: 8px; padding: 2px 6px; background: #ff6b6b33; color: #ff6b6b; border-radius: 4px; font-size: 0.7rem;", h.textContent = "⚡ interrupted", i.appendChild(h);
      } else
        i.textContent = r.content;
      c.appendChild(s), c.appendChild(i), n == null || n.appendChild(c);
    }
  }), n && (n.scrollTop = n.scrollHeight);
}
function ve(e, t, n) {
  const a = document.getElementById("chat-history"), r = document.getElementById("chat-history-empty");
  r && (r.style.display = "none");
  const c = document.createElement("div");
  c.className = `chat-bubble ${e}`;
  const s = document.createElement("div");
  s.className = "chat-bubble-label", s.textContent = e === "user" ? "You" : n;
  const i = document.createElement("div");
  i.className = "chat-bubble-content", i.textContent = t, c.appendChild(s), c.appendChild(i), a == null || a.appendChild(c), a && (a.scrollTop = a.scrollHeight);
}
function nt(e) {
  const t = document.getElementById("chat-history"), n = document.getElementById("chat-history-empty");
  n && (n.style.display = "none");
  const a = document.createElement("div");
  a.className = "chat-bubble context";
  const r = document.createElement("div");
  r.className = "chat-bubble-content", r.textContent = e, a.appendChild(r), t == null || t.appendChild(a), t && (t.scrollTop = t.scrollHeight);
}
let V = null, G = null;
function ot() {
  se();
  const e = be("character-preview-canvas");
  if (!e) return;
  const t = e.getContext("2d");
  V = new De(t, e.width, e.height);
  const n = V, a = {
    style: o("character-text-style").value,
    fontFamily: o("character-font-family").value,
    fontSize: parseInt(o("character-font-size").value),
    duration: parseInt(o("character-text-duration").value),
    color: o("character-text-color").value,
    strokeColor: o("character-stroke-color").value,
    strokeWidth: parseInt(o("character-stroke-width").value),
    positionX: parseInt(o("character-position-x").value) / 100,
    positionY: parseInt(o("character-position-y").value) / 100
  }, r = e.width / 800;
  n.show({
    text: "Sample Text",
    style: a.style,
    duration: a.duration,
    x: a.positionX,
    y: a.positionY,
    fontFamily: a.fontFamily,
    fontSize: Math.round(a.fontSize * r),
    color: a.color,
    strokeColor: a.strokeWidth > 0 ? a.strokeColor : null,
    strokeWidth: Math.round(a.strokeWidth * r)
  });
  function c() {
    t.clearRect(0, 0, e.width, e.height), n.update(), n.draw(), n.isAnimating() && (G = requestAnimationFrame(c));
  }
  c();
}
function se() {
  G && (cancelAnimationFrame(G), G = null), V && V.clear();
  const e = be("character-preview-canvas");
  if (e) {
    const t = e.getContext("2d");
    t == null || t.clearRect(0, 0, e.width, e.height);
  }
}
const L = l("character-modal"), ae = Ne("character-form"), ke = l("character-modal-title");
function rt() {
  C = null, ke.textContent = "Create Character", ae.reset(), o("character-name").disabled = !1, o("character-color").value = "#e94560", o("character-icon").value = "🔊", o("character-stability").value = "50", l("character-stability-value").textContent = "0.50", o("character-similarity").value = "75", l("character-similarity-value").textContent = "0.75", o("character-voice-style").value = "0", l("character-style-value").textContent = "0.00", o("character-voice-speed").value = "100", l("character-speed-value").textContent = "1.0", o("character-volume").value = "100", l("character-volume-value").textContent = "100", m("character-text-style").value = "typewriter", o("character-font-family").value = "Arial", o("character-font-size").value = "48", o("character-text-duration").value = "3000", o("character-text-color").value = "#ffffff", o("character-stroke-color").value = "#000000", o("character-stroke-width").value = "0", l("character-stroke-width-value").textContent = "0", o("character-position-x").value = "50", l("character-pos-x-value").textContent = "50", o("character-position-y").value = "50", l("character-pos-y-value").textContent = "50", o("character-model").value = "anthropic/claude-sonnet-4.5", m("character-provider").innerHTML = '<option value="">Default (auto)</option>', m("character-provider").value = "", o("character-temperature").value = "70", l("character-temp-value").textContent = "0.7", o("character-max-tokens").value = "1024", m("character-tts-model").value = "eleven_multilingual_v2", l("tts-model-info").textContent = "", oe("eleven_multilingual_v2"), o("character-memory-enabled").checked = !1, o("character-persist-memory").checked = !1, o("character-twitch-chat-enabled").checked = !1, o("character-twitch-chat-seconds").value = "60", o("character-twitch-chat-max").value = "20", L.classList.add("active");
}
function Ie(e) {
  C = e, ke.textContent = "Edit Character";
  const t = e;
  o("character-name").value = e.name, o("character-name").disabled = !0, b("character-description").value = t.description || "", o("character-color").value = t.color, o("character-icon").value = t.icon;
  const n = e.tts_provider || "elevenlabs";
  if (m("character-tts-provider").value = n, Ee(n), n === "cartesia" && e.tts_settings)
    re().then(() => {
      const a = e.tts_settings, r = a.voice_id || "";
      o("cartesia-voice-id").value = r;
      const c = m("cartesia-voice-select");
      c && r && Array.from(c.options).find((v) => v.value === r) && (c.value = r), o("cartesia-model-id").value = a.model_id || "sonic-2024-12-12", m("cartesia-language").value = a.language || "en";
      const s = a.speed || 1, i = Math.max(0.6, Math.min(1.5, s));
      o("cartesia-speed").value = String(Math.round(i * 100)), l("cartesia-speed-value").textContent = i.toFixed(1), s !== i && console.warn(`Cartesia speed ${s} was clamped to ${i} (valid: 0.6-1.5)`), K(r);
    });
  else {
    const a = e.tts_settings || {};
    o("character-voice-id").value = a.voice_id || t.elevenlabs_voice_id;
    const r = a.model_id || t.elevenlabs_model_id || "eleven_multilingual_v2";
    m("character-tts-model").value = r, oe(r), Ce(a.voice_id || t.elevenlabs_voice_id);
    const c = a.stability ?? t.voice_stability;
    o("character-stability").value = String(Math.round(c * 100)), l("character-stability-value").textContent = c.toFixed(2);
    const s = a.similarity_boost ?? t.voice_similarity_boost;
    o("character-similarity").value = String(Math.round(s * 100)), l("character-similarity-value").textContent = s.toFixed(2);
    const i = a.style ?? t.voice_style;
    o("character-voice-style").value = String(Math.round(i * 100)), l("character-style-value").textContent = i.toFixed(2);
    const d = a.speed ?? t.voice_speed;
    o("character-voice-speed").value = String(Math.round(d * 100)), l("character-speed-value").textContent = d.toFixed(1);
  }
  o("character-volume").value = String(Math.round(t.default_volume * 100)), l("character-volume-value").textContent = String(Math.round(t.default_volume * 100)), o("character-muted").checked = t.mute_state, m("character-text-style").value = t.default_text_style, o("character-font-family").value = e.text_font_family || "Arial", o("character-font-size").value = String(e.text_font_size || 48), o("character-text-duration").value = String(t.text_duration), o("character-text-color").value = e.text_color || "#ffffff", o("character-stroke-color").value = e.text_stroke_color || "#000000", o("character-stroke-width").value = String(e.text_stroke_width || 0), l("character-stroke-width-value").textContent = String(e.text_stroke_width || 0), o("character-position-x").value = String(Math.round((e.text_position_x || 0.5) * 100)), l("character-pos-x-value").textContent = String(Math.round((e.text_position_x || 0.5) * 100)), o("character-position-y").value = String(Math.round((e.text_position_y || 0.5) * 100)), l("character-pos-y-value").textContent = String(Math.round((e.text_position_y || 0.5) * 100)), b("character-prompt").value = e.system_prompt || "", o("character-model").value = e.openrouter_model || "", xe(e.openrouter_model || "").then(() => {
    m("character-provider").value = t.provider || "";
  }), o("character-temperature").value = String(Math.round(t.temperature * 100)), l("character-temp-value").textContent = t.temperature.toFixed(1), o("character-max-tokens").value = String(t.max_tokens), o("character-memory-enabled").checked = t.memory_enabled || !1, o("character-persist-memory").checked = e.persist_memory || !1, o("character-twitch-chat-enabled").checked = t.twitch_chat_enabled || !1, o("character-twitch-chat-seconds").value = String(t.twitch_chat_window_seconds || 60), o("character-twitch-chat-max").value = String(t.twitch_chat_max_messages || 20), L.classList.add("active");
}
function Y() {
  L.classList.remove("active"), C = null, se();
}
async function ct(e) {
  e.preventDefault();
  const t = m("character-tts-provider").value;
  let n = null;
  t === "cartesia" ? n = {
    voice_id: o("cartesia-voice-id").value,
    model_id: o("cartesia-model-id").value,
    language: m("cartesia-language").value,
    speed: parseInt(o("cartesia-speed").value) / 100
  } : n = {
    voice_id: o("character-voice-id").value,
    model_id: m("character-tts-model").value,
    stability: parseInt(o("character-stability").value) / 100,
    similarity_boost: parseInt(o("character-similarity").value) / 100,
    style: parseInt(o("character-voice-style").value) / 100,
    speed: parseInt(o("character-voice-speed").value) / 100
  };
  const a = {
    name: o("character-name").value,
    description: b("character-description").value || null,
    color: o("character-color").value,
    icon: o("character-icon").value,
    // TTS provider abstraction
    tts_provider: t,
    tts_settings: n,
    // Legacy ElevenLabs fields (for backwards compatibility)
    elevenlabs_voice_id: o("character-voice-id").value,
    elevenlabs_model_id: m("character-tts-model").value,
    voice_stability: parseInt(o("character-stability").value) / 100,
    voice_similarity_boost: parseInt(o("character-similarity").value) / 100,
    voice_style: parseInt(o("character-voice-style").value) / 100,
    voice_speed: parseInt(o("character-voice-speed").value) / 100,
    default_volume: parseInt(o("character-volume").value) / 100,
    mute_state: o("character-muted").checked,
    default_text_style: m("character-text-style").value,
    text_font_family: o("character-font-family").value,
    text_font_size: parseInt(o("character-font-size").value),
    text_duration: parseInt(o("character-text-duration").value),
    text_color: o("character-text-color").value,
    text_stroke_color: parseInt(o("character-stroke-width").value) > 0 ? o("character-stroke-color").value : null,
    text_stroke_width: parseInt(o("character-stroke-width").value),
    text_position_x: parseInt(o("character-position-x").value) / 100,
    text_position_y: parseInt(o("character-position-y").value) / 100,
    system_prompt: b("character-prompt").value || null,
    model: o("character-model").value,
    provider: m("character-provider").value || null,
    temperature: parseInt(o("character-temperature").value) / 100,
    max_tokens: parseInt(o("character-max-tokens").value),
    memory_enabled: o("character-memory-enabled").checked,
    persist_memory: o("character-persist-memory").checked,
    twitch_chat_enabled: o("character-twitch-chat-enabled").checked,
    twitch_chat_window_seconds: parseInt(o("character-twitch-chat-seconds").value),
    twitch_chat_max_messages: parseInt(o("character-twitch-chat-max").value),
    // Optimistic concurrency control - send timestamp to detect conflicts
    expected_updated_at: (C == null ? void 0 : C.updated_at) || null
  };
  try {
    if (C) {
      const r = await Ye(C.name, a, !1);
      if (r && r.status === 409) {
        const c = await u(`/api/characters/${encodeURIComponent(C.name)}`, "GET", null, !1);
        c && !("error" in c) ? (Ie(c), f("Someone else modified this character. Please review the updated values and try again.", "warning")) : (Y(), f("Character was modified. Please try again.", "warning"));
        return;
      }
    } else
      await Ve(a);
    Y();
  } catch (r) {
    console.error("Error saving character:", r), alert("Error saving character. Check console for details.");
  }
}
const F = l("speak-modal");
function st(e) {
  const t = w.find((n) => n.name === e);
  t && ($ = t, l("speak-modal-title").textContent = `Speak as ${t.name}`, b("speak-text").value = "", o("speak-show-text").checked = !0, l("speak-status").style.display = "none", A("speak-send-btn").disabled = !1, F.classList.add("active"));
}
function Se() {
  F.classList.remove("active"), $ = null;
}
async function it() {
  if (!$) return;
  const e = b("speak-text").value.trim(), t = o("speak-show-text").checked;
  if (!e) {
    alert("Please enter text to speak");
    return;
  }
  const n = l("speak-status"), a = l("speak-status-text"), r = A("speak-send-btn"), c = A("speak-stop-btn");
  n.style.display = "block", a.textContent = "Speaking...", r.disabled = !0, c.style.display = "inline-block", x = $.name, g = "speak", B = !1;
  try {
    const s = await et($.name, e, t);
    s.error || s.detail ? (a.textContent = `Error: ${s.error || s.detail}`, c.style.display = "none", x = null, g = null) : (a.textContent = "Playing audio...", b("speak-text").value = "", X());
  } catch (s) {
    console.error("Speak error:", s), a.textContent = `Error: ${s.message || "Unknown error"}`, c.style.display = "none", x = null, g = null;
  } finally {
    r.disabled = !1;
  }
}
async function lt(e) {
  const t = e === "speak" ? $ == null ? void 0 : $.name : p == null ? void 0 : p.name;
  if (!t) return;
  const n = document.getElementById(`${e}-status-text`), a = document.getElementById(`${e}-stop-btn`);
  n && (n.textContent = "Stopping..."), a && (a.disabled = !0);
  try {
    const r = await u(`/api/characters/${t}/stop`, "POST");
    n && (r.was_active ? n.textContent = "Stopped" : n.textContent = "Nothing to stop"), e === "chat" && r.was_active && setTimeout(async () => {
      try {
        const c = await ce(t);
        l("chat-memory-count").textContent = `Memory: ${c.message_count} messages`, j(c.messages, t);
      } catch (c) {
        console.error("Error refreshing memory after stop:", c);
      }
    }, 500);
  } catch (r) {
    console.error("Stop error:", r), n && (n.textContent = `Stop failed: ${r.message}`);
  } finally {
    a && (a.disabled = !1, a.style.display = "none"), x = null, g = null, B = !1;
    const r = document.getElementById(`${e}-send-btn`);
    r && (r.disabled = !1);
  }
}
const E = document.getElementById("chat-modal"), ye = 20, ge = 5;
function ie() {
  S = [];
  const e = document.getElementById("chat-image-previews");
  if (e)
    for (; e.firstChild; )
      e.removeChild(e.firstChild);
}
function $e(e, t) {
  if (S.length >= ge) {
    f(`Maximum ${ge} images allowed`, "warning");
    return;
  }
  S.push({ data: e, mediaType: t });
  const n = l("chat-image-previews"), a = document.createElement("div");
  a.className = "image-preview-thumb", a.dataset.index = String(S.length - 1);
  const r = document.createElement("img");
  r.src = `data:${t};base64,${e}`;
  const c = document.createElement("button");
  c.className = "remove-btn", c.textContent = "×", c.onclick = function() {
    const s = parseInt(a.dataset.index || "0");
    S.splice(s, 1), a.remove(), document.querySelectorAll("#chat-image-previews .image-preview-thumb").forEach((i, d) => {
      i.dataset.index = String(d);
    });
  }, a.appendChild(r), a.appendChild(c), n.appendChild(a);
}
async function Te(e) {
  if (!e.type.startsWith("image/")) {
    f("Only image files are supported", "error");
    return;
  }
  if (e.size > ye * 1024 * 1024) {
    f(`Image too large (max ${ye}MB)`, "error");
    return;
  }
  return new Promise((t) => {
    const n = new FileReader();
    n.onload = (a) => {
      var i;
      const c = ((i = a.target) == null ? void 0 : i.result).split(",")[1], s = e.type || "image/png";
      $e(c, s), t();
    }, n.readAsDataURL(e);
  });
}
function dt() {
  o("chat-image-input").click();
}
async function ut(e) {
  const t = e.target, n = t.files;
  if (n)
    for (const a of n)
      await Te(a);
  t.value = "";
}
async function ht() {
  try {
    const e = await navigator.mediaDevices.getDisplayMedia({
      video: !0
    }), t = document.createElement("video");
    t.srcObject = e, await t.play(), await new Promise((s) => {
      t.readyState >= 2 ? s() : t.onloadeddata = () => s();
    });
    const n = document.createElement("canvas");
    n.width = t.videoWidth, n.height = t.videoHeight, n.getContext("2d").drawImage(t, 0, 0), e.getTracks().forEach((s) => s.stop());
    const c = n.toDataURL("image/png").split(",")[1];
    $e(c, "image/png"), f("Screen captured!", "success");
  } catch (e) {
    e instanceof Error && e.name === "NotAllowedError" ? f("Screen capture permission denied", "warning") : (console.error("Screen capture error:", e), f("Screen capture failed", "error"));
  }
}
function we(e) {
  var n;
  const t = (n = e.clipboardData) == null ? void 0 : n.items;
  if (t) {
    for (const a of t)
      if (a.type.startsWith("image/")) {
        e.preventDefault();
        const r = a.getAsFile();
        r && Te(r);
      }
  }
}
async function mt(e) {
  const t = w.find((a) => a.name === e);
  if (!t) return;
  if (!t.system_prompt) {
    alert('This character has no AI system prompt configured. Use "Speak" for direct TTS.');
    return;
  }
  p = t, l("chat-modal-title").textContent = `Chat with ${t.name}`, b("chat-message").value = "", o("chat-show-text").checked = !0, o("chat-include-twitch").checked = !0, o("chat-twitch-seconds").value = "", l("chat-status").style.display = "none", l("chat-twitch-details").style.display = "none", A("chat-send-btn").disabled = !1, ie();
  const n = b("chat-message");
  n.removeEventListener("paste", we), n.addEventListener("paste", we);
  try {
    const a = await ce(e);
    l("chat-memory-count").textContent = `Memory: ${a.message_count} messages${t.memory_enabled ? "" : " (disabled)"}`, j(a.messages, e);
  } catch {
    l("chat-memory-count").textContent = "Memory: 0 messages", j([], e);
  }
  E == null || E.classList.add("active");
}
function Me() {
  E == null || E.classList.remove("active"), p = null, ie();
}
async function pt() {
  if (!p) return;
  const e = b("chat-message").value.trim(), t = o("chat-show-text").checked, n = o("chat-include-twitch").checked;
  let a = o("chat-twitch-seconds").value;
  if (n || (a = "0"), !e) {
    alert("Please enter a message");
    return;
  }
  const r = l("chat-status"), c = l("chat-status-text"), s = A("chat-send-btn"), i = A("chat-stop-btn");
  r.style.display = "block", c.textContent = "Generating...", s.disabled = !0, i.style.display = "inline-block", x = p.name, g = "chat", B = !1;
  try {
    const d = S.length > 0, v = d ? `[${S.length} image(s)] ${e}` : e;
    ve("user", v, p.name), b("chat-message").value = "";
    const k = d ? [...S] : null;
    ie();
    const h = await tt(p.name, e, t, a, k);
    if (h.error || h.detail)
      c.textContent = `Error: ${h.error || h.detail}`, i.style.display = "none", x = null, g = null;
    else {
      if (h.twitch_chat_context) {
        const P = h.twitch_chat_context.split(`
`), Pe = P.slice(-4).map((Q) => Q.length > 60 ? Q.substring(0, 57) + "..." : Q).join(" | ");
        nt(`📺 Twitch chat (${P.length}): ${Pe}`);
      }
      ve("assistant", h.response_text || "", p.name);
      let _ = "Playing audio...";
      const H = document.getElementById("chat-twitch-details"), le = document.getElementById("chat-twitch-summary"), de = document.getElementById("chat-twitch-context-text");
      if (h.twitch_chat_context) {
        const P = h.twitch_chat_context.split(`
`).length;
        _ += ` (${P} chat msgs)`, le && (le.textContent = `Twitch Chat Context (${P} messages)`), de && (de.textContent = h.twitch_chat_context), H && (H.style.display = "block");
      } else
        H && (H.style.display = "none");
      c.textContent = _, X();
      const Le = await ce(p.name), Ae = p;
      l("chat-memory-count").textContent = `Memory: ${Le.message_count} messages${Ae.memory_enabled ? "" : " (not saving)"}`;
    }
  } catch (d) {
    console.error("Chat error:", d), c.textContent = `Error: ${d instanceof Error ? d.message : "Unknown error"}`, i.style.display = "none", x = null, g = null;
  } finally {
    s.disabled = !1;
  }
}
async function ft() {
  if (p && confirm(`Clear conversation memory for ${p.name}?`))
    try {
      await at(p.name);
      const e = document.getElementById("chat-memory-count"), t = document.getElementById("chat-status"), n = document.getElementById("chat-status-text"), a = document.getElementById("chat-twitch-details");
      e && (e.textContent = "Memory: 0 messages"), t && (t.style.display = "block"), n && (n.textContent = "Memory cleared!"), j([], p.name), a && (a.style.display = "none");
    } catch (e) {
      console.error("Error clearing memory:", e), alert("Error clearing memory");
    }
}
function vt(e) {
  if (!e || e.length === 0) {
    fe.innerHTML = '<div class="history-item"><span class="history-content">No history yet</span></div>';
    return;
  }
  fe.innerHTML = e.map((t) => {
    const n = new Date(t.timestamp).toLocaleTimeString();
    return `
                <div class="history-item">
                    <span class="history-channel">${I(t.channel)}</span>
                    <span class="history-content">${I(t.content)}</span>
                    <span class="history-time">${I(n)}</span>
                </div>
            `;
  }).join("");
}
function ne() {
  if (R) {
    if (w.length === 0) {
      R.innerHTML = `
                <div class="no-channels">
                    <p>No characters configured yet.</p>
                    <p>Click "Create Character" to add one.</p>
                </div>
            `;
      return;
    }
    R.innerHTML = w.map((e) => yt(e)).join("");
  }
}
function yt(e) {
  var h;
  let t = "", n = "offline";
  e.connected ? e.streaming ? (t = "streaming", n = "streaming") : e.playing ? (t = "playing", n = "playing") : n = "ready" : (t = "", n = "offline");
  const a = e.connected ? "" : "disconnected", r = e.system_prompt ? '<span class="voice-indicator">AI</span>' : "", c = I(e.description || (e.system_prompt ? e.system_prompt.substring(0, 80) + "..." : "No description")), s = I(e.name), i = I(e.icon), d = He(e.color), v = I(e.model ? e.model.split("/").pop() : ""), k = I(e.tts_provider === "cartesia" ? (((h = e.tts_settings) == null ? void 0 : h.model_id) || "sonic").replace("sonic-", "") : (e.elevenlabs_model_id || "multilingual_v2").replace("eleven_", "").replace("_", " "));
  return `
            <div class="channel-card ${a}" data-character="${s}" style="border-left-color: ${d}">
                <div class="channel-header">
                    <div class="channel-name">
                        <span class="channel-icon">${i}</span>
                        ${s}
                        ${r}
                    </div>
                    <span class="channel-status ${t}">${n}</span>
                </div>
                <p class="channel-description">${c}</p>
                <div class="channel-controls">
                    <div class="control-row" style="font-size: 0.75rem; color: var(--text-secondary);">
                        <span>TTS: ${e.tts_provider === "cartesia" ? "Cartesia" : "ElevenLabs"}</span>
                        <span>${k}</span>
                    </div>
                    ${e.system_prompt ? `<div class="control-row" style="font-size: 0.75rem; color: var(--text-secondary);"><span>AI: ${v}</span></div>` : ""}
                </div>
                <div class="channel-actions">
                    <button data-action="speak" data-character="${s}">Speak</button>
                    ${e.system_prompt ? `<button data-action="chat" data-character="${s}">Chat</button>` : ""}
                    <button data-action="copy-url" data-character="${s}" title="Copy browser source URL for OBS">Copy URL</button>
                    <button data-action="rotate-token" data-character="${s}" title="Invalidate old URL and generate new token">Rotate</button>
                    <button data-action="edit" data-character="${s}">Edit</button>
                    <button class="secondary" data-action="delete" data-character="${s}">Delete</button>
                </div>
            </div>
        `;
}
window.openCreateCharacterModal = rt;
window.closeCharacterModal = Y;
window.editCharacter = async function(e) {
  const t = await u(`/api/characters/${encodeURIComponent(e)}`);
  t && !("error" in t) ? Ie(t) : f("Failed to load character", "error");
};
window.deleteCharacter = Xe;
window.openSpeakModal = st;
window.closeSpeakModal = Se;
window.sendSpeak = it;
window.stopGeneration = lt;
window.openChatModal = mt;
window.closeChatModal = Me;
window.sendChat = pt;
window.clearChatMemory = ft;
window.attachImage = dt;
window.handleImageSelect = ut;
window.captureScreen = ht;
window.previewCharacterTextStyle = ot;
window.stopCharacterTextPreview = se;
window.updateProviderDropdown = xe;
window.loadVoiceModels = Ce;
window.updateModelInfo = oe;
window.toggleTTSProvider = Ee;
window.updateCartesiaVoiceInfo = K;
window.loadCartesiaVoices = re;
window.selectCartesiaVoice = Qe;
window.onCartesiaManualIdChange = Ze;
window.copyCharacterUrl = async function(e) {
  const t = w.find((a) => a.name === e);
  if (!(t != null && t.ws_token)) {
    f("Character token not found", "error");
    return;
  }
  const n = `${window.location.origin}/channel/${encodeURIComponent(e)}?token=${encodeURIComponent(t.ws_token)}`;
  try {
    await navigator.clipboard.writeText(n);
    const a = document.querySelector(`[data-character="${CSS.escape(e)}"]`);
    if (a) {
      const r = a.querySelector('button[data-action="copy-url"]');
      if (r) {
        const c = r.textContent;
        r.textContent = "Copied!", setTimeout(() => {
          r.textContent = c;
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
      const t = await u(`/api/characters/${encodeURIComponent(e)}/rotate-token`, "POST");
      if (t != null && t.success) {
        const n = w.find((a) => a.name === e);
        n && t.ws_token && (n.ws_token = t.ws_token), f("Token rotated. Copy new URL for OBS.", "success");
      } else
        f((t == null ? void 0 : t.detail) || "Failed to rotate token", "error");
    } catch (t) {
      console.error("Failed to rotate token:", t), f("Failed to rotate token", "error");
    }
};
const Z = document.getElementById("twitch-btn"), ee = document.getElementById("twitch-btn-text");
async function Be() {
  if (!(!Z || !ee))
    try {
      const t = await (await fetch("/api/twitch/status")).json();
      t.connected ? (Z.classList.add("connected"), ee.textContent = `#${t.channel}`) : (Z.classList.remove("connected"), ee.textContent = "Twitch");
    } catch (e) {
      console.error("Error checking Twitch status:", e);
    }
}
ae && ae.addEventListener("submit", ct);
L && L.addEventListener("click", (e) => {
  e.target === L && Y();
});
F && F.addEventListener("click", (e) => {
  e.target === F && Se();
});
E && E.addEventListener("click", (e) => {
  e.target === E && Me();
});
R && R.addEventListener("click", (e) => {
  const n = e.target.closest("button[data-action]");
  if (!n) return;
  const a = n.dataset.action, r = n.dataset.character;
  if (r)
    switch (a) {
      case "speak":
        window.openSpeakModal(r);
        break;
      case "chat":
        window.openChatModal(r);
        break;
      case "copy-url":
        window.copyCharacterUrl(r);
        break;
      case "rotate-token":
        window.rotateCharacterToken(r);
        break;
      case "edit":
        window.editCharacter(r);
        break;
      case "delete":
        window.deleteCharacter(r);
        break;
    }
});
_e();
J();
je();
X();
Be();
Je();
setInterval(X, 1e4);
setInterval(Be, 15e3);
