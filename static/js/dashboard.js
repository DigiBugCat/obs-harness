import { TextAnimator as Re } from "./text-animator.js";
function l(e) {
  return document.getElementById(e);
}
function r(e) {
  return document.getElementById(e);
}
function m(e) {
  return document.getElementById(e);
}
function D(e) {
  return document.getElementById(e);
}
function _(e) {
  return document.getElementById(e);
}
function Ce(e) {
  return document.getElementById(e);
}
function Ne(e) {
  return document.getElementById(e);
}
let y = null, L = null, B = 0;
const Fe = 1e3, He = 3e4, z = 10, he = 6e4, Oe = 3e4;
let W = Date.now(), N = null, R = null, me = [], w = [], k = null, p = null, M = null, j = [], E = null, g = null, A = !1, T = [], ae = null, x = null;
function Ge() {
  const t = new URLSearchParams(window.location.search).get("channel");
  return t ? (localStorage.setItem("effectiveChannel", t), t) : localStorage.getItem("effectiveChannel");
}
function ze(e) {
  if (!x) return e;
  const t = e.includes("?") ? "&" : "?";
  return `${e}${t}channel=${encodeURIComponent(x)}`;
}
const pe = document.getElementById("ws-status"), fe = document.getElementById("ws-status-text"), F = document.getElementById("characters-container"), ve = document.getElementById("history-list");
function $(e) {
  if (e == null) return "";
  const t = document.createElement("div");
  return t.textContent = String(e), t.innerHTML;
}
function qe(e, t = "#9146ff") {
  return e && /^#[0-9a-fA-F]{3,4}$|^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$/.test(e) ? e : t;
}
function We() {
  return ae;
}
function xe() {
  let t = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/dashboard`;
  x && (t += `?channel=${encodeURIComponent(x)}`), y = new WebSocket(t), y.onopen = () => {
    pe.classList.add("connected"), fe.textContent = "Connected", B = 0, W = Date.now(), Ye(), L && (clearTimeout(L), L = null);
  }, y.onclose = () => {
    pe.classList.remove("connected"), fe.textContent = "Disconnected", Ve(), je();
  }, y.onerror = (a) => {
    console.error("Dashboard WebSocket error:", a);
  }, y.onmessage = (a) => {
    try {
      const n = JSON.parse(a.data);
      Xe(n);
    } catch (n) {
      console.error("Error parsing message:", n);
    }
  };
}
function je() {
  if (!L) {
    if (B >= z) {
      console.log(`[dashboard] Max reconnect attempts (${z}) reached, reloading page...`), location.reload();
      return;
    }
    const e = Math.min(
      Fe * Math.pow(2, B),
      He
    );
    B++, console.log(`[dashboard] Reconnecting in ${e}ms (attempt ${B}/${z})...`), L = setTimeout(() => {
      L = null, xe();
    }, e);
  }
}
function Ve() {
  N || (N = setInterval(async () => {
    if (!(y && y.readyState === WebSocket.OPEN))
      try {
        (await fetch("/health", { signal: AbortSignal.timeout(5e3) })).ok && B >= z / 2 && (console.log("[dashboard] Server healthy but WebSocket failing, reloading page..."), location.reload());
      } catch {
      }
  }, Oe));
}
function Ye() {
  N && (clearInterval(N), N = null);
}
setInterval(() => {
  y && y.readyState === WebSocket.OPEN && Date.now() - W > he && (console.log(`[dashboard] No ping received in ${he}ms, connection stale - reconnecting...`), W = Date.now(), y.close());
}, 1e4);
function Xe(e) {
  if (e.type === "ping") {
    y && y.readyState === WebSocket.OPEN && y.send(JSON.stringify({ event: "pong", ts: e.ts })), W = Date.now();
    return;
  }
  if (e.type === "hello") {
    const t = e.build_id;
    if (e.tenant_id && (ae = e.tenant_id, console.log(`[dashboard] Tenant ID: ${ae}`)), R === null)
      R = t ?? null, console.log(`[dashboard] Server build ID: ${R}`);
    else if (R !== t) {
      console.log(`[dashboard] Server version changed (${R} -> ${t}), refreshing page...`), location.reload();
      return;
    } else
      console.log("[dashboard] Reconnected to same server version");
    return;
  }
  if (e.type === "characters") {
    const t = We(), a = e.characters, n = new Map(a.map((o) => [o.name, o]));
    if (w = w.map((o) => {
      var s, i;
      const c = `${t}:${o.name}`;
      return {
        ...o,
        connected: n.has(c),
        playing: ((s = n.get(c)) == null ? void 0 : s.playing) || !1,
        streaming: ((i = n.get(c)) == null ? void 0 : i.streaming) || !1
      };
    }), oe(), E && g) {
      const o = `${t}:${E}`, c = n.get(o);
      if (c && (c.streaming && (A = !0), A && !c.streaming)) {
        const s = document.getElementById(`${g}-stop-btn`), i = document.getElementById(`${g}-status-text`);
        s && (s.style.display = "none"), i && (i.textContent = "Complete!"), E = null, g = null, A = !1;
      }
    }
  } else e.type === "character_sync" && (w = e.characters, oe(), O || console.log("Character data synced from server"), O = !1);
}
let O = !1;
function f(e, t = "info", a = 4e3) {
  const n = document.querySelector(".toast-notification");
  n && n.remove();
  const o = document.createElement("div");
  o.className = `toast-notification toast-${t}`, o.textContent = e, document.body.appendChild(o), setTimeout(() => {
    o.classList.add("hiding"), setTimeout(() => o.remove(), 300);
  }, a);
}
async function u(e, t = "GET", a = null, n = !0) {
  const o = {
    method: t,
    headers: { "Content-Type": "application/json" }
  };
  a && (o.body = JSON.stringify(a));
  try {
    const c = await fetch(e, o), s = await c.json();
    if (!c.ok) {
      const i = s.detail || s.error || `HTTP ${c.status}`;
      return n && f(`API Error: ${i}`, "error"), console.error(`API Error [${t} ${e}]:`, i), { error: i, status: c.status };
    }
    return s;
  } catch (c) {
    const s = c.message || "Network error";
    return n && f(`Connection Error: ${s}`, "error"), console.error(`Fetch Error [${t} ${e}]:`, c), { error: s, networkError: !0 };
  }
}
async function Je() {
  const e = await u("/api/presets");
  return Array.isArray(e) && (me = e), me;
}
async function K() {
  const e = await u("/api/history");
  Array.isArray(e) && _t(e);
}
async function Q() {
  const e = await u(ze("/api/characters"));
  return Array.isArray(e) && (w = e, oe()), w;
}
async function Ke(e) {
  O = !0;
  const t = await u("/api/characters", "POST", e);
  return await Q(), t;
}
async function Qe(e, t, a = !0) {
  O = !0;
  const n = await u(`/api/characters/${e}`, "PUT", t, a);
  return await Q(), n;
}
async function Ze(e) {
  confirm(`Delete character "${e}"? This cannot be undone.`) && (O = !0, await u(`/api/characters/${e}`, "DELETE"), await Q());
}
async function Ee(e) {
  const t = document.getElementById("character-provider");
  if (t) {
    if (t.innerHTML = '<option value="">Loading providers...</option>', t.disabled = !0, !e || e.trim() === "") {
      t.innerHTML = '<option value="">Default (auto)</option>', t.disabled = !1;
      return;
    }
    try {
      const a = await u(`/api/openrouter/models/${encodeURIComponent(e)}/providers`, "GET", null, !1);
      if (t.innerHTML = '<option value="">Default (auto)</option>', a.providers && a.providers.length > 0)
        for (const n of a.providers) {
          const o = document.createElement("option");
          o.value = n, o.textContent = n, t.appendChild(o);
        }
    } catch (a) {
      console.error("Error fetching providers:", a), t.innerHTML = '<option value="">Default (auto)</option>';
    } finally {
      t.disabled = !1;
    }
  }
}
async function et() {
  const e = document.getElementById("character-tts-model");
  if (e)
    try {
      const t = await u("/api/elevenlabs/models", "GET", null, !1);
      Array.isArray(t) && (j = t, e.innerHTML = t.map((a) => {
        const n = a.name || a.model_id;
        return `<option value="${a.model_id}">${n}</option>`;
      }).join(""));
    } catch (t) {
      console.error("Error fetching ElevenLabs models:", t);
    }
}
async function ke(e) {
  const t = m("character-tts-model"), a = document.getElementById("tts-model-info");
  if (!(!t || !e)) {
    a && (a.textContent = "");
    try {
      const n = await u(`/api/elevenlabs/voices/${e}`, "GET", null, !1);
      if (n != null && n.high_quality_base_model_ids && n.high_quality_base_model_ids.length > 0) {
        const o = new Set(n.high_quality_base_model_ids);
        Array.from(t.options).forEach((c) => {
          if (o.has(c.value)) {
            const s = j.find((i) => i.model_id === c.value);
            c.textContent = `${(s == null ? void 0 : s.name) || c.value} (Recommended)`;
          } else {
            const s = j.find((i) => i.model_id === c.value);
            c.textContent = (s == null ? void 0 : s.name) || c.value;
          }
        }), a && (a.textContent = `Voice "${n.name}" is optimized for: ${n.high_quality_base_model_ids.join(", ")}`);
      }
    } catch (n) {
      console.error("Error fetching voice info:", n), a && (a.textContent = "Could not fetch voice info");
    }
  }
}
const tt = {
  eleven_v3: "Latest flagship model with emotionally rich, expressive speech. 70+ languages. Best for audiobooks & dramatic content. Not optimized for real-time.",
  eleven_multilingual_v2: "Advanced emotionally-aware synthesis. 29 languages. Most stable for long-form. Higher latency but best quality.",
  eleven_flash_v2_5: "Fastest model (~75ms latency). 32 languages. 50% lower cost. Best for real-time agents & bulk processing.",
  eleven_turbo_v2_5: "Balanced quality & speed (~250ms). 32 languages. Good middle-ground between Flash and Multilingual.",
  eleven_flash_v2: "Ultra-fast for real-time (~75ms). English only. Great for conversational agents.",
  eleven_turbo_v2: "Quality-focused with low latency (~250ms). English only. Good balance for English projects.",
  eleven_multilingual_v1: "Legacy multilingual model. Use v2 for better results.",
  eleven_monolingual_v1: "Legacy English model. Use newer models for better quality."
};
function re(e) {
  const t = document.getElementById("tts-model-info"), a = document.getElementById("voice-style-row"), n = document.getElementById("voice-similarity-row"), o = j.find((c) => c.model_id === e);
  o && (a && (a.style.display = o.can_use_style ? "" : "none"), n && (n.style.display = o.can_use_speaker_boost ? "" : "none"), t && (t.textContent = tt[e] || ""));
}
let V = [];
async function ce() {
  try {
    V = await u("/api/cartesia/voices", "GET", null, !1);
    const e = document.getElementById("cartesia-voice-select");
    if (!e) return;
    e.innerHTML = '<option value="">-- Select a voice --</option>', V.forEach((t) => {
      const a = document.createElement("option");
      a.value = t.voice_id, a.textContent = `${t.name} (${t.language})`, e.appendChild(a);
    });
  } catch (e) {
    console.error("Error loading Cartesia voices:", e);
    const t = document.getElementById("cartesia-voice-select");
    t && (t.innerHTML = '<option value="">Failed to load voices</option>');
  }
}
function at(e) {
  const t = document.getElementById("cartesia-voice-id");
  t && e && (t.value = e), Z(e);
}
function nt(e) {
  const t = document.getElementById("cartesia-voice-select");
  if (t && e)
    if (Array.from(t.options).find((n) => n.value === e))
      t.value = e, Z(e);
    else {
      t.value = "";
      const n = document.getElementById("cartesia-voice-info");
      n && (n.textContent = "Custom voice ID");
    }
}
function Z(e) {
  const t = document.getElementById("cartesia-voice-info");
  if (!t) return;
  if (!e) {
    t.textContent = "";
    return;
  }
  const a = V.find((n) => n.voice_id === e);
  a && a.description ? t.textContent = a.description : t.textContent = "";
}
function Ie(e) {
  const t = document.getElementById("elevenlabs-settings"), a = document.getElementById("cartesia-settings");
  e === "cartesia" ? (t && (t.style.display = "none"), a && (a.style.display = "block"), V.length === 0 && ce()) : (t && (t.style.display = "block"), a && (a.style.display = "none"));
}
async function ot(e, t, a) {
  return u(`/api/characters/${e}/speak`, "POST", {
    text: t,
    show_text: a
  });
}
async function rt(e, t, a, n = null, o = null) {
  const c = {
    message: t,
    show_text: a
  };
  return n !== null && n !== "" && (c.twitch_chat_seconds = parseInt(n)), o && o.length > 0 && (c.images = o.map((s) => ({
    data: s.data,
    media_type: s.mediaType
  }))), u(`/api/characters/${e}/chat`, "POST", c);
}
async function se(e) {
  return u(`/api/characters/${e}/memory`);
}
async function ct(e) {
  return u(`/api/characters/${e}/memory`, "DELETE");
}
function Y(e, t) {
  const a = document.getElementById("chat-history"), n = document.getElementById("chat-history-empty");
  if (!e || e.length === 0) {
    n && (n.style.display = "block"), a == null || a.querySelectorAll(".chat-bubble").forEach((o) => o.remove());
    return;
  }
  n && (n.style.display = "none"), a == null || a.querySelectorAll(".chat-bubble").forEach((o) => o.remove()), e.forEach((o) => {
    if (o.role === "context") {
      const c = o.content.split(`
`), s = c.slice(-4).map((v) => v.length > 60 ? v.substring(0, 57) + "..." : v).join(" | "), i = document.createElement("div");
      i.className = "chat-bubble context";
      const d = document.createElement("div");
      d.className = "chat-bubble-content", d.textContent = `📺 Twitch (${c.length}): ${s}`, i.appendChild(d), a == null || a.appendChild(i);
    } else {
      const c = document.createElement("div");
      c.className = `chat-bubble ${o.role}`;
      const s = document.createElement("div");
      s.className = "chat-bubble-label", s.textContent = o.role === "user" ? "You" : t;
      const i = document.createElement("div");
      if (i.className = "chat-bubble-content", o.interrupted && o.generated_text) {
        const d = o.content || "", v = o.generated_text || "";
        if (d) {
          const b = document.createElement("span");
          b.textContent = d, i.appendChild(b);
        }
        let S = "";
        if ((v.startsWith(d) || v.length > d.length) && (S = v.substring(d.length).trim()), S) {
          const b = document.createElement("span");
          b.style.textDecoration = "line-through", b.style.opacity = "0.6", b.textContent = " " + S, i.appendChild(b);
        }
        const h = document.createElement("span");
        h.style.cssText = "display: inline-block; margin-left: 8px; padding: 2px 6px; background: #ff6b6b33; color: #ff6b6b; border-radius: 4px; font-size: 0.7rem;", h.textContent = "⚡ interrupted", i.appendChild(h);
      } else
        i.textContent = o.content;
      c.appendChild(s), c.appendChild(i), a == null || a.appendChild(c);
    }
  }), a && (a.scrollTop = a.scrollHeight);
}
function ye(e, t, a) {
  const n = document.getElementById("chat-history"), o = document.getElementById("chat-history-empty");
  o && (o.style.display = "none");
  const c = document.createElement("div");
  c.className = `chat-bubble ${e}`;
  const s = document.createElement("div");
  s.className = "chat-bubble-label", s.textContent = e === "user" ? "You" : a;
  const i = document.createElement("div");
  i.className = "chat-bubble-content", i.textContent = t, c.appendChild(s), c.appendChild(i), n == null || n.appendChild(c), n && (n.scrollTop = n.scrollHeight);
}
function st(e) {
  const t = document.getElementById("chat-history"), a = document.getElementById("chat-history-empty");
  a && (a.style.display = "none");
  const n = document.createElement("div");
  n.className = "chat-bubble context";
  const o = document.createElement("div");
  o.className = "chat-bubble-content", o.textContent = e, n.appendChild(o), t == null || t.appendChild(n), t && (t.scrollTop = t.scrollHeight);
}
let X = null, q = null;
function it() {
  ie();
  const e = Ce("character-preview-canvas");
  if (!e) return;
  const t = e.getContext("2d");
  X = new Re(t, e.width, e.height);
  const a = X, n = {
    style: r("character-text-style").value,
    fontFamily: r("character-font-family").value,
    fontSize: parseInt(r("character-font-size").value),
    duration: parseInt(r("character-text-duration").value),
    color: r("character-text-color").value,
    strokeColor: r("character-stroke-color").value,
    strokeWidth: parseInt(r("character-stroke-width").value),
    positionX: parseInt(r("character-position-x").value) / 100,
    positionY: parseInt(r("character-position-y").value) / 100
  }, o = e.width / 800;
  a.show({
    text: "Sample Text",
    style: n.style,
    duration: n.duration,
    x: n.positionX,
    y: n.positionY,
    fontFamily: n.fontFamily,
    fontSize: Math.round(n.fontSize * o),
    color: n.color,
    strokeColor: n.strokeWidth > 0 ? n.strokeColor : null,
    strokeWidth: Math.round(n.strokeWidth * o)
  });
  function c() {
    t.clearRect(0, 0, e.width, e.height), a.update(), a.draw(), a.isAnimating() && (q = requestAnimationFrame(c));
  }
  c();
}
function ie() {
  q && (cancelAnimationFrame(q), q = null), X && X.clear();
  const e = Ce("character-preview-canvas");
  if (e) {
    const t = e.getContext("2d");
    t == null || t.clearRect(0, 0, e.width, e.height);
  }
}
const P = l("character-modal"), ne = Ne("character-form"), Se = l("character-modal-title");
function lt() {
  k = null, Se.textContent = "Create Character", ne.reset(), r("character-name").disabled = !1, r("character-color").value = "#e94560", r("character-icon").value = "🔊", r("character-stability").value = "50", l("character-stability-value").textContent = "0.50", r("character-similarity").value = "75", l("character-similarity-value").textContent = "0.75", r("character-voice-style").value = "0", l("character-style-value").textContent = "0.00", r("character-voice-speed").value = "100", l("character-speed-value").textContent = "1.0", r("character-volume").value = "100", l("character-volume-value").textContent = "100", m("character-text-style").value = "typewriter", r("character-font-family").value = "Arial", r("character-font-size").value = "48", r("character-text-duration").value = "3000", r("character-text-color").value = "#ffffff", r("character-stroke-color").value = "#000000", r("character-stroke-width").value = "0", l("character-stroke-width-value").textContent = "0", r("character-position-x").value = "50", l("character-pos-x-value").textContent = "50", r("character-position-y").value = "50", l("character-pos-y-value").textContent = "50", r("character-model").value = "anthropic/claude-sonnet-4.5", m("character-provider").innerHTML = '<option value="">Default (auto)</option>', m("character-provider").value = "", r("character-temperature").value = "70", l("character-temp-value").textContent = "0.7", r("character-max-tokens").value = "1024", m("character-tts-model").value = "eleven_multilingual_v2", l("tts-model-info").textContent = "", re("eleven_multilingual_v2"), r("character-memory-enabled").checked = !1, r("character-persist-memory").checked = !1, r("character-twitch-chat-enabled").checked = !1, r("character-twitch-chat-seconds").value = "60", r("character-twitch-chat-max").value = "20", P.classList.add("active");
}
function $e(e) {
  k = e, Se.textContent = "Edit Character";
  const t = e;
  r("character-name").value = e.name, r("character-name").disabled = !0, _("character-description").value = t.description || "", r("character-color").value = t.color, r("character-icon").value = t.icon;
  const a = e.tts_provider || "elevenlabs";
  if (m("character-tts-provider").value = a, Ie(a), a === "cartesia" && e.tts_settings)
    ce().then(() => {
      const n = e.tts_settings, o = n.voice_id || "";
      r("cartesia-voice-id").value = o;
      const c = m("cartesia-voice-select");
      c && o && Array.from(c.options).find((v) => v.value === o) && (c.value = o), r("cartesia-model-id").value = n.model_id || "sonic-2024-12-12", m("cartesia-language").value = n.language || "en";
      const s = n.speed || 1, i = Math.max(0.6, Math.min(1.5, s));
      r("cartesia-speed").value = String(Math.round(i * 100)), l("cartesia-speed-value").textContent = i.toFixed(1), s !== i && console.warn(`Cartesia speed ${s} was clamped to ${i} (valid: 0.6-1.5)`), Z(o);
    });
  else {
    const n = e.tts_settings || {};
    r("character-voice-id").value = n.voice_id || t.elevenlabs_voice_id;
    const o = n.model_id || t.elevenlabs_model_id || "eleven_multilingual_v2";
    m("character-tts-model").value = o, re(o), ke(n.voice_id || t.elevenlabs_voice_id);
    const c = n.stability ?? t.voice_stability;
    r("character-stability").value = String(Math.round(c * 100)), l("character-stability-value").textContent = c.toFixed(2);
    const s = n.similarity_boost ?? t.voice_similarity_boost;
    r("character-similarity").value = String(Math.round(s * 100)), l("character-similarity-value").textContent = s.toFixed(2);
    const i = n.style ?? t.voice_style;
    r("character-voice-style").value = String(Math.round(i * 100)), l("character-style-value").textContent = i.toFixed(2);
    const d = n.speed ?? t.voice_speed;
    r("character-voice-speed").value = String(Math.round(d * 100)), l("character-speed-value").textContent = d.toFixed(1);
  }
  r("character-volume").value = String(Math.round(t.default_volume * 100)), l("character-volume-value").textContent = String(Math.round(t.default_volume * 100)), r("character-muted").checked = t.mute_state, m("character-text-style").value = t.default_text_style, r("character-font-family").value = e.text_font_family || "Arial", r("character-font-size").value = String(e.text_font_size || 48), r("character-text-duration").value = String(t.text_duration), r("character-text-color").value = e.text_color || "#ffffff", r("character-stroke-color").value = e.text_stroke_color || "#000000", r("character-stroke-width").value = String(e.text_stroke_width || 0), l("character-stroke-width-value").textContent = String(e.text_stroke_width || 0), r("character-position-x").value = String(Math.round((e.text_position_x || 0.5) * 100)), l("character-pos-x-value").textContent = String(Math.round((e.text_position_x || 0.5) * 100)), r("character-position-y").value = String(Math.round((e.text_position_y || 0.5) * 100)), l("character-pos-y-value").textContent = String(Math.round((e.text_position_y || 0.5) * 100)), _("character-prompt").value = e.system_prompt || "", r("character-model").value = e.openrouter_model || "", Ee(e.openrouter_model || "").then(() => {
    m("character-provider").value = t.provider || "";
  }), r("character-temperature").value = String(Math.round(t.temperature * 100)), l("character-temp-value").textContent = t.temperature.toFixed(1), r("character-max-tokens").value = String(t.max_tokens), r("character-memory-enabled").checked = t.memory_enabled || !1, r("character-persist-memory").checked = e.persist_memory || !1, r("character-twitch-chat-enabled").checked = t.twitch_chat_enabled || !1, r("character-twitch-chat-seconds").value = String(t.twitch_chat_window_seconds || 60), r("character-twitch-chat-max").value = String(t.twitch_chat_max_messages || 20), P.classList.add("active");
}
function J() {
  P.classList.remove("active"), k = null, ie();
}
async function dt(e) {
  e.preventDefault();
  const t = m("character-tts-provider").value;
  let a = null;
  t === "cartesia" ? a = {
    voice_id: r("cartesia-voice-id").value,
    model_id: r("cartesia-model-id").value,
    language: m("cartesia-language").value,
    speed: parseInt(r("cartesia-speed").value) / 100
  } : a = {
    voice_id: r("character-voice-id").value,
    model_id: m("character-tts-model").value,
    stability: parseInt(r("character-stability").value) / 100,
    similarity_boost: parseInt(r("character-similarity").value) / 100,
    style: parseInt(r("character-voice-style").value) / 100,
    speed: parseInt(r("character-voice-speed").value) / 100
  };
  const n = {
    name: r("character-name").value,
    description: _("character-description").value || null,
    color: r("character-color").value,
    icon: r("character-icon").value,
    // TTS provider abstraction
    tts_provider: t,
    tts_settings: a,
    // Legacy ElevenLabs fields (for backwards compatibility)
    elevenlabs_voice_id: r("character-voice-id").value,
    elevenlabs_model_id: m("character-tts-model").value,
    voice_stability: parseInt(r("character-stability").value) / 100,
    voice_similarity_boost: parseInt(r("character-similarity").value) / 100,
    voice_style: parseInt(r("character-voice-style").value) / 100,
    voice_speed: parseInt(r("character-voice-speed").value) / 100,
    default_volume: parseInt(r("character-volume").value) / 100,
    mute_state: r("character-muted").checked,
    default_text_style: m("character-text-style").value,
    text_font_family: r("character-font-family").value,
    text_font_size: parseInt(r("character-font-size").value),
    text_duration: parseInt(r("character-text-duration").value),
    text_color: r("character-text-color").value,
    text_stroke_color: parseInt(r("character-stroke-width").value) > 0 ? r("character-stroke-color").value : null,
    text_stroke_width: parseInt(r("character-stroke-width").value),
    text_position_x: parseInt(r("character-position-x").value) / 100,
    text_position_y: parseInt(r("character-position-y").value) / 100,
    system_prompt: _("character-prompt").value || null,
    model: r("character-model").value,
    provider: m("character-provider").value || null,
    temperature: parseInt(r("character-temperature").value) / 100,
    max_tokens: parseInt(r("character-max-tokens").value),
    memory_enabled: r("character-memory-enabled").checked,
    persist_memory: r("character-persist-memory").checked,
    twitch_chat_enabled: r("character-twitch-chat-enabled").checked,
    twitch_chat_window_seconds: parseInt(r("character-twitch-chat-seconds").value),
    twitch_chat_max_messages: parseInt(r("character-twitch-chat-max").value),
    // Optimistic concurrency control - send timestamp to detect conflicts
    expected_updated_at: (k == null ? void 0 : k.updated_at) || null
  };
  try {
    if (k) {
      const o = await Qe(k.name, n, !1);
      if (o && o.status === 409) {
        const c = await u(`/api/characters/${encodeURIComponent(k.name)}`, "GET", null, !1);
        c && !("error" in c) ? ($e(c), f("Someone else modified this character. Please review the updated values and try again.", "warning")) : (J(), f("Character was modified. Please try again.", "warning"));
        return;
      }
    } else
      await Ke(n);
    J();
  } catch (o) {
    console.error("Error saving character:", o), alert("Error saving character. Check console for details.");
  }
}
const H = l("speak-modal");
function ut(e) {
  const t = w.find((a) => a.name === e);
  t && (M = t, l("speak-modal-title").textContent = `Speak as ${t.name}`, _("speak-text").value = "", r("speak-show-text").checked = !0, l("speak-status").style.display = "none", D("speak-send-btn").disabled = !1, H.classList.add("active"));
}
function Te() {
  H.classList.remove("active"), M = null;
}
async function ht() {
  if (!M) return;
  const e = _("speak-text").value.trim(), t = r("speak-show-text").checked;
  if (!e) {
    alert("Please enter text to speak");
    return;
  }
  const a = l("speak-status"), n = l("speak-status-text"), o = D("speak-send-btn"), c = D("speak-stop-btn");
  a.style.display = "block", n.textContent = "Speaking...", o.disabled = !0, c.style.display = "inline-block", E = M.name, g = "speak", A = !1;
  try {
    const s = await ot(M.name, e, t);
    s.error || s.detail ? (n.textContent = `Error: ${s.error || s.detail}`, c.style.display = "none", E = null, g = null) : (n.textContent = "Playing audio...", _("speak-text").value = "", K());
  } catch (s) {
    console.error("Speak error:", s), n.textContent = `Error: ${s.message || "Unknown error"}`, c.style.display = "none", E = null, g = null;
  } finally {
    o.disabled = !1;
  }
}
async function mt(e) {
  const t = e === "speak" ? M == null ? void 0 : M.name : p == null ? void 0 : p.name;
  if (!t) return;
  const a = document.getElementById(`${e}-status-text`), n = document.getElementById(`${e}-stop-btn`);
  a && (a.textContent = "Stopping..."), n && (n.disabled = !0);
  try {
    const o = await u(`/api/characters/${t}/stop`, "POST");
    a && (o.was_active ? a.textContent = "Stopped" : a.textContent = "Nothing to stop"), e === "chat" && o.was_active && setTimeout(async () => {
      try {
        const c = await se(t);
        l("chat-memory-count").textContent = `Memory: ${c.message_count} messages`, Y(c.messages, t);
      } catch (c) {
        console.error("Error refreshing memory after stop:", c);
      }
    }, 500);
  } catch (o) {
    console.error("Stop error:", o), a && (a.textContent = `Stop failed: ${o.message}`);
  } finally {
    n && (n.disabled = !1, n.style.display = "none"), E = null, g = null, A = !1;
    const o = document.getElementById(`${e}-send-btn`);
    o && (o.disabled = !1);
  }
}
const I = document.getElementById("chat-modal"), ge = 20, we = 5;
function le() {
  T = [];
  const e = document.getElementById("chat-image-previews");
  if (e)
    for (; e.firstChild; )
      e.removeChild(e.firstChild);
}
function Me(e, t) {
  if (T.length >= we) {
    f(`Maximum ${we} images allowed`, "warning");
    return;
  }
  T.push({ data: e, mediaType: t });
  const a = l("chat-image-previews"), n = document.createElement("div");
  n.className = "image-preview-thumb", n.dataset.index = String(T.length - 1);
  const o = document.createElement("img");
  o.src = `data:${t};base64,${e}`;
  const c = document.createElement("button");
  c.className = "remove-btn", c.textContent = "×", c.onclick = function() {
    const s = parseInt(n.dataset.index || "0");
    T.splice(s, 1), n.remove(), document.querySelectorAll("#chat-image-previews .image-preview-thumb").forEach((i, d) => {
      i.dataset.index = String(d);
    });
  }, n.appendChild(o), n.appendChild(c), a.appendChild(n);
}
async function Be(e) {
  if (!e.type.startsWith("image/")) {
    f("Only image files are supported", "error");
    return;
  }
  if (e.size > ge * 1024 * 1024) {
    f(`Image too large (max ${ge}MB)`, "error");
    return;
  }
  return new Promise((t) => {
    const a = new FileReader();
    a.onload = (n) => {
      var i;
      const c = ((i = n.target) == null ? void 0 : i.result).split(",")[1], s = e.type || "image/png";
      Me(c, s), t();
    }, a.readAsDataURL(e);
  });
}
function pt() {
  r("chat-image-input").click();
}
async function ft(e) {
  const t = e.target, a = t.files;
  if (a)
    for (const n of a)
      await Be(n);
  t.value = "";
}
async function vt() {
  try {
    const e = await navigator.mediaDevices.getDisplayMedia({
      video: !0
    }), t = document.createElement("video");
    t.srcObject = e, await t.play(), await new Promise((s) => {
      t.readyState >= 2 ? s() : t.onloadeddata = () => s();
    });
    const a = document.createElement("canvas");
    a.width = t.videoWidth, a.height = t.videoHeight, a.getContext("2d").drawImage(t, 0, 0), e.getTracks().forEach((s) => s.stop());
    const c = a.toDataURL("image/png").split(",")[1];
    Me(c, "image/png"), f("Screen captured!", "success");
  } catch (e) {
    e instanceof Error && e.name === "NotAllowedError" ? f("Screen capture permission denied", "warning") : (console.error("Screen capture error:", e), f("Screen capture failed", "error"));
  }
}
function _e(e) {
  var a;
  const t = (a = e.clipboardData) == null ? void 0 : a.items;
  if (t) {
    for (const n of t)
      if (n.type.startsWith("image/")) {
        e.preventDefault();
        const o = n.getAsFile();
        o && Be(o);
      }
  }
}
async function yt(e) {
  const t = w.find((n) => n.name === e);
  if (!t) return;
  if (!t.system_prompt) {
    alert('This character has no AI system prompt configured. Use "Speak" for direct TTS.');
    return;
  }
  p = t, l("chat-modal-title").textContent = `Chat with ${t.name}`, _("chat-message").value = "", r("chat-show-text").checked = !0, r("chat-include-twitch").checked = !0, r("chat-twitch-seconds").value = "", l("chat-status").style.display = "none", l("chat-twitch-details").style.display = "none", D("chat-send-btn").disabled = !1, le();
  const a = _("chat-message");
  a.removeEventListener("paste", _e), a.addEventListener("paste", _e);
  try {
    const n = await se(e);
    l("chat-memory-count").textContent = `Memory: ${n.message_count} messages${t.memory_enabled ? "" : " (disabled)"}`, Y(n.messages, e);
  } catch {
    l("chat-memory-count").textContent = "Memory: 0 messages", Y([], e);
  }
  I == null || I.classList.add("active");
}
function Le() {
  I == null || I.classList.remove("active"), p = null, le();
}
async function gt() {
  if (!p) return;
  const e = _("chat-message").value.trim(), t = r("chat-show-text").checked, a = r("chat-include-twitch").checked;
  let n = r("chat-twitch-seconds").value;
  if (a || (n = "0"), !e) {
    alert("Please enter a message");
    return;
  }
  const o = l("chat-status"), c = l("chat-status-text"), s = D("chat-send-btn"), i = D("chat-stop-btn");
  o.style.display = "block", c.textContent = "Generating...", s.disabled = !0, i.style.display = "inline-block", E = p.name, g = "chat", A = !1;
  try {
    const d = T.length > 0, v = d ? `[${T.length} image(s)] ${e}` : e;
    ye("user", v, p.name), _("chat-message").value = "";
    const S = d ? [...T] : null;
    le();
    const h = await rt(p.name, e, t, n, S);
    if (h.error || h.detail)
      c.textContent = `Error: ${h.error || h.detail}`, i.style.display = "none", E = null, g = null;
    else {
      if (h.twitch_chat_context) {
        const U = h.twitch_chat_context.split(`
`), Ue = U.slice(-4).map((ee) => ee.length > 60 ? ee.substring(0, 57) + "..." : ee).join(" | ");
        st(`📺 Twitch chat (${U.length}): ${Ue}`);
      }
      ye("assistant", h.response_text || "", p.name);
      let b = "Playing audio...";
      const G = document.getElementById("chat-twitch-details"), de = document.getElementById("chat-twitch-summary"), ue = document.getElementById("chat-twitch-context-text");
      if (h.twitch_chat_context) {
        const U = h.twitch_chat_context.split(`
`).length;
        b += ` (${U} chat msgs)`, de && (de.textContent = `Twitch Chat Context (${U} messages)`), ue && (ue.textContent = h.twitch_chat_context), G && (G.style.display = "block");
      } else
        G && (G.style.display = "none");
      c.textContent = b, K();
      const Pe = await se(p.name), De = p;
      l("chat-memory-count").textContent = `Memory: ${Pe.message_count} messages${De.memory_enabled ? "" : " (not saving)"}`;
    }
  } catch (d) {
    console.error("Chat error:", d), c.textContent = `Error: ${d instanceof Error ? d.message : "Unknown error"}`, i.style.display = "none", E = null, g = null;
  } finally {
    s.disabled = !1;
  }
}
async function wt() {
  if (p && confirm(`Clear conversation memory for ${p.name}?`))
    try {
      await ct(p.name);
      const e = document.getElementById("chat-memory-count"), t = document.getElementById("chat-status"), a = document.getElementById("chat-status-text"), n = document.getElementById("chat-twitch-details");
      e && (e.textContent = "Memory: 0 messages"), t && (t.style.display = "block"), a && (a.textContent = "Memory cleared!"), Y([], p.name), n && (n.style.display = "none");
    } catch (e) {
      console.error("Error clearing memory:", e), alert("Error clearing memory");
    }
}
function _t(e) {
  if (!e || e.length === 0) {
    ve.innerHTML = '<div class="history-item"><span class="history-content">No history yet</span></div>';
    return;
  }
  ve.innerHTML = e.map((t) => {
    const a = new Date(t.timestamp).toLocaleTimeString();
    return `
                <div class="history-item">
                    <span class="history-channel">${$(t.channel)}</span>
                    <span class="history-content">${$(t.content)}</span>
                    <span class="history-time">${$(a)}</span>
                </div>
            `;
  }).join("");
}
function oe() {
  if (F) {
    if (w.length === 0) {
      F.innerHTML = `
                <div class="no-channels">
                    <p>No characters configured yet.</p>
                    <p>Click "Create Character" to add one.</p>
                </div>
            `;
      return;
    }
    F.innerHTML = w.map((e) => bt(e)).join("");
  }
}
function bt(e) {
  var h;
  let t = "", a = "offline";
  e.connected ? e.streaming ? (t = "streaming", a = "streaming") : e.playing ? (t = "playing", a = "playing") : a = "ready" : (t = "", a = "offline");
  const n = e.connected ? "" : "disconnected", o = e.system_prompt ? '<span class="voice-indicator">AI</span>' : "", c = $(e.description || (e.system_prompt ? e.system_prompt.substring(0, 80) + "..." : "No description")), s = $(e.name), i = $(e.icon), d = qe(e.color), v = $(e.model ? e.model.split("/").pop() : ""), S = $(e.tts_provider === "cartesia" ? (((h = e.tts_settings) == null ? void 0 : h.model_id) || "sonic").replace("sonic-", "") : (e.elevenlabs_model_id || "multilingual_v2").replace("eleven_", "").replace("_", " "));
  return `
            <div class="channel-card ${n}" data-character="${s}" style="border-left-color: ${d}">
                <div class="channel-header">
                    <div class="channel-name">
                        <span class="channel-icon">${i}</span>
                        ${s}
                        ${o}
                    </div>
                    <span class="channel-status ${t}">${a}</span>
                </div>
                <p class="channel-description">${c}</p>
                <div class="channel-controls">
                    <div class="control-row" style="font-size: 0.75rem; color: var(--text-secondary);">
                        <span>TTS: ${e.tts_provider === "cartesia" ? "Cartesia" : "ElevenLabs"}</span>
                        <span>${S}</span>
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
window.openCreateCharacterModal = lt;
window.closeCharacterModal = J;
window.editCharacter = async function(e) {
  const t = await u(`/api/characters/${encodeURIComponent(e)}`);
  t && !("error" in t) ? $e(t) : f("Failed to load character", "error");
};
window.deleteCharacter = Ze;
window.openSpeakModal = ut;
window.closeSpeakModal = Te;
window.sendSpeak = ht;
window.stopGeneration = mt;
window.openChatModal = yt;
window.closeChatModal = Le;
window.sendChat = gt;
window.clearChatMemory = wt;
window.attachImage = pt;
window.handleImageSelect = ft;
window.captureScreen = vt;
window.previewCharacterTextStyle = it;
window.stopCharacterTextPreview = ie;
window.updateProviderDropdown = Ee;
window.loadVoiceModels = ke;
window.updateModelInfo = re;
window.toggleTTSProvider = Ie;
window.updateCartesiaVoiceInfo = Z;
window.loadCartesiaVoices = ce;
window.selectCartesiaVoice = at;
window.onCartesiaManualIdChange = nt;
window.copyCharacterUrl = async function(e) {
  const t = w.find((n) => n.name === e);
  if (!(t != null && t.ws_token)) {
    f("Character token not found", "error");
    return;
  }
  const a = `${window.location.origin}/channel/${encodeURIComponent(e)}?token=${encodeURIComponent(t.ws_token)}`;
  try {
    await navigator.clipboard.writeText(a);
    const n = document.querySelector(`[data-character="${CSS.escape(e)}"]`);
    if (n) {
      const o = n.querySelector('button[data-action="copy-url"]');
      if (o) {
        const c = o.textContent;
        o.textContent = "Copied!", setTimeout(() => {
          o.textContent = c;
        }, 1500);
      }
    }
  } catch (n) {
    console.error("Failed to copy URL:", n), prompt("Copy this URL for OBS browser source:", a);
  }
};
window.rotateCharacterToken = async function(e) {
  if (confirm(`Rotate token for "${e}"?

This will invalidate any existing OBS browser source URLs. You'll need to update your OBS sources with the new URL.`))
    try {
      const t = await u(`/api/characters/${encodeURIComponent(e)}/rotate-token`, "POST");
      if (t != null && t.success) {
        const a = w.find((n) => n.name === e);
        a && t.ws_token && (a.ws_token = t.ws_token), f("Token rotated. Copy new URL for OBS.", "success");
      } else
        f((t == null ? void 0 : t.detail) || "Failed to rotate token", "error");
    } catch (t) {
      console.error("Failed to rotate token:", t), f("Failed to rotate token", "error");
    }
};
const te = document.getElementById("twitch-user"), be = document.getElementById("twitch-username");
async function Ae() {
  if (!(!te || !be))
    try {
      const t = await (await fetch("/api/twitch/status")).json();
      t.connected && t.channel ? (be.textContent = t.channel, te.style.display = "inline-flex") : te.style.display = "none";
    } catch (e) {
      console.error("Error checking Twitch status:", e);
    }
}
const C = document.getElementById("channel-switcher");
async function Ct() {
  if (C)
    try {
      const t = await (await fetch("/api/moderators/accessible-channels")).json();
      if (!t.channels || t.channels.length <= 1) {
        C.style.display = "none", x && t.channels && !t.channels.find((a) => a.tenant_id === x) && (x = null, localStorage.removeItem("effectiveChannel"));
        return;
      }
      if (C.innerHTML = "", t.channels.forEach((a) => {
        const n = document.createElement("option");
        n.value = a.tenant_id, n.textContent = a.is_own ? `${a.username} (You)` : a.username, C.appendChild(n);
      }), x)
        C.value = x;
      else {
        const a = t.channels.find((n) => n.is_own);
        a && (C.value = a.tenant_id);
      }
      C.style.display = "inline-flex", C.onchange = () => {
        const a = C.value, n = t.channels.find((o) => o.is_own);
        a === (n == null ? void 0 : n.tenant_id) ? (localStorage.removeItem("effectiveChannel"), window.location.href = "/") : (localStorage.setItem("effectiveChannel", a), window.location.href = `/?channel=${encodeURIComponent(a)}`);
      };
    } catch (e) {
      console.error("Error loading accessible channels:", e), C.style.display = "none";
    }
}
ne && ne.addEventListener("submit", dt);
P && P.addEventListener("click", (e) => {
  e.target === P && J();
});
H && H.addEventListener("click", (e) => {
  e.target === H && Te();
});
I && I.addEventListener("click", (e) => {
  e.target === I && Le();
});
F && F.addEventListener("click", (e) => {
  const a = e.target.closest("button[data-action]");
  if (!a) return;
  const n = a.dataset.action, o = a.dataset.character;
  if (o)
    switch (n) {
      case "speak":
        window.openSpeakModal(o);
        break;
      case "chat":
        window.openChatModal(o);
        break;
      case "copy-url":
        window.copyCharacterUrl(o);
        break;
      case "rotate-token":
        window.rotateCharacterToken(o);
        break;
      case "edit":
        window.editCharacter(o);
        break;
      case "delete":
        window.deleteCharacter(o);
        break;
    }
});
x = Ge();
xe();
Q();
Je();
K();
Ae();
et();
Ct();
setInterval(K, 1e4);
setInterval(Ae, 15e3);
