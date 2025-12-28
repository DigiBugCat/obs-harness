import { TextAnimator as Ne } from "./text-animator.js";
function l(e) {
  return document.getElementById(e);
}
function r(e) {
  return document.getElementById(e);
}
function u(e) {
  return document.getElementById(e);
}
function D(e) {
  return document.getElementById(e);
}
function C(e) {
  return document.getElementById(e);
}
function xe(e) {
  return document.getElementById(e);
}
function He(e) {
  return document.getElementById(e);
}
let g = null, L = null, B = 0;
const Oe = 1e3, Ge = 3e4, q = 10, me = 6e4, ze = 3e4;
let W = Date.now(), N = null, R = null, pe = [], b = [], S = null, p = null, M = null, j = [], I = null, _ = null, A = !1, T = [], ae = null, E = null;
function qe() {
  const t = new URLSearchParams(window.location.search).get("channel");
  return t ? (localStorage.setItem("effectiveChannel", t), t) : localStorage.getItem("effectiveChannel");
}
function Ve(e) {
  if (!E) return e;
  const t = e.includes("?") ? "&" : "?";
  return `${e}${t}channel=${encodeURIComponent(E)}`;
}
const fe = document.getElementById("ws-status"), ve = document.getElementById("ws-status-text"), H = document.getElementById("characters-container"), ye = document.getElementById("history-list");
function k(e) {
  if (e == null) return "";
  const t = document.createElement("div");
  return t.textContent = String(e), t.innerHTML;
}
function We(e, t = "#9146ff") {
  return e && /^#[0-9a-fA-F]{3,4}$|^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$/.test(e) ? e : t;
}
function je() {
  return ae;
}
function ke() {
  let t = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/dashboard`;
  E && (t += `?channel=${encodeURIComponent(E)}`), g = new WebSocket(t), g.onopen = () => {
    fe.classList.add("connected"), ve.textContent = "Connected", B = 0, W = Date.now(), Ke(), L && (clearTimeout(L), L = null);
  }, g.onclose = () => {
    fe.classList.remove("connected"), ve.textContent = "Disconnected", Xe(), Ye();
  }, g.onerror = (a) => {
    console.error("Dashboard WebSocket error:", a);
  }, g.onmessage = (a) => {
    try {
      const n = JSON.parse(a.data);
      Je(n);
    } catch (n) {
      console.error("Error parsing message:", n);
    }
  };
}
function Ye() {
  if (!L) {
    if (B >= q) {
      console.log(`[dashboard] Max reconnect attempts (${q}) reached, reloading page...`), location.reload();
      return;
    }
    const e = Math.min(
      Oe * Math.pow(2, B),
      Ge
    );
    B++, console.log(`[dashboard] Reconnecting in ${e}ms (attempt ${B}/${q})...`), L = setTimeout(() => {
      L = null, ke();
    }, e);
  }
}
function Xe() {
  N || (N = setInterval(async () => {
    if (!(g && g.readyState === WebSocket.OPEN))
      try {
        (await fetch("/health", { signal: AbortSignal.timeout(5e3) })).ok && B >= q / 2 && (console.log("[dashboard] Server healthy but WebSocket failing, reloading page..."), location.reload());
      } catch {
      }
  }, ze));
}
function Ke() {
  N && (clearInterval(N), N = null);
}
setInterval(() => {
  g && g.readyState === WebSocket.OPEN && Date.now() - W > me && (console.log(`[dashboard] No ping received in ${me}ms, connection stale - reconnecting...`), W = Date.now(), g.close());
}, 1e4);
function Je(e) {
  if (e.type === "ping") {
    g && g.readyState === WebSocket.OPEN && g.send(JSON.stringify({ event: "pong", ts: e.ts })), W = Date.now();
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
    const t = je(), a = e.characters, n = new Map(a.map((o) => [o.name, o]));
    if (b = b.map((o) => {
      var c, i;
      const s = `${t}:${o.name}`;
      return {
        ...o,
        connected: n.has(s),
        playing: ((c = n.get(s)) == null ? void 0 : c.playing) || !1,
        streaming: ((i = n.get(s)) == null ? void 0 : i.streaming) || !1
      };
    }), re(), I && _) {
      const o = `${t}:${I}`, s = n.get(o);
      if (s && (s.streaming && (A = !0), A && !s.streaming)) {
        const c = document.getElementById(`${_}-stop-btn`), i = document.getElementById(`${_}-status-text`);
        c && (c.style.display = "none"), i && (i.textContent = "Complete!"), I = null, _ = null, A = !1;
      }
    }
  } else e.type === "character_sync" && (b = e.characters, re(), G || console.log("Character data synced from server"), G = !1);
}
let G = !1;
function f(e, t = "info", a = 4e3) {
  const n = document.querySelector(".toast-notification");
  n && n.remove();
  const o = document.createElement("div");
  o.className = `toast-notification toast-${t}`, o.textContent = e, document.body.appendChild(o), setTimeout(() => {
    o.classList.add("hiding"), setTimeout(() => o.remove(), 300);
  }, a);
}
async function h(e, t = "GET", a = null, n = !0) {
  const o = {
    method: t,
    headers: { "Content-Type": "application/json" }
  };
  a && (o.body = JSON.stringify(a));
  try {
    const s = await fetch(e, o), c = await s.json();
    if (!s.ok) {
      const i = c.detail || c.error || `HTTP ${s.status}`;
      return n && f(`API Error: ${i}`, "error"), console.error(`API Error [${t} ${e}]:`, i), { error: i, status: s.status };
    }
    return c;
  } catch (s) {
    const c = s.message || "Network error";
    return n && f(`Connection Error: ${c}`, "error"), console.error(`Fetch Error [${t} ${e}]:`, s), { error: c, networkError: !0 };
  }
}
async function Qe() {
  const e = await h("/api/presets");
  return Array.isArray(e) && (pe = e), pe;
}
async function Q() {
  const e = await h("/api/history");
  Array.isArray(e) && Ct(e);
}
async function Z() {
  const e = await h(Ve("/api/characters"));
  return Array.isArray(e) && (b = e, re()), b;
}
async function Ze(e) {
  G = !0;
  const t = await h("/api/characters", "POST", e);
  return await Z(), t;
}
async function et(e, t, a = !0) {
  G = !0;
  const n = await h(`/api/characters/${e}`, "PUT", t, a);
  return await Z(), n;
}
async function tt(e) {
  confirm(`Delete character "${e}"? This cannot be undone.`) && (G = !0, await h(`/api/characters/${e}`, "DELETE"), await Z());
}
async function Ee(e) {
  const t = document.getElementById("character-provider");
  if (t) {
    if (t.innerHTML = '<option value="">Loading providers...</option>', t.disabled = !0, !e || e.trim() === "") {
      t.innerHTML = '<option value="">Default (auto)</option>', t.disabled = !1;
      return;
    }
    try {
      const a = await h(`/api/openrouter/models/${encodeURIComponent(e)}/providers`, "GET", null, !1);
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
async function nt() {
  const e = document.getElementById("character-tts-model");
  if (e)
    try {
      const t = await h("/api/elevenlabs/models", "GET", null, !1);
      Array.isArray(t) && (j = t, e.innerHTML = t.map((a) => {
        const n = a.name || a.model_id;
        return `<option value="${a.model_id}">${n}</option>`;
      }).join(""));
    } catch (t) {
      console.error("Error fetching ElevenLabs models:", t);
    }
}
async function Ie(e) {
  const t = u("character-tts-model"), a = document.getElementById("tts-model-info");
  if (!(!t || !e)) {
    a && (a.textContent = "");
    try {
      const n = await h(`/api/elevenlabs/voices/${e}`, "GET", null, !1);
      if (n != null && n.high_quality_base_model_ids && n.high_quality_base_model_ids.length > 0) {
        const o = new Set(n.high_quality_base_model_ids);
        Array.from(t.options).forEach((s) => {
          if (o.has(s.value)) {
            const c = j.find((i) => i.model_id === s.value);
            s.textContent = `${(c == null ? void 0 : c.name) || s.value} (Recommended)`;
          } else {
            const c = j.find((i) => i.model_id === s.value);
            s.textContent = (c == null ? void 0 : c.name) || s.value;
          }
        }), a && (a.textContent = `Voice "${n.name}" is optimized for: ${n.high_quality_base_model_ids.join(", ")}`);
      }
    } catch (n) {
      console.error("Error fetching voice info:", n), a && (a.textContent = "Could not fetch voice info");
    }
  }
}
const at = {
  eleven_v3: "Latest flagship model with emotionally rich, expressive speech. 70+ languages. Best for audiobooks & dramatic content. Not optimized for real-time.",
  eleven_multilingual_v2: "Advanced emotionally-aware synthesis. 29 languages. Most stable for long-form. Higher latency but best quality.",
  eleven_flash_v2_5: "Fastest model (~75ms latency). 32 languages. 50% lower cost. Best for real-time agents & bulk processing.",
  eleven_turbo_v2_5: "Balanced quality & speed (~250ms). 32 languages. Good middle-ground between Flash and Multilingual.",
  eleven_flash_v2: "Ultra-fast for real-time (~75ms). English only. Great for conversational agents.",
  eleven_turbo_v2: "Quality-focused with low latency (~250ms). English only. Good balance for English projects.",
  eleven_multilingual_v1: "Legacy multilingual model. Use v2 for better results.",
  eleven_monolingual_v1: "Legacy English model. Use newer models for better quality."
};
function se(e) {
  const t = document.getElementById("tts-model-info"), a = document.getElementById("voice-style-row"), n = document.getElementById("voice-similarity-row"), o = j.find((s) => s.model_id === e);
  o && (a && (a.style.display = o.can_use_style ? "" : "none"), n && (n.style.display = o.can_use_speaker_boost ? "" : "none"), t && (t.textContent = at[e] || ""));
}
let Y = [], F = [];
async function ce() {
  try {
    Y = await h("/api/cartesia/voices", "GET", null, !1);
    const e = document.getElementById("cartesia-voice-select");
    if (!e) return;
    e.innerHTML = '<option value="">-- Select a voice --</option>', Y.forEach((t) => {
      const a = document.createElement("option");
      a.value = t.voice_id, a.textContent = `${t.name} (${t.language})`, e.appendChild(a);
    });
  } catch (e) {
    console.error("Error loading Cartesia voices:", e);
    const t = document.getElementById("cartesia-voice-select");
    t && (t.innerHTML = '<option value="">Failed to load voices</option>');
  }
}
function ot(e) {
  const t = document.getElementById("cartesia-voice-id");
  t && e && (t.value = e), ee(e);
}
function rt(e) {
  const t = document.getElementById("cartesia-voice-select");
  if (t && e)
    if (Array.from(t.options).find((n) => n.value === e))
      t.value = e, ee(e);
    else {
      t.value = "";
      const n = document.getElementById("cartesia-voice-info");
      n && (n.textContent = "Custom voice ID");
    }
}
function ee(e) {
  const t = document.getElementById("cartesia-voice-info");
  if (!t) return;
  if (!e) {
    t.textContent = "";
    return;
  }
  const a = Y.find((n) => n.voice_id === e);
  a && a.description ? t.textContent = a.description : t.textContent = "";
}
async function Se() {
  try {
    F = await h("/api/kokoro/voices", "GET", null, !1);
    const e = document.getElementById("kokoro-voice-select");
    if (!e) return;
    e.innerHTML = "", F.forEach((a) => {
      const n = document.createElement("option");
      n.value = a.id, n.textContent = a.name, e.appendChild(n);
    });
    const t = F.find((a) => a.id === "af_heart") || F[0];
    t && (e.value = t.id);
  } catch (e) {
    console.error("Error loading Kokoro voices:", e);
    const t = document.getElementById("kokoro-voice-select");
    t && (t.innerHTML = '<option value="">Failed to load voices</option>');
  }
}
function $e(e) {
  const t = document.getElementById("elevenlabs-settings"), a = document.getElementById("cartesia-settings"), n = document.getElementById("kokoro-settings");
  if (e === "cartesia")
    t && (t.style.display = "none"), a && (a.style.display = "block"), n && (n.style.display = "none"), Y.length === 0 && ce();
  else if (e === "kokoro") {
    t && (t.style.display = "none"), a && (a.style.display = "none"), n && (n.style.display = "block");
    const o = r("kokoro-speed");
    l("kokoro-speed-value").textContent = (parseInt(o.value) / 100).toFixed(1), F.length === 0 && Se();
  } else
    t && (t.style.display = "block"), a && (a.style.display = "none"), n && (n.style.display = "none");
}
async function st(e, t, a) {
  return h(`/api/characters/${e}/speak`, "POST", {
    text: t,
    show_text: a
  });
}
async function ct(e, t, a, n = null, o = null) {
  const s = {
    message: t,
    show_text: a
  };
  return n !== null && n !== "" && (s.twitch_chat_seconds = parseInt(n)), o && o.length > 0 && (s.images = o.map((c) => ({
    data: c.data,
    media_type: c.mediaType
  }))), h(`/api/characters/${e}/chat`, "POST", s);
}
async function ie(e) {
  return h(`/api/characters/${e}/memory`);
}
async function it(e) {
  return h(`/api/characters/${e}/memory`, "DELETE");
}
function X(e, t) {
  const a = document.getElementById("chat-history"), n = document.getElementById("chat-history-empty");
  if (!e || e.length === 0) {
    n && (n.style.display = "block"), a == null || a.querySelectorAll(".chat-bubble").forEach((o) => o.remove());
    return;
  }
  n && (n.style.display = "none"), a == null || a.querySelectorAll(".chat-bubble").forEach((o) => o.remove()), e.forEach((o) => {
    if (o.role === "context") {
      const s = o.content.split(`
`), c = s.slice(-4).map((v) => v.length > 60 ? v.substring(0, 57) + "..." : v).join(" | "), i = document.createElement("div");
      i.className = "chat-bubble context";
      const d = document.createElement("div");
      d.className = "chat-bubble-content", d.textContent = `📺 Twitch (${s.length}): ${c}`, i.appendChild(d), a == null || a.appendChild(i);
    } else {
      const s = document.createElement("div");
      s.className = `chat-bubble ${o.role}`;
      const c = document.createElement("div");
      c.className = "chat-bubble-label", c.textContent = o.role === "user" ? "You" : t;
      const i = document.createElement("div");
      if (i.className = "chat-bubble-content", o.interrupted && o.generated_text) {
        const d = o.content || "", v = o.generated_text || "";
        if (d) {
          const y = document.createElement("span");
          y.textContent = d, i.appendChild(y);
        }
        let w = "";
        if ((v.startsWith(d) || v.length > d.length) && (w = v.substring(d.length).trim()), w) {
          const y = document.createElement("span");
          y.style.textDecoration = "line-through", y.style.opacity = "0.6", y.textContent = " " + w, i.appendChild(y);
        }
        const m = document.createElement("span");
        m.style.cssText = "display: inline-block; margin-left: 8px; padding: 2px 6px; background: #ff6b6b33; color: #ff6b6b; border-radius: 4px; font-size: 0.7rem;", m.textContent = "⚡ interrupted", i.appendChild(m);
      } else
        i.textContent = o.content;
      s.appendChild(c), s.appendChild(i), a == null || a.appendChild(s);
    }
  }), a && (a.scrollTop = a.scrollHeight);
}
function ge(e, t, a) {
  const n = document.getElementById("chat-history"), o = document.getElementById("chat-history-empty");
  o && (o.style.display = "none");
  const s = document.createElement("div");
  s.className = `chat-bubble ${e}`;
  const c = document.createElement("div");
  c.className = "chat-bubble-label", c.textContent = e === "user" ? "You" : a;
  const i = document.createElement("div");
  i.className = "chat-bubble-content", i.textContent = t, s.appendChild(c), s.appendChild(i), n == null || n.appendChild(s), n && (n.scrollTop = n.scrollHeight);
}
function lt(e) {
  const t = document.getElementById("chat-history"), a = document.getElementById("chat-history-empty");
  a && (a.style.display = "none");
  const n = document.createElement("div");
  n.className = "chat-bubble context";
  const o = document.createElement("div");
  o.className = "chat-bubble-content", o.textContent = e, n.appendChild(o), t == null || t.appendChild(n), t && (t.scrollTop = t.scrollHeight);
}
let K = null, V = null;
function dt() {
  le();
  const e = xe("character-preview-canvas");
  if (!e) return;
  const t = e.getContext("2d");
  K = new Ne(t, e.width, e.height);
  const a = K, n = {
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
  function s() {
    t.clearRect(0, 0, e.width, e.height), a.update(), a.draw(), a.isAnimating() && (V = requestAnimationFrame(s));
  }
  s();
}
function le() {
  V && (cancelAnimationFrame(V), V = null), K && K.clear();
  const e = xe("character-preview-canvas");
  if (e) {
    const t = e.getContext("2d");
    t == null || t.clearRect(0, 0, e.width, e.height);
  }
}
const P = l("character-modal"), oe = He("character-form"), Te = l("character-modal-title");
function ut() {
  S = null, Te.textContent = "Create Character", oe.reset(), r("character-name").disabled = !1, r("character-color").value = "#e94560", r("character-icon").value = "🔊", r("character-stability").value = "50", l("character-stability-value").textContent = "0.50", r("character-similarity").value = "75", l("character-similarity-value").textContent = "0.75", r("character-voice-style").value = "0", l("character-style-value").textContent = "0.00", r("character-voice-speed").value = "100", l("character-speed-value").textContent = "1.0", r("character-volume").value = "100", l("character-volume-value").textContent = "100", u("character-text-style").value = "typewriter", r("character-font-family").value = "Arial", r("character-font-size").value = "48", r("character-text-duration").value = "3000", r("character-text-color").value = "#ffffff", r("character-stroke-color").value = "#000000", r("character-stroke-width").value = "0", l("character-stroke-width-value").textContent = "0", r("character-position-x").value = "50", l("character-pos-x-value").textContent = "50", r("character-position-y").value = "50", l("character-pos-y-value").textContent = "50", r("character-model").value = "anthropic/claude-sonnet-4.5", u("character-provider").innerHTML = '<option value="">Default (auto)</option>', u("character-provider").value = "", r("character-temperature").value = "70", l("character-temp-value").textContent = "0.7", r("character-max-tokens").value = "1024", u("character-tts-model").value = "eleven_multilingual_v2", l("tts-model-info").textContent = "", se("eleven_multilingual_v2"), r("kokoro-speed").value = "100", l("kokoro-speed-value").textContent = "1.0", r("character-memory-enabled").checked = !1, r("character-persist-memory").checked = !1, r("character-twitch-chat-enabled").checked = !1, r("character-twitch-chat-seconds").value = "60", r("character-twitch-chat-max").value = "20", P.classList.add("active");
}
function Me(e) {
  S = e, Te.textContent = "Edit Character";
  const t = e;
  r("character-name").value = e.name, r("character-name").disabled = !0, C("character-description").value = t.description || "", r("character-color").value = t.color, r("character-icon").value = t.icon;
  const a = e.tts_provider || "elevenlabs";
  if (u("character-tts-provider").value = a, $e(a), a === "cartesia" && e.tts_settings)
    ce().then(() => {
      const n = e.tts_settings, o = n.voice_id || "";
      r("cartesia-voice-id").value = o;
      const s = u("cartesia-voice-select");
      s && o && Array.from(s.options).find((v) => v.value === o) && (s.value = o), r("cartesia-model-id").value = n.model_id || "sonic-2024-12-12", u("cartesia-language").value = n.language || "en";
      const c = n.speed || 1, i = Math.max(0.6, Math.min(1.5, c));
      r("cartesia-speed").value = String(Math.round(i * 100)), l("cartesia-speed-value").textContent = i.toFixed(1), c !== i && console.warn(`Cartesia speed ${c} was clamped to ${i} (valid: 0.6-1.5)`), ee(o);
    });
  else if (a === "kokoro" && e.tts_settings)
    Se().then(() => {
      const n = e.tts_settings, o = n.voice || "af_heart", s = u("kokoro-voice-select");
      s && o && (s.value = o);
      const c = n.speed || 1;
      r("kokoro-speed").value = String(Math.round(c * 100)), l("kokoro-speed-value").textContent = c.toFixed(1);
    });
  else {
    const n = e.tts_settings || {};
    r("character-voice-id").value = n.voice_id || t.elevenlabs_voice_id;
    const o = n.model_id || t.elevenlabs_model_id || "eleven_multilingual_v2";
    u("character-tts-model").value = o, se(o), Ie(n.voice_id || t.elevenlabs_voice_id);
    const s = n.stability ?? t.voice_stability;
    r("character-stability").value = String(Math.round(s * 100)), l("character-stability-value").textContent = s.toFixed(2);
    const c = n.similarity_boost ?? t.voice_similarity_boost;
    r("character-similarity").value = String(Math.round(c * 100)), l("character-similarity-value").textContent = c.toFixed(2);
    const i = n.style ?? t.voice_style;
    r("character-voice-style").value = String(Math.round(i * 100)), l("character-style-value").textContent = i.toFixed(2);
    const d = n.speed ?? t.voice_speed;
    r("character-voice-speed").value = String(Math.round(d * 100)), l("character-speed-value").textContent = d.toFixed(1);
  }
  r("character-volume").value = String(Math.round(t.default_volume * 100)), l("character-volume-value").textContent = String(Math.round(t.default_volume * 100)), r("character-muted").checked = t.mute_state, u("character-text-style").value = t.default_text_style, r("character-font-family").value = e.text_font_family || "Arial", r("character-font-size").value = String(e.text_font_size || 48), r("character-text-duration").value = String(t.text_duration), r("character-text-color").value = e.text_color || "#ffffff", r("character-stroke-color").value = e.text_stroke_color || "#000000", r("character-stroke-width").value = String(e.text_stroke_width || 0), l("character-stroke-width-value").textContent = String(e.text_stroke_width || 0), r("character-position-x").value = String(Math.round((e.text_position_x || 0.5) * 100)), l("character-pos-x-value").textContent = String(Math.round((e.text_position_x || 0.5) * 100)), r("character-position-y").value = String(Math.round((e.text_position_y || 0.5) * 100)), l("character-pos-y-value").textContent = String(Math.round((e.text_position_y || 0.5) * 100)), C("character-prompt").value = e.system_prompt || "", r("character-model").value = e.openrouter_model || "", Ee(e.openrouter_model || "").then(() => {
    u("character-provider").value = t.provider || "";
  }), r("character-temperature").value = String(Math.round(t.temperature * 100)), l("character-temp-value").textContent = t.temperature.toFixed(1), r("character-max-tokens").value = String(t.max_tokens), r("character-memory-enabled").checked = t.memory_enabled || !1, r("character-persist-memory").checked = e.persist_memory || !1, r("character-twitch-chat-enabled").checked = t.twitch_chat_enabled || !1, r("character-twitch-chat-seconds").value = String(t.twitch_chat_window_seconds || 60), r("character-twitch-chat-max").value = String(t.twitch_chat_max_messages || 20), P.classList.add("active");
}
function J() {
  P.classList.remove("active"), S = null, le();
}
async function ht(e) {
  e.preventDefault();
  const t = u("character-tts-provider").value;
  let a = null;
  t === "cartesia" ? a = {
    voice_id: r("cartesia-voice-id").value,
    model_id: r("cartesia-model-id").value,
    language: u("cartesia-language").value,
    speed: parseInt(r("cartesia-speed").value) / 100
  } : t === "kokoro" ? a = {
    voice: u("kokoro-voice-select").value,
    speed: parseInt(r("kokoro-speed").value) / 100
  } : a = {
    voice_id: r("character-voice-id").value,
    model_id: u("character-tts-model").value,
    stability: parseInt(r("character-stability").value) / 100,
    similarity_boost: parseInt(r("character-similarity").value) / 100,
    style: parseInt(r("character-voice-style").value) / 100,
    speed: parseInt(r("character-voice-speed").value) / 100
  };
  const n = {
    name: r("character-name").value,
    description: C("character-description").value || null,
    color: r("character-color").value,
    icon: r("character-icon").value,
    // TTS provider abstraction
    tts_provider: t,
    tts_settings: a,
    // Legacy ElevenLabs fields (for backwards compatibility)
    elevenlabs_voice_id: r("character-voice-id").value,
    elevenlabs_model_id: u("character-tts-model").value,
    voice_stability: parseInt(r("character-stability").value) / 100,
    voice_similarity_boost: parseInt(r("character-similarity").value) / 100,
    voice_style: parseInt(r("character-voice-style").value) / 100,
    voice_speed: parseInt(r("character-voice-speed").value) / 100,
    default_volume: parseInt(r("character-volume").value) / 100,
    mute_state: r("character-muted").checked,
    default_text_style: u("character-text-style").value,
    text_font_family: r("character-font-family").value,
    text_font_size: parseInt(r("character-font-size").value),
    text_duration: parseInt(r("character-text-duration").value),
    text_color: r("character-text-color").value,
    text_stroke_color: parseInt(r("character-stroke-width").value) > 0 ? r("character-stroke-color").value : null,
    text_stroke_width: parseInt(r("character-stroke-width").value),
    text_position_x: parseInt(r("character-position-x").value) / 100,
    text_position_y: parseInt(r("character-position-y").value) / 100,
    system_prompt: C("character-prompt").value || null,
    model: r("character-model").value,
    provider: u("character-provider").value || null,
    temperature: parseInt(r("character-temperature").value) / 100,
    max_tokens: parseInt(r("character-max-tokens").value),
    memory_enabled: r("character-memory-enabled").checked,
    persist_memory: r("character-persist-memory").checked,
    twitch_chat_enabled: r("character-twitch-chat-enabled").checked,
    twitch_chat_window_seconds: parseInt(r("character-twitch-chat-seconds").value),
    twitch_chat_max_messages: parseInt(r("character-twitch-chat-max").value),
    // Optimistic concurrency control - send timestamp to detect conflicts
    expected_updated_at: (S == null ? void 0 : S.updated_at) || null
  };
  try {
    if (S) {
      const o = await et(S.name, n, !1);
      if (o && o.status === 409) {
        const s = await h(`/api/characters/${encodeURIComponent(S.name)}`, "GET", null, !1);
        s && !("error" in s) ? (Me(s), f("Someone else modified this character. Please review the updated values and try again.", "warning")) : (J(), f("Character was modified. Please try again.", "warning"));
        return;
      }
    } else
      await Ze(n);
    J();
  } catch (o) {
    console.error("Error saving character:", o), alert("Error saving character. Check console for details.");
  }
}
const O = l("speak-modal");
function mt(e) {
  const t = b.find((a) => a.name === e);
  t && (M = t, l("speak-modal-title").textContent = `Speak as ${t.name}`, C("speak-text").value = "", r("speak-show-text").checked = !0, l("speak-status").style.display = "none", D("speak-send-btn").disabled = !1, O.classList.add("active"));
}
function Be() {
  O.classList.remove("active"), M = null;
}
async function pt() {
  if (!M) return;
  const e = C("speak-text").value.trim(), t = r("speak-show-text").checked;
  if (!e) {
    alert("Please enter text to speak");
    return;
  }
  const a = l("speak-status"), n = l("speak-status-text"), o = D("speak-send-btn"), s = D("speak-stop-btn");
  a.style.display = "block", n.textContent = "Speaking...", o.disabled = !0, s.style.display = "inline-block", I = M.name, _ = "speak", A = !1;
  try {
    const c = await st(M.name, e, t);
    c.error || c.detail ? (n.textContent = `Error: ${c.error || c.detail}`, s.style.display = "none", I = null, _ = null) : (n.textContent = "Playing audio...", C("speak-text").value = "", Q());
  } catch (c) {
    console.error("Speak error:", c), n.textContent = `Error: ${c.message || "Unknown error"}`, s.style.display = "none", I = null, _ = null;
  } finally {
    o.disabled = !1;
  }
}
async function ft(e) {
  const t = e === "speak" ? M == null ? void 0 : M.name : p == null ? void 0 : p.name;
  if (!t) return;
  const a = document.getElementById(`${e}-status-text`), n = document.getElementById(`${e}-stop-btn`);
  a && (a.textContent = "Stopping..."), n && (n.disabled = !0);
  try {
    const o = await h(`/api/characters/${t}/stop`, "POST");
    a && (o.was_active ? a.textContent = "Stopped" : a.textContent = "Nothing to stop"), e === "chat" && o.was_active && setTimeout(async () => {
      try {
        const s = await ie(t);
        l("chat-memory-count").textContent = `Memory: ${s.message_count} messages`, X(s.messages, t);
      } catch (s) {
        console.error("Error refreshing memory after stop:", s);
      }
    }, 500);
  } catch (o) {
    console.error("Stop error:", o), a && (a.textContent = `Stop failed: ${o.message}`);
  } finally {
    n && (n.disabled = !1, n.style.display = "none"), I = null, _ = null, A = !1;
    const o = document.getElementById(`${e}-send-btn`);
    o && (o.disabled = !1);
  }
}
const $ = document.getElementById("chat-modal"), we = 20, _e = 5;
function de() {
  T = [];
  const e = document.getElementById("chat-image-previews");
  if (e)
    for (; e.firstChild; )
      e.removeChild(e.firstChild);
}
function Le(e, t) {
  if (T.length >= _e) {
    f(`Maximum ${_e} images allowed`, "warning");
    return;
  }
  T.push({ data: e, mediaType: t });
  const a = l("chat-image-previews"), n = document.createElement("div");
  n.className = "image-preview-thumb", n.dataset.index = String(T.length - 1);
  const o = document.createElement("img");
  o.src = `data:${t};base64,${e}`;
  const s = document.createElement("button");
  s.className = "remove-btn", s.textContent = "×", s.onclick = function() {
    const c = parseInt(n.dataset.index || "0");
    T.splice(c, 1), n.remove(), document.querySelectorAll("#chat-image-previews .image-preview-thumb").forEach((i, d) => {
      i.dataset.index = String(d);
    });
  }, n.appendChild(o), n.appendChild(s), a.appendChild(n);
}
async function Ae(e) {
  if (!e.type.startsWith("image/")) {
    f("Only image files are supported", "error");
    return;
  }
  if (e.size > we * 1024 * 1024) {
    f(`Image too large (max ${we}MB)`, "error");
    return;
  }
  return new Promise((t) => {
    const a = new FileReader();
    a.onload = (n) => {
      var i;
      const s = ((i = n.target) == null ? void 0 : i.result).split(",")[1], c = e.type || "image/png";
      Le(s, c), t();
    }, a.readAsDataURL(e);
  });
}
function vt() {
  r("chat-image-input").click();
}
async function yt(e) {
  const t = e.target, a = t.files;
  if (a)
    for (const n of a)
      await Ae(n);
  t.value = "";
}
async function gt() {
  try {
    const e = await navigator.mediaDevices.getDisplayMedia({
      video: !0
    }), t = document.createElement("video");
    t.srcObject = e, await t.play(), await new Promise((c) => {
      t.readyState >= 2 ? c() : t.onloadeddata = () => c();
    });
    const a = document.createElement("canvas");
    a.width = t.videoWidth, a.height = t.videoHeight, a.getContext("2d").drawImage(t, 0, 0), e.getTracks().forEach((c) => c.stop());
    const s = a.toDataURL("image/png").split(",")[1];
    Le(s, "image/png"), f("Screen captured!", "success");
  } catch (e) {
    e instanceof Error && e.name === "NotAllowedError" ? f("Screen capture permission denied", "warning") : (console.error("Screen capture error:", e), f("Screen capture failed", "error"));
  }
}
function be(e) {
  var a;
  const t = (a = e.clipboardData) == null ? void 0 : a.items;
  if (t) {
    for (const n of t)
      if (n.type.startsWith("image/")) {
        e.preventDefault();
        const o = n.getAsFile();
        o && Ae(o);
      }
  }
}
async function wt(e) {
  const t = b.find((n) => n.name === e);
  if (!t) return;
  if (!t.system_prompt) {
    alert('This character has no AI system prompt configured. Use "Speak" for direct TTS.');
    return;
  }
  p = t, l("chat-modal-title").textContent = `Chat with ${t.name}`, C("chat-message").value = "", r("chat-show-text").checked = !0, r("chat-include-twitch").checked = !0, r("chat-twitch-seconds").value = "", l("chat-status").style.display = "none", l("chat-twitch-details").style.display = "none", D("chat-send-btn").disabled = !1, de();
  const a = C("chat-message");
  a.removeEventListener("paste", be), a.addEventListener("paste", be);
  try {
    const n = await ie(e);
    l("chat-memory-count").textContent = `Memory: ${n.message_count} messages${t.memory_enabled ? "" : " (disabled)"}`, X(n.messages, e);
  } catch {
    l("chat-memory-count").textContent = "Memory: 0 messages", X([], e);
  }
  $ == null || $.classList.add("active");
}
function Pe() {
  $ == null || $.classList.remove("active"), p = null, de();
}
async function _t() {
  if (!p) return;
  const e = C("chat-message").value.trim(), t = r("chat-show-text").checked, a = r("chat-include-twitch").checked;
  let n = r("chat-twitch-seconds").value;
  if (a || (n = "0"), !e) {
    alert("Please enter a message");
    return;
  }
  const o = l("chat-status"), s = l("chat-status-text"), c = D("chat-send-btn"), i = D("chat-stop-btn");
  o.style.display = "block", s.textContent = "Generating...", c.disabled = !0, i.style.display = "inline-block", I = p.name, _ = "chat", A = !1;
  try {
    const d = T.length > 0, v = d ? `[${T.length} image(s)] ${e}` : e;
    ge("user", v, p.name), C("chat-message").value = "";
    const w = d ? [...T] : null;
    de();
    const m = await ct(p.name, e, t, n, w);
    if (m.error || m.detail)
      s.textContent = `Error: ${m.error || m.detail}`, i.style.display = "none", I = null, _ = null;
    else {
      if (m.twitch_chat_context) {
        const U = m.twitch_chat_context.split(`
`), Fe = U.slice(-4).map((te) => te.length > 60 ? te.substring(0, 57) + "..." : te).join(" | ");
        lt(`📺 Twitch chat (${U.length}): ${Fe}`);
      }
      ge("assistant", m.response_text || "", p.name);
      let y = "Playing audio...";
      const z = document.getElementById("chat-twitch-details"), ue = document.getElementById("chat-twitch-summary"), he = document.getElementById("chat-twitch-context-text");
      if (m.twitch_chat_context) {
        const U = m.twitch_chat_context.split(`
`).length;
        y += ` (${U} chat msgs)`, ue && (ue.textContent = `Twitch Chat Context (${U} messages)`), he && (he.textContent = m.twitch_chat_context), z && (z.style.display = "block");
      } else
        z && (z.style.display = "none");
      s.textContent = y, Q();
      const Ue = await ie(p.name), Re = p;
      l("chat-memory-count").textContent = `Memory: ${Ue.message_count} messages${Re.memory_enabled ? "" : " (not saving)"}`;
    }
  } catch (d) {
    console.error("Chat error:", d), s.textContent = `Error: ${d instanceof Error ? d.message : "Unknown error"}`, i.style.display = "none", I = null, _ = null;
  } finally {
    c.disabled = !1;
  }
}
async function bt() {
  if (p && confirm(`Clear conversation memory for ${p.name}?`))
    try {
      await it(p.name);
      const e = document.getElementById("chat-memory-count"), t = document.getElementById("chat-status"), a = document.getElementById("chat-status-text"), n = document.getElementById("chat-twitch-details");
      e && (e.textContent = "Memory: 0 messages"), t && (t.style.display = "block"), a && (a.textContent = "Memory cleared!"), X([], p.name), n && (n.style.display = "none");
    } catch (e) {
      console.error("Error clearing memory:", e), alert("Error clearing memory");
    }
}
function Ct(e) {
  if (!e || e.length === 0) {
    ye.innerHTML = '<div class="history-item"><span class="history-content">No history yet</span></div>';
    return;
  }
  ye.innerHTML = e.map((t) => {
    const a = new Date(t.timestamp).toLocaleTimeString();
    return `
                <div class="history-item">
                    <span class="history-channel">${k(t.channel)}</span>
                    <span class="history-content">${k(t.content)}</span>
                    <span class="history-time">${k(a)}</span>
                </div>
            `;
  }).join("");
}
function re() {
  if (H) {
    if (b.length === 0) {
      H.innerHTML = `
                <div class="no-channels">
                    <p>No characters configured yet.</p>
                    <p>Click "Create Character" to add one.</p>
                </div>
            `;
      return;
    }
    H.innerHTML = b.map((e) => xt(e)).join("");
  }
}
function xt(e) {
  var m, y;
  let t = "", a = "offline";
  e.connected ? e.streaming ? (t = "streaming", a = "streaming") : e.playing ? (t = "playing", a = "playing") : a = "ready" : (t = "", a = "offline");
  const n = e.connected ? "" : "disconnected", o = e.system_prompt ? '<span class="voice-indicator">AI</span>' : "", s = k(e.description || (e.system_prompt ? e.system_prompt.substring(0, 80) + "..." : "No description")), c = k(e.name), i = k(e.icon), d = We(e.color), v = k(e.model ? e.model.split("/").pop() : "");
  let w;
  return e.tts_provider === "cartesia" ? w = k((((m = e.tts_settings) == null ? void 0 : m.model_id) || "sonic").replace("sonic-", "")) : e.tts_provider === "kokoro" ? w = k(((y = e.tts_settings) == null ? void 0 : y.voice) || "af_heart") : w = k((e.elevenlabs_model_id || "multilingual_v2").replace("eleven_", "").replace("_", " ")), `
            <div class="channel-card ${n}" data-character="${c}" style="border-left-color: ${d}">
                <div class="channel-header">
                    <div class="channel-name">
                        <span class="channel-icon">${i}</span>
                        ${c}
                        ${o}
                    </div>
                    <span class="channel-status ${t}">${a}</span>
                </div>
                <p class="channel-description">${s}</p>
                <div class="channel-controls">
                    <div class="control-row" style="font-size: 0.75rem; color: var(--text-secondary);">
                        <span>TTS: ${e.tts_provider === "cartesia" ? "Cartesia" : e.tts_provider === "kokoro" ? "Kokoro" : "ElevenLabs"}</span>
                        <span>${w}</span>
                    </div>
                    ${e.system_prompt ? `<div class="control-row" style="font-size: 0.75rem; color: var(--text-secondary);"><span>AI: ${v}</span></div>` : ""}
                </div>
                <div class="channel-actions">
                    <button data-action="speak" data-character="${c}">Speak</button>
                    ${e.system_prompt ? `<button data-action="chat" data-character="${c}">Chat</button>` : ""}
                    <button data-action="copy-url" data-character="${c}" title="Copy browser source URL for OBS">Copy URL</button>
                    <button data-action="rotate-token" data-character="${c}" title="Invalidate old URL and generate new token">Rotate</button>
                    <button data-action="edit" data-character="${c}">Edit</button>
                    <button class="secondary" data-action="delete" data-character="${c}">Delete</button>
                </div>
            </div>
        `;
}
window.openCreateCharacterModal = ut;
window.closeCharacterModal = J;
window.editCharacter = async function(e) {
  const t = await h(`/api/characters/${encodeURIComponent(e)}`);
  t && !("error" in t) ? Me(t) : f("Failed to load character", "error");
};
window.deleteCharacter = tt;
window.openSpeakModal = mt;
window.closeSpeakModal = Be;
window.sendSpeak = pt;
window.stopGeneration = ft;
window.openChatModal = wt;
window.closeChatModal = Pe;
window.sendChat = _t;
window.clearChatMemory = bt;
window.attachImage = vt;
window.handleImageSelect = yt;
window.captureScreen = gt;
window.previewCharacterTextStyle = dt;
window.stopCharacterTextPreview = le;
window.updateProviderDropdown = Ee;
window.loadVoiceModels = Ie;
window.updateModelInfo = se;
window.toggleTTSProvider = $e;
window.updateCartesiaVoiceInfo = ee;
window.loadCartesiaVoices = ce;
window.selectCartesiaVoice = ot;
window.onCartesiaManualIdChange = rt;
window.copyCharacterUrl = async function(e) {
  const t = b.find((n) => n.name === e);
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
        const s = o.textContent;
        o.textContent = "Copied!", setTimeout(() => {
          o.textContent = s;
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
      const t = await h(`/api/characters/${encodeURIComponent(e)}/rotate-token`, "POST");
      if (t != null && t.success) {
        const a = b.find((n) => n.name === e);
        a && t.ws_token && (a.ws_token = t.ws_token), f("Token rotated. Copy new URL for OBS.", "success");
      } else
        f((t == null ? void 0 : t.detail) || "Failed to rotate token", "error");
    } catch (t) {
      console.error("Failed to rotate token:", t), f("Failed to rotate token", "error");
    }
};
const ne = document.getElementById("twitch-user"), Ce = document.getElementById("twitch-username");
async function De() {
  if (!(!ne || !Ce))
    try {
      const t = await (await fetch("/api/twitch/status")).json();
      t.connected && t.channel ? (Ce.textContent = t.channel, ne.style.display = "inline-flex") : ne.style.display = "none";
    } catch (e) {
      console.error("Error checking Twitch status:", e);
    }
}
const x = document.getElementById("channel-switcher");
async function kt() {
  if (x)
    try {
      const t = await (await fetch("/api/moderators/accessible-channels")).json();
      if (!t.channels || t.channels.length <= 1) {
        x.style.display = "none", E && t.channels && !t.channels.find((a) => a.tenant_id === E) && (E = null, localStorage.removeItem("effectiveChannel"));
        return;
      }
      if (x.innerHTML = "", t.channels.forEach((a) => {
        const n = document.createElement("option");
        n.value = a.tenant_id, n.textContent = a.is_own ? `${a.username} (You)` : a.username, x.appendChild(n);
      }), E)
        x.value = E;
      else {
        const a = t.channels.find((n) => n.is_own);
        a && (x.value = a.tenant_id);
      }
      x.style.display = "inline-flex", x.onchange = () => {
        const a = x.value, n = t.channels.find((o) => o.is_own);
        a === (n == null ? void 0 : n.tenant_id) ? (localStorage.removeItem("effectiveChannel"), window.location.href = "/") : (localStorage.setItem("effectiveChannel", a), window.location.href = `/?channel=${encodeURIComponent(a)}`);
      };
    } catch (e) {
      console.error("Error loading accessible channels:", e), x.style.display = "none";
    }
}
oe && oe.addEventListener("submit", ht);
P && P.addEventListener("click", (e) => {
  e.target === P && J();
});
O && O.addEventListener("click", (e) => {
  e.target === O && Be();
});
$ && $.addEventListener("click", (e) => {
  e.target === $ && Pe();
});
H && H.addEventListener("click", (e) => {
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
E = qe();
ke();
Z();
Qe();
Q();
De();
nt();
kt();
setInterval(Q, 1e4);
setInterval(De, 15e3);
