import { TextAnimator as Oe } from "./text-animator.js";
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
function x(e) {
  return document.getElementById(e);
}
function Ee(e) {
  return document.getElementById(e);
}
function Ge(e) {
  return document.getElementById(e);
}
let g = null, L = null, B = 0;
const ze = 1e3, Ve = 3e4, j = 10, pe = 6e4, je = 3e4;
let W = Date.now(), N = null, R = null, fe = [], _ = [], S = null, f = null, M = null, Y = [], I = null, b = null, P = !1, T = [], oe = null, E = null;
function qe() {
  const t = new URLSearchParams(window.location.search).get("channel");
  return t ? (localStorage.setItem("effectiveChannel", t), t) : localStorage.getItem("effectiveChannel");
}
function We(e) {
  if (!E) return e;
  const t = e.includes("?") ? "&" : "?";
  return `${e}${t}channel=${encodeURIComponent(E)}`;
}
const ve = document.getElementById("ws-status"), ye = document.getElementById("ws-status-text"), O = document.getElementById("characters-container"), ge = document.getElementById("history-list");
function k(e) {
  if (e == null) return "";
  const t = document.createElement("div");
  return t.textContent = String(e), t.innerHTML;
}
function Ye(e, t = "#9146ff") {
  return e && /^#[0-9a-fA-F]{3,4}$|^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$/.test(e) ? e : t;
}
function Ke() {
  return oe;
}
function Ie() {
  let t = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/dashboard`;
  E && (t += `?channel=${encodeURIComponent(E)}`), g = new WebSocket(t), g.onopen = () => {
    ve.classList.add("connected"), ye.textContent = "Connected", B = 0, W = Date.now(), Qe(), L && (clearTimeout(L), L = null);
  }, g.onclose = () => {
    ve.classList.remove("connected"), ye.textContent = "Disconnected", Je(), Xe();
  }, g.onerror = (a) => {
    console.error("Dashboard WebSocket error:", a);
  }, g.onmessage = (a) => {
    try {
      const n = JSON.parse(a.data);
      Ze(n);
    } catch (n) {
      console.error("Error parsing message:", n);
    }
  };
}
function Xe() {
  if (!L) {
    if (B >= j) {
      console.log(`[dashboard] Max reconnect attempts (${j}) reached, reloading page...`), location.reload();
      return;
    }
    const e = Math.min(
      ze * Math.pow(2, B),
      Ve
    );
    B++, console.log(`[dashboard] Reconnecting in ${e}ms (attempt ${B}/${j})...`), L = setTimeout(() => {
      L = null, Ie();
    }, e);
  }
}
function Je() {
  N || (N = setInterval(async () => {
    if (!(g && g.readyState === WebSocket.OPEN))
      try {
        (await fetch("/health", { signal: AbortSignal.timeout(5e3) })).ok && B >= j / 2 && (console.log("[dashboard] Server healthy but WebSocket failing, reloading page..."), location.reload());
      } catch {
      }
  }, je));
}
function Qe() {
  N && (clearInterval(N), N = null);
}
setInterval(() => {
  g && g.readyState === WebSocket.OPEN && Date.now() - W > pe && (console.log(`[dashboard] No ping received in ${pe}ms, connection stale - reconnecting...`), W = Date.now(), g.close());
}, 1e4);
function Ze(e) {
  if (e.type === "ping") {
    g && g.readyState === WebSocket.OPEN && g.send(JSON.stringify({ event: "pong", ts: e.ts })), W = Date.now();
    return;
  }
  if (e.type === "hello") {
    const t = e.build_id;
    if (e.tenant_id && (oe = e.tenant_id, console.log(`[dashboard] Tenant ID: ${oe}`)), R === null)
      R = t ?? null, console.log(`[dashboard] Server build ID: ${R}`);
    else if (R !== t) {
      console.log(`[dashboard] Server version changed (${R} -> ${t}), refreshing page...`), location.reload();
      return;
    } else
      console.log("[dashboard] Reconnected to same server version");
    return;
  }
  if (e.type === "characters") {
    const t = Ke(), a = e.characters, n = new Map(a.map((o) => [o.name, o]));
    if (_ = _.map((o) => {
      var c, i;
      const s = `${t}:${o.name}`;
      return {
        ...o,
        connected: n.has(s),
        playing: ((c = n.get(s)) == null ? void 0 : c.playing) || !1,
        streaming: ((i = n.get(s)) == null ? void 0 : i.streaming) || !1
      };
    }), se(), I && b) {
      const o = `${t}:${I}`, s = n.get(o);
      if (s && (s.streaming && (P = !0), P && !s.streaming)) {
        const c = document.getElementById(`${b}-stop-btn`), i = document.getElementById(`${b}-status-text`);
        c && (c.style.display = "none"), i && (i.textContent = "Complete!"), I = null, b = null, P = !1;
      }
    }
  } else e.type === "character_sync" && (_ = e.characters, se(), z || console.log("Character data synced from server"), z = !1);
}
let z = !1;
function m(e, t = "info", a = 4e3) {
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
      return n && m(`API Error: ${i}`, "error"), console.error(`API Error [${t} ${e}]:`, i), { error: i, status: s.status };
    }
    return c;
  } catch (s) {
    const c = s.message || "Network error";
    return n && m(`Connection Error: ${c}`, "error"), console.error(`Fetch Error [${t} ${e}]:`, s), { error: c, networkError: !0 };
  }
}
async function et() {
  const e = await h("/api/presets");
  return Array.isArray(e) && (fe = e), fe;
}
async function Z() {
  const e = await h("/api/history");
  Array.isArray(e) && Et(e);
}
async function ee() {
  const e = await h(We("/api/characters"));
  return Array.isArray(e) && (_ = e, se()), _;
}
async function tt(e) {
  z = !0;
  const t = await h("/api/characters", "POST", e);
  return await ee(), t;
}
async function nt(e, t, a = !0) {
  z = !0;
  const n = await h(`/api/characters/${e}`, "PUT", t, a);
  return await ee(), n;
}
async function at(e) {
  confirm(`Delete character "${e}"? This cannot be undone.`) && (z = !0, await h(`/api/characters/${e}`, "DELETE"), await ee());
}
async function Se(e) {
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
async function ot() {
  const e = document.getElementById("character-tts-model");
  if (e)
    try {
      const t = await h("/api/elevenlabs/models", "GET", null, !1);
      Array.isArray(t) && (Y = t, e.innerHTML = t.map((a) => {
        const n = a.name || a.model_id;
        return `<option value="${a.model_id}">${n}</option>`;
      }).join(""));
    } catch (t) {
      console.error("Error fetching ElevenLabs models:", t);
    }
}
async function $e(e) {
  const t = u("character-tts-model"), a = document.getElementById("tts-model-info");
  if (!(!t || !e)) {
    a && (a.textContent = "");
    try {
      const n = await h(`/api/elevenlabs/voices/${e}`, "GET", null, !1);
      if (n != null && n.high_quality_base_model_ids && n.high_quality_base_model_ids.length > 0) {
        const o = new Set(n.high_quality_base_model_ids);
        Array.from(t.options).forEach((s) => {
          if (o.has(s.value)) {
            const c = Y.find((i) => i.model_id === s.value);
            s.textContent = `${(c == null ? void 0 : c.name) || s.value} (Recommended)`;
          } else {
            const c = Y.find((i) => i.model_id === s.value);
            s.textContent = (c == null ? void 0 : c.name) || s.value;
          }
        }), a && (a.textContent = `Voice "${n.name}" is optimized for: ${n.high_quality_base_model_ids.join(", ")}`);
      }
    } catch (n) {
      console.error("Error fetching voice info:", n), a && (a.textContent = "Could not fetch voice info");
    }
  }
}
const rt = {
  eleven_v3: "Latest flagship model with emotionally rich, expressive speech. 70+ languages. Best for audiobooks & dramatic content. Not optimized for real-time.",
  eleven_multilingual_v2: "Advanced emotionally-aware synthesis. 29 languages. Most stable for long-form. Higher latency but best quality.",
  eleven_flash_v2_5: "Fastest model (~75ms latency). 32 languages. 50% lower cost. Best for real-time agents & bulk processing.",
  eleven_turbo_v2_5: "Balanced quality & speed (~250ms). 32 languages. Good middle-ground between Flash and Multilingual.",
  eleven_flash_v2: "Ultra-fast for real-time (~75ms). English only. Great for conversational agents.",
  eleven_turbo_v2: "Quality-focused with low latency (~250ms). English only. Good balance for English projects.",
  eleven_multilingual_v1: "Legacy multilingual model. Use v2 for better results.",
  eleven_monolingual_v1: "Legacy English model. Use newer models for better quality."
};
function ce(e) {
  const t = document.getElementById("tts-model-info"), a = document.getElementById("voice-style-row"), n = document.getElementById("voice-similarity-row"), o = Y.find((s) => s.model_id === e);
  o && (a && (a.style.display = o.can_use_style ? "" : "none"), n && (n.style.display = o.can_use_speaker_boost ? "" : "none"), t && (t.textContent = rt[e] || ""));
}
let K = [], H = [];
async function ie() {
  try {
    K = await h("/api/cartesia/voices", "GET", null, !1);
    const e = document.getElementById("cartesia-voice-select");
    if (!e) return;
    e.innerHTML = '<option value="">-- Select a voice --</option>', K.forEach((t) => {
      const a = document.createElement("option");
      a.value = t.voice_id, a.textContent = `${t.name} (${t.language})`, e.appendChild(a);
    });
  } catch (e) {
    console.error("Error loading Cartesia voices:", e);
    const t = document.getElementById("cartesia-voice-select");
    t && (t.innerHTML = '<option value="">Failed to load voices</option>');
  }
}
function st(e) {
  const t = document.getElementById("cartesia-voice-id");
  t && e && (t.value = e), te(e);
}
function ct(e) {
  const t = document.getElementById("cartesia-voice-select");
  if (t && e)
    if (Array.from(t.options).find((n) => n.value === e))
      t.value = e, te(e);
    else {
      t.value = "";
      const n = document.getElementById("cartesia-voice-info");
      n && (n.textContent = "Custom voice ID");
    }
}
function te(e) {
  const t = document.getElementById("cartesia-voice-info");
  if (!t) return;
  if (!e) {
    t.textContent = "";
    return;
  }
  const a = K.find((n) => n.voice_id === e);
  a && a.description ? t.textContent = a.description : t.textContent = "";
}
async function Te() {
  try {
    H = await h("/api/kokoro/voices", "GET", null, !1);
    const e = document.getElementById("kokoro-voice-select");
    if (!e) return;
    e.innerHTML = "", H.forEach((a) => {
      const n = document.createElement("option");
      n.value = a.id, n.textContent = a.name, e.appendChild(n);
    });
    const t = H.find((a) => a.id === "af_heart") || H[0];
    t && (e.value = t.id);
  } catch (e) {
    console.error("Error loading Kokoro voices:", e);
    const t = document.getElementById("kokoro-voice-select");
    t && (t.innerHTML = '<option value="">Failed to load voices</option>');
  }
}
let F = !1;
async function it() {
  const e = u("kokoro-voice-select").value, t = parseInt(r("kokoro-speed").value) / 100, a = r("kokoro-preview-text").value.trim() || "Hello! This is a voice preview.";
  if (!e) {
    m("Please select a voice first", "warning");
    return;
  }
  if (F)
    return;
  const n = document.getElementById("kokoro-preview-btn"), o = n.textContent || "Preview";
  n.disabled = !0, n.textContent = "Loading...", F = !0;
  try {
    const s = await fetch("/api/kokoro/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voice: e, speed: t, text: a })
    });
    if (!s.ok)
      throw new Error(`HTTP ${s.status}`);
    const c = await s.arrayBuffer(), i = document.getElementById("kokoro-preview-player"), d = new Blob([c], { type: "audio/wav" });
    i.src = URL.createObjectURL(d), n.textContent = "Playing...", i.onended = () => {
      F = !1, n.disabled = !1, n.textContent = o;
    }, i.onerror = () => {
      F = !1, n.disabled = !1, n.textContent = o, m("Audio playback failed", "error");
    }, await i.play();
  } catch (s) {
    console.error("Preview error:", s), m(`Preview failed: ${s}`, "error"), F = !1, n.disabled = !1, n.textContent = o;
  }
}
function Me(e) {
  const t = document.getElementById("elevenlabs-settings"), a = document.getElementById("cartesia-settings"), n = document.getElementById("kokoro-settings");
  if (e === "cartesia")
    t && (t.style.display = "none"), a && (a.style.display = "block"), n && (n.style.display = "none"), K.length === 0 && ie();
  else if (e === "kokoro") {
    t && (t.style.display = "none"), a && (a.style.display = "none"), n && (n.style.display = "block");
    const o = r("kokoro-speed");
    l("kokoro-speed-value").textContent = (parseInt(o.value) / 100).toFixed(1), H.length === 0 && Te();
  } else
    t && (t.style.display = "block"), a && (a.style.display = "none"), n && (n.style.display = "none");
}
async function lt(e, t, a) {
  return h(`/api/characters/${e}/speak`, "POST", {
    text: t,
    show_text: a
  });
}
async function dt(e, t, a, n = null, o = null) {
  const s = {
    message: t,
    show_text: a
  };
  return n !== null && n !== "" && (s.twitch_chat_seconds = parseInt(n)), o && o.length > 0 && (s.images = o.map((c) => ({
    data: c.data,
    media_type: c.mediaType
  }))), h(`/api/characters/${e}/chat`, "POST", s);
}
async function le(e) {
  return h(`/api/characters/${e}/memory`);
}
async function ut(e) {
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
        const p = document.createElement("span");
        p.style.cssText = "display: inline-block; margin-left: 8px; padding: 2px 6px; background: #ff6b6b33; color: #ff6b6b; border-radius: 4px; font-size: 0.7rem;", p.textContent = "⚡ interrupted", i.appendChild(p);
      } else
        i.textContent = o.content;
      s.appendChild(c), s.appendChild(i), a == null || a.appendChild(s);
    }
  }), a && (a.scrollTop = a.scrollHeight);
}
function we(e, t, a) {
  const n = document.getElementById("chat-history"), o = document.getElementById("chat-history-empty");
  o && (o.style.display = "none");
  const s = document.createElement("div");
  s.className = `chat-bubble ${e}`;
  const c = document.createElement("div");
  c.className = "chat-bubble-label", c.textContent = e === "user" ? "You" : a;
  const i = document.createElement("div");
  i.className = "chat-bubble-content", i.textContent = t, s.appendChild(c), s.appendChild(i), n == null || n.appendChild(s), n && (n.scrollTop = n.scrollHeight);
}
function ht(e) {
  const t = document.getElementById("chat-history"), a = document.getElementById("chat-history-empty");
  a && (a.style.display = "none");
  const n = document.createElement("div");
  n.className = "chat-bubble context";
  const o = document.createElement("div");
  o.className = "chat-bubble-content", o.textContent = e, n.appendChild(o), t == null || t.appendChild(n), t && (t.scrollTop = t.scrollHeight);
}
let J = null, q = null;
function mt() {
  de();
  const e = Ee("character-preview-canvas");
  if (!e) return;
  const t = e.getContext("2d");
  J = new Oe(t, e.width, e.height);
  const a = J, n = {
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
    t.clearRect(0, 0, e.width, e.height), a.update(), a.draw(), a.isAnimating() && (q = requestAnimationFrame(s));
  }
  s();
}
function de() {
  q && (cancelAnimationFrame(q), q = null), J && J.clear();
  const e = Ee("character-preview-canvas");
  if (e) {
    const t = e.getContext("2d");
    t == null || t.clearRect(0, 0, e.width, e.height);
  }
}
const A = l("character-modal"), re = Ge("character-form"), Be = l("character-modal-title");
function pt() {
  S = null, Be.textContent = "Create Character", re.reset(), r("character-name").disabled = !1, r("character-color").value = "#e94560", r("character-icon").value = "🔊", r("character-stability").value = "50", l("character-stability-value").textContent = "0.50", r("character-similarity").value = "75", l("character-similarity-value").textContent = "0.75", r("character-voice-style").value = "0", l("character-style-value").textContent = "0.00", r("character-voice-speed").value = "100", l("character-speed-value").textContent = "1.0", r("character-volume").value = "100", l("character-volume-value").textContent = "100", u("character-text-style").value = "typewriter", r("character-font-family").value = "Arial", r("character-font-size").value = "48", r("character-text-duration").value = "3000", r("character-text-color").value = "#ffffff", r("character-stroke-color").value = "#000000", r("character-stroke-width").value = "0", l("character-stroke-width-value").textContent = "0", r("character-position-x").value = "50", l("character-pos-x-value").textContent = "50", r("character-position-y").value = "50", l("character-pos-y-value").textContent = "50", r("character-model").value = "anthropic/claude-sonnet-4.5", u("character-provider").innerHTML = '<option value="">Default (auto)</option>', u("character-provider").value = "", r("character-temperature").value = "70", l("character-temp-value").textContent = "0.7", r("character-max-tokens").value = "1024", u("character-tts-model").value = "eleven_multilingual_v2", l("tts-model-info").textContent = "", ce("eleven_multilingual_v2"), r("kokoro-speed").value = "100", l("kokoro-speed-value").textContent = "1.0", r("character-memory-enabled").checked = !1, r("character-persist-memory").checked = !1, r("character-twitch-chat-enabled").checked = !1, r("character-twitch-chat-seconds").value = "60", r("character-twitch-chat-max").value = "20", A.classList.add("active");
}
function Le(e) {
  S = e, Be.textContent = "Edit Character";
  const t = e;
  r("character-name").value = e.name, r("character-name").disabled = !0, x("character-description").value = t.description || "", r("character-color").value = t.color, r("character-icon").value = t.icon;
  const a = e.tts_provider || "elevenlabs";
  if (u("character-tts-provider").value = a, Me(a), a === "cartesia" && e.tts_settings)
    ie().then(() => {
      const n = e.tts_settings, o = n.voice_id || "";
      r("cartesia-voice-id").value = o;
      const s = u("cartesia-voice-select");
      s && o && Array.from(s.options).find((v) => v.value === o) && (s.value = o), r("cartesia-model-id").value = n.model_id || "sonic-2024-12-12", u("cartesia-language").value = n.language || "en";
      const c = n.speed || 1, i = Math.max(0.6, Math.min(1.5, c));
      r("cartesia-speed").value = String(Math.round(i * 100)), l("cartesia-speed-value").textContent = i.toFixed(1), c !== i && console.warn(`Cartesia speed ${c} was clamped to ${i} (valid: 0.6-1.5)`), te(o);
    });
  else if (a === "kokoro" && e.tts_settings)
    Te().then(() => {
      const n = e.tts_settings, o = n.voice || "af_heart", s = u("kokoro-voice-select");
      s && o && (s.value = o);
      const c = n.speed || 1;
      r("kokoro-speed").value = String(Math.round(c * 100)), l("kokoro-speed-value").textContent = c.toFixed(1);
    });
  else {
    const n = e.tts_settings || {};
    r("character-voice-id").value = n.voice_id || t.elevenlabs_voice_id;
    const o = n.model_id || t.elevenlabs_model_id || "eleven_multilingual_v2";
    u("character-tts-model").value = o, ce(o), $e(n.voice_id || t.elevenlabs_voice_id);
    const s = n.stability ?? t.voice_stability;
    r("character-stability").value = String(Math.round(s * 100)), l("character-stability-value").textContent = s.toFixed(2);
    const c = n.similarity_boost ?? t.voice_similarity_boost;
    r("character-similarity").value = String(Math.round(c * 100)), l("character-similarity-value").textContent = c.toFixed(2);
    const i = n.style ?? t.voice_style;
    r("character-voice-style").value = String(Math.round(i * 100)), l("character-style-value").textContent = i.toFixed(2);
    const d = n.speed ?? t.voice_speed;
    r("character-voice-speed").value = String(Math.round(d * 100)), l("character-speed-value").textContent = d.toFixed(1);
  }
  r("character-volume").value = String(Math.round(t.default_volume * 100)), l("character-volume-value").textContent = String(Math.round(t.default_volume * 100)), r("character-muted").checked = t.mute_state, u("character-text-style").value = t.default_text_style, r("character-font-family").value = e.text_font_family || "Arial", r("character-font-size").value = String(e.text_font_size || 48), r("character-text-duration").value = String(t.text_duration), r("character-text-color").value = e.text_color || "#ffffff", r("character-stroke-color").value = e.text_stroke_color || "#000000", r("character-stroke-width").value = String(e.text_stroke_width || 0), l("character-stroke-width-value").textContent = String(e.text_stroke_width || 0), r("character-position-x").value = String(Math.round((e.text_position_x || 0.5) * 100)), l("character-pos-x-value").textContent = String(Math.round((e.text_position_x || 0.5) * 100)), r("character-position-y").value = String(Math.round((e.text_position_y || 0.5) * 100)), l("character-pos-y-value").textContent = String(Math.round((e.text_position_y || 0.5) * 100)), x("character-prompt").value = e.system_prompt || "", r("character-model").value = e.openrouter_model || "", Se(e.openrouter_model || "").then(() => {
    u("character-provider").value = t.provider || "";
  }), r("character-temperature").value = String(Math.round(t.temperature * 100)), l("character-temp-value").textContent = t.temperature.toFixed(1), r("character-max-tokens").value = String(t.max_tokens), r("character-memory-enabled").checked = t.memory_enabled || !1, r("character-persist-memory").checked = e.persist_memory || !1, r("character-twitch-chat-enabled").checked = t.twitch_chat_enabled || !1, r("character-twitch-chat-seconds").value = String(t.twitch_chat_window_seconds || 60), r("character-twitch-chat-max").value = String(t.twitch_chat_max_messages || 20), A.classList.add("active");
}
function Q() {
  A.classList.remove("active"), S = null, de();
}
async function ft(e) {
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
    description: x("character-description").value || null,
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
    system_prompt: x("character-prompt").value || null,
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
      const o = await nt(S.name, n, !1);
      if (o && o.status === 409) {
        const s = await h(`/api/characters/${encodeURIComponent(S.name)}`, "GET", null, !1);
        s && !("error" in s) ? (Le(s), m("Someone else modified this character. Please review the updated values and try again.", "warning")) : (Q(), m("Character was modified. Please try again.", "warning"));
        return;
      }
    } else
      await tt(n);
    Q();
  } catch (o) {
    console.error("Error saving character:", o), alert("Error saving character. Check console for details.");
  }
}
const G = l("speak-modal");
function vt(e) {
  const t = _.find((a) => a.name === e);
  t && (M = t, l("speak-modal-title").textContent = `Speak as ${t.name}`, x("speak-text").value = "", r("speak-show-text").checked = !0, l("speak-status").style.display = "none", D("speak-send-btn").disabled = !1, G.classList.add("active"));
}
function Pe() {
  G.classList.remove("active"), M = null;
}
async function yt() {
  if (!M) return;
  const e = x("speak-text").value.trim(), t = r("speak-show-text").checked;
  if (!e) {
    alert("Please enter text to speak");
    return;
  }
  const a = l("speak-status"), n = l("speak-status-text"), o = D("speak-send-btn"), s = D("speak-stop-btn");
  a.style.display = "block", n.textContent = "Speaking...", o.disabled = !0, s.style.display = "inline-block", I = M.name, b = "speak", P = !1;
  try {
    const c = await lt(M.name, e, t);
    c.error || c.detail ? (n.textContent = `Error: ${c.error || c.detail}`, s.style.display = "none", I = null, b = null) : (n.textContent = "Playing audio...", x("speak-text").value = "", Z());
  } catch (c) {
    console.error("Speak error:", c), n.textContent = `Error: ${c.message || "Unknown error"}`, s.style.display = "none", I = null, b = null;
  } finally {
    o.disabled = !1;
  }
}
async function gt(e) {
  const t = e === "speak" ? M == null ? void 0 : M.name : f == null ? void 0 : f.name;
  if (!t) return;
  const a = document.getElementById(`${e}-status-text`), n = document.getElementById(`${e}-stop-btn`);
  a && (a.textContent = "Stopping..."), n && (n.disabled = !0);
  try {
    const o = await h(`/api/characters/${t}/stop`, "POST");
    a && (o.was_active ? a.textContent = "Stopped" : a.textContent = "Nothing to stop"), e === "chat" && o.was_active && setTimeout(async () => {
      try {
        const s = await le(t);
        l("chat-memory-count").textContent = `Memory: ${s.message_count} messages`, X(s.messages, t);
      } catch (s) {
        console.error("Error refreshing memory after stop:", s);
      }
    }, 500);
  } catch (o) {
    console.error("Stop error:", o), a && (a.textContent = `Stop failed: ${o.message}`);
  } finally {
    n && (n.disabled = !1, n.style.display = "none"), I = null, b = null, P = !1;
    const o = document.getElementById(`${e}-send-btn`);
    o && (o.disabled = !1);
  }
}
const $ = document.getElementById("chat-modal"), be = 20, _e = 5;
function ue() {
  T = [];
  const e = document.getElementById("chat-image-previews");
  if (e)
    for (; e.firstChild; )
      e.removeChild(e.firstChild);
}
function Ae(e, t) {
  if (T.length >= _e) {
    m(`Maximum ${_e} images allowed`, "warning");
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
async function De(e) {
  if (!e.type.startsWith("image/")) {
    m("Only image files are supported", "error");
    return;
  }
  if (e.size > be * 1024 * 1024) {
    m(`Image too large (max ${be}MB)`, "error");
    return;
  }
  return new Promise((t) => {
    const a = new FileReader();
    a.onload = (n) => {
      var i;
      const s = ((i = n.target) == null ? void 0 : i.result).split(",")[1], c = e.type || "image/png";
      Ae(s, c), t();
    }, a.readAsDataURL(e);
  });
}
function wt() {
  r("chat-image-input").click();
}
async function bt(e) {
  const t = e.target, a = t.files;
  if (a)
    for (const n of a)
      await De(n);
  t.value = "";
}
async function _t() {
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
    Ae(s, "image/png"), m("Screen captured!", "success");
  } catch (e) {
    e instanceof Error && e.name === "NotAllowedError" ? m("Screen capture permission denied", "warning") : (console.error("Screen capture error:", e), m("Screen capture failed", "error"));
  }
}
function xe(e) {
  var a;
  const t = (a = e.clipboardData) == null ? void 0 : a.items;
  if (t) {
    for (const n of t)
      if (n.type.startsWith("image/")) {
        e.preventDefault();
        const o = n.getAsFile();
        o && De(o);
      }
  }
}
async function xt(e) {
  const t = _.find((n) => n.name === e);
  if (!t) return;
  if (!t.system_prompt) {
    alert('This character has no AI system prompt configured. Use "Speak" for direct TTS.');
    return;
  }
  f = t, l("chat-modal-title").textContent = `Chat with ${t.name}`, x("chat-message").value = "", r("chat-show-text").checked = !0, r("chat-include-twitch").checked = !0, r("chat-twitch-seconds").value = "", l("chat-status").style.display = "none", l("chat-twitch-details").style.display = "none", D("chat-send-btn").disabled = !1, ue();
  const a = x("chat-message");
  a.removeEventListener("paste", xe), a.addEventListener("paste", xe);
  try {
    const n = await le(e);
    l("chat-memory-count").textContent = `Memory: ${n.message_count} messages${t.memory_enabled ? "" : " (disabled)"}`, X(n.messages, e);
  } catch {
    l("chat-memory-count").textContent = "Memory: 0 messages", X([], e);
  }
  $ == null || $.classList.add("active");
}
function Ue() {
  $ == null || $.classList.remove("active"), f = null, ue();
}
async function Ct() {
  if (!f) return;
  const e = x("chat-message").value.trim(), t = r("chat-show-text").checked, a = r("chat-include-twitch").checked;
  let n = r("chat-twitch-seconds").value;
  if (a || (n = "0"), !e) {
    alert("Please enter a message");
    return;
  }
  const o = l("chat-status"), s = l("chat-status-text"), c = D("chat-send-btn"), i = D("chat-stop-btn");
  o.style.display = "block", s.textContent = "Generating...", c.disabled = !0, i.style.display = "inline-block", I = f.name, b = "chat", P = !1;
  try {
    const d = T.length > 0, v = d ? `[${T.length} image(s)] ${e}` : e;
    we("user", v, f.name), x("chat-message").value = "";
    const w = d ? [...T] : null;
    ue();
    const p = await dt(f.name, e, t, n, w);
    if (p.error || p.detail)
      s.textContent = `Error: ${p.error || p.detail}`, i.style.display = "none", I = null, b = null;
    else {
      if (p.twitch_chat_context) {
        const U = p.twitch_chat_context.split(`
`), Ne = U.slice(-4).map((ne) => ne.length > 60 ? ne.substring(0, 57) + "..." : ne).join(" | ");
        ht(`📺 Twitch chat (${U.length}): ${Ne}`);
      }
      we("assistant", p.response_text || "", f.name);
      let y = "Playing audio...";
      const V = document.getElementById("chat-twitch-details"), he = document.getElementById("chat-twitch-summary"), me = document.getElementById("chat-twitch-context-text");
      if (p.twitch_chat_context) {
        const U = p.twitch_chat_context.split(`
`).length;
        y += ` (${U} chat msgs)`, he && (he.textContent = `Twitch Chat Context (${U} messages)`), me && (me.textContent = p.twitch_chat_context), V && (V.style.display = "block");
      } else
        V && (V.style.display = "none");
      s.textContent = y, Z();
      const Fe = await le(f.name), He = f;
      l("chat-memory-count").textContent = `Memory: ${Fe.message_count} messages${He.memory_enabled ? "" : " (not saving)"}`;
    }
  } catch (d) {
    console.error("Chat error:", d), s.textContent = `Error: ${d instanceof Error ? d.message : "Unknown error"}`, i.style.display = "none", I = null, b = null;
  } finally {
    c.disabled = !1;
  }
}
async function kt() {
  if (f && confirm(`Clear conversation memory for ${f.name}?`))
    try {
      await ut(f.name);
      const e = document.getElementById("chat-memory-count"), t = document.getElementById("chat-status"), a = document.getElementById("chat-status-text"), n = document.getElementById("chat-twitch-details");
      e && (e.textContent = "Memory: 0 messages"), t && (t.style.display = "block"), a && (a.textContent = "Memory cleared!"), X([], f.name), n && (n.style.display = "none");
    } catch (e) {
      console.error("Error clearing memory:", e), alert("Error clearing memory");
    }
}
function Et(e) {
  if (!e || e.length === 0) {
    ge.innerHTML = '<div class="history-item"><span class="history-content">No history yet</span></div>';
    return;
  }
  ge.innerHTML = e.map((t) => {
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
function se() {
  if (O) {
    if (_.length === 0) {
      O.innerHTML = `
                <div class="no-channels">
                    <p>No characters configured yet.</p>
                    <p>Click "Create Character" to add one.</p>
                </div>
            `;
      return;
    }
    O.innerHTML = _.map((e) => It(e)).join("");
  }
}
function It(e) {
  var p, y;
  let t = "", a = "offline";
  e.connected ? e.streaming ? (t = "streaming", a = "streaming") : e.playing ? (t = "playing", a = "playing") : a = "ready" : (t = "", a = "offline");
  const n = e.connected ? "" : "disconnected", o = e.system_prompt ? '<span class="voice-indicator">AI</span>' : "", s = k(e.description || (e.system_prompt ? e.system_prompt.substring(0, 80) + "..." : "No description")), c = k(e.name), i = k(e.icon), d = Ye(e.color), v = k(e.model ? e.model.split("/").pop() : "");
  let w;
  return e.tts_provider === "cartesia" ? w = k((((p = e.tts_settings) == null ? void 0 : p.model_id) || "sonic").replace("sonic-", "")) : e.tts_provider === "kokoro" ? w = k(((y = e.tts_settings) == null ? void 0 : y.voice) || "af_heart") : w = k((e.elevenlabs_model_id || "multilingual_v2").replace("eleven_", "").replace("_", " ")), `
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
window.openCreateCharacterModal = pt;
window.closeCharacterModal = Q;
window.editCharacter = async function(e) {
  const t = await h(`/api/characters/${encodeURIComponent(e)}`);
  t && !("error" in t) ? Le(t) : m("Failed to load character", "error");
};
window.deleteCharacter = at;
window.openSpeakModal = vt;
window.closeSpeakModal = Pe;
window.sendSpeak = yt;
window.stopGeneration = gt;
window.openChatModal = xt;
window.closeChatModal = Ue;
window.sendChat = Ct;
window.clearChatMemory = kt;
window.attachImage = wt;
window.handleImageSelect = bt;
window.captureScreen = _t;
window.previewCharacterTextStyle = mt;
window.stopCharacterTextPreview = de;
window.updateProviderDropdown = Se;
window.loadVoiceModels = $e;
window.updateModelInfo = ce;
window.toggleTTSProvider = Me;
window.updateCartesiaVoiceInfo = te;
window.loadCartesiaVoices = ie;
window.selectCartesiaVoice = st;
window.onCartesiaManualIdChange = ct;
window.copyCharacterUrl = async function(e) {
  const t = _.find((n) => n.name === e);
  if (!(t != null && t.ws_token)) {
    m("Character token not found", "error");
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
        const a = _.find((n) => n.name === e);
        a && t.ws_token && (a.ws_token = t.ws_token), m("Token rotated. Copy new URL for OBS.", "success");
      } else
        m((t == null ? void 0 : t.detail) || "Failed to rotate token", "error");
    } catch (t) {
      console.error("Failed to rotate token:", t), m("Failed to rotate token", "error");
    }
};
const ae = document.getElementById("twitch-user"), Ce = document.getElementById("twitch-username");
async function Re() {
  if (!(!ae || !Ce))
    try {
      const t = await (await fetch("/api/twitch/status")).json();
      t.connected && t.channel ? (Ce.textContent = t.channel, ae.style.display = "inline-flex") : ae.style.display = "none";
    } catch (e) {
      console.error("Error checking Twitch status:", e);
    }
}
const C = document.getElementById("channel-switcher");
async function St() {
  if (C)
    try {
      const t = await (await fetch("/api/moderators/accessible-channels")).json();
      if (!t.channels || t.channels.length <= 1) {
        C.style.display = "none", E && t.channels && !t.channels.find((a) => a.tenant_id === E) && (E = null, localStorage.removeItem("effectiveChannel"));
        return;
      }
      if (C.innerHTML = "", t.channels.forEach((a) => {
        const n = document.createElement("option");
        n.value = a.tenant_id, n.textContent = a.is_own ? `${a.username} (You)` : a.username, C.appendChild(n);
      }), E)
        C.value = E;
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
re && re.addEventListener("submit", ft);
const ke = document.getElementById("kokoro-preview-btn");
ke && ke.addEventListener("click", it);
A && A.addEventListener("click", (e) => {
  e.target === A && Q();
});
G && G.addEventListener("click", (e) => {
  e.target === G && Pe();
});
$ && $.addEventListener("click", (e) => {
  e.target === $ && Ue();
});
O && O.addEventListener("click", (e) => {
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
Ie();
ee();
et();
Z();
Re();
ot();
St();
setInterval(Z, 1e4);
setInterval(Re, 15e3);
