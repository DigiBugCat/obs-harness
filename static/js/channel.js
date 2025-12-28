import { TextAnimator as L } from "./text-animator.js";
console.log("[channel.js] VERSION 13 LOADED - token-based WebSocket auth");
const O = window.location.pathname.split("/"), n = O[O.length - 1] || "default", j = new URLSearchParams(window.location.search), M = j.get("token");
let c = null, S = null, x = 0;
const q = 1e3, G = 3e4, D = 10, F = 6e4, J = 3e4;
let P = Date.now(), A = null, _ = null, i = null, r = null, W = !1, I = 24e3, k = 1, h = 0, C = 0, N = !1, y = [], T = null, b = [], g = !1, f = [], E = 0, m = 0;
const l = document.getElementById("canvas"), s = l.getContext("2d");
let o = null, H = !1;
function U() {
  l.width = window.innerWidth, l.height = window.innerHeight, o && o.resize(l.width, l.height);
}
window.addEventListener("resize", U);
U();
typeof L < "u" && (o = new L(s, l.width, l.height));
function V() {
  if (!M) {
    console.error(`[${n}] No token provided - WebSocket connection requires ?token= parameter`), B("Missing Token", "Get URL from dashboard");
    return;
  }
  const t = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/${encodeURIComponent(n)}?token=${encodeURIComponent(M)}`;
  c = new WebSocket(t), c.binaryType = "arraybuffer", c.onopen = () => {
    console.log(`[${n}] Connected to server`), x = 0, P = Date.now(), Z(), S && (clearTimeout(S), S = null);
  }, c.onclose = (a) => {
    if (a.code === 4004) {
      console.error(`[${n}] Invalid channel or token: ${a.reason}`), B("Invalid channel or token", "Copy fresh URL from dashboard");
      return;
    }
    console.log(`[${n}] Disconnected from server`), Q(), K();
  }, c.onerror = (a) => {
    console.error(`[${n}] WebSocket error:`, a);
  }, c.onmessage = (a) => {
    a.data instanceof ArrayBuffer ? le(a.data) : te(a.data);
  };
}
function K() {
  if (!S) {
    if (x >= D) {
      console.log(`[${n}] Max reconnect attempts (${D}) reached, reloading page...`), location.reload();
      return;
    }
    const e = Math.min(
      q * Math.pow(2, x),
      G
    );
    x++, console.log(`[${n}] Reconnecting in ${e}ms (attempt ${x}/${D})...`), S = setTimeout(() => {
      S = null, V();
    }, e);
  }
}
function p(e) {
  c && c.readyState === WebSocket.OPEN && c.send(JSON.stringify(e));
}
function Q() {
  A || (A = setInterval(async () => {
    if (!(c && c.readyState === WebSocket.OPEN))
      try {
        (await fetch("/health", { signal: AbortSignal.timeout(5e3) })).ok && x >= D / 2 && (console.log(`[${n}] Server healthy but WebSocket failing, reloading page...`), location.reload());
      } catch {
      }
  }, J));
}
function Z() {
  A && (clearInterval(A), A = null);
}
function ee(e) {
  const t = e.build_id;
  if (_ === null)
    _ = t, console.log(`[${n}] Server build ID: ${_}`);
  else if (_ !== t) {
    console.log(`[${n}] Server version changed (${_} -> ${t}), refreshing page...`), location.reload();
    return;
  } else
    console.log(`[${n}] Reconnected to same server version`);
}
function te(e) {
  try {
    const t = JSON.parse(e);
    switch (console.log(`[${n}] Received:`, t), t.action) {
      case "hello":
        ee(t);
        break;
      case "ping":
        p({ event: "pong", ts: t.ts }), P = Date.now();
        break;
      case "play":
        ne(t);
        break;
      case "stop":
        oe();
        break;
      case "volume":
        re(t.level);
        break;
      case "stream_start":
        ae(t);
        break;
      case "stream_end":
        se();
        break;
      case "stop_stream":
        ce();
        break;
      case "text":
        de(t);
        break;
      case "clear_text":
        fe();
        break;
      case "text_stream_start":
        ue(t);
        break;
      case "text_chunk":
        he(t);
        break;
      case "text_stream_end":
        pe();
        break;
      case "word_timing":
        me(t);
        break;
      default:
        console.warn(`[${n}] Unknown action:`, t.action);
    }
  } catch (t) {
    console.error(`[${n}] Error parsing message:`, t);
  }
}
function ne(e) {
  i && (i.pause(), i = null), i = new Audio(e.file), i.volume = e.volume ?? 1, i.loop = e.loop ?? !1, i.onended = () => {
    i.loop || p({ event: "ended", file: e.file });
  }, i.onerror = (t) => {
    p({ event: "error", message: `Failed to load: ${e.file}` });
  }, i.play().catch((t) => {
    p({ event: "error", message: `Playback failed: ${t.message}` });
  });
}
function oe() {
  i && (i.pause(), i.currentTime = 0, i = null);
}
function re(e) {
  i && (i.volume = Math.max(0, Math.min(1, e)));
}
function ae(e) {
  r || (r = new (window.AudioContext || window.webkitAudioContext)()), r.state === "suspended" && r.resume(), I = e.sample_rate || 24e3, k = e.channels || 1, W = !0, h = r.currentTime, N = !1, y = [], console.log(`[${n}] Stream started: ${I}Hz, ${k}ch`);
}
function le(e) {
  if (!(!W || !r))
    try {
      if (!e || !(e instanceof ArrayBuffer) || e.byteLength === 0) {
        console.warn(`[${n}] Invalid stream data received`);
        return;
      }
      const t = new Int16Array(e), a = new Float32Array(t.length);
      for (let d = 0; d < t.length; d++)
        a[d] = t[d] / 32768;
      const u = a.length / k;
      if (u <= 0) {
        console.warn(`[${n}] Empty audio chunk, skipping`);
        return;
      }
      const v = r.createBuffer(
        k,
        u,
        I
      );
      for (let d = 0; d < k; d++) {
        const Y = v.getChannelData(d);
        for (let R = 0; R < u; R++)
          Y[R] = a[R * k + d];
      }
      const w = r.createBufferSource();
      w.buffer = v, w.connect(r.destination), h < r.currentTime && (h = r.currentTime), w.start(h), y.push(w), w.onended = () => {
        const d = y.indexOf(w);
        d !== -1 && y.splice(d, 1);
      }, N || (N = !0, E = h, ie()), h += v.duration;
    } catch (t) {
      console.error(`[${n}] Error processing audio stream data:`, t);
    }
}
function ie() {
  if (!(!o || !T)) {
    if (o.startStream(T), console.log(`[${n}] Text stream activated (synced to audio, wordTiming=${g})`), !g)
      for (const e of b)
        o.appendText(e);
    b = [], T = null;
  }
}
function se() {
  if (W = !1, T = null, b = [], r && h > r.currentTime) {
    C = h;
    const e = (h - r.currentTime) * 1e3;
    console.log(`[${n}] Stream ended, audio finishes in ${e.toFixed(0)}ms`), setTimeout(() => {
      p({ event: "stream_ended" }), console.log(`[${n}] Audio playback complete, sent stream_ended`);
    }, e + 100);
  } else
    C = 0, console.log(`[${n}] Stream ended, no pending audio`), p({ event: "stream_ended" });
}
function ce() {
  console.log(`[${n}] Stop stream: forcefully stopping audio (${y.length} sources tracked)`);
  let e = 0, t = "", a = 0;
  if (r && E > 0) {
    e = r.currentTime - E;
    for (const u of f)
      if (u.start <= e)
        t && (t += " "), t += u.word, a++;
      else
        break;
  }
  console.log(`[${n}] Stop at ${e.toFixed(2)}s - ${a}/${f.length} words played: "${t.substring(0, 50)}..."`), r && (r.close().catch(() => {
  }), r = null), y = [], W = !1, h = 0, C = 0, N = !1, E = 0, g = !1, f = [], m = 0, $ = !1, T = null, b = [], o && o.clear(), p({
    event: "stream_stopped",
    playback_time: e,
    spoken_text: t,
    word_count: a
  });
}
function de(e) {
  if (!o) {
    console.warn(`[${n}] TextAnimator not available`);
    return;
  }
  o.show({
    text: e.text,
    style: e.style || "typewriter",
    duration: e.duration || 3e3,
    x: e.position_x ?? 0.5,
    y: e.position_y ?? 0.5,
    fontFamily: e.font_family || "Arial",
    fontSize: e.font_size || 48,
    color: e.color || "#ffffff",
    strokeColor: e.stroke_color,
    strokeWidth: e.stroke_width || 0,
    onComplete: () => {
      p({ event: "text_complete" });
    }
  });
}
function fe() {
  o && o.clear();
}
function ue(e) {
  if (!o) {
    console.warn(`[${n}] TextAnimator not available`);
    return;
  }
  const t = {
    fontFamily: e.font_family || "Arial",
    fontSize: e.font_size || 48,
    color: e.color || "#ffffff",
    strokeColor: e.stroke_color,
    strokeWidth: e.stroke_width || 0,
    positionX: e.position_x ?? 0.5,
    positionY: e.position_y ?? 0.5,
    instantReveal: e.instant_reveal || !1
  };
  g = !1, f = [], m = 0, $ = !1, T = t, b = [], console.log(`[${n}] Text stream pending (waiting for audio)`);
}
function he(e) {
  o && (g || (T ? b.push(e.text) : o.appendText(e.text)));
}
function me(e) {
  if (!(!e.words || e.words.length === 0)) {
    g = !0;
    for (const t of e.words)
      f.push({
        word: t.word,
        start: t.start,
        end: t.end
      });
    console.log(`[${n}] Word timing received: ${e.words.map((t) => `"${t.word}"@${t.start.toFixed(2)}s`).join(", ")} (total: ${f.length})`);
  }
}
function pe() {
  if (!o) return;
  const e = 2e3;
  let t = e;
  r && C > r.currentTime && (t = (C - r.currentTime) * 1e3 + e), setTimeout(() => {
    g = !1, f = [], m = 0, $ = !1;
  }, t), o.endStream(t), console.log(`[${n}] Text stream ended, fade in ${t.toFixed(0)}ms, unrevealed words: ${f.length - m}`), p({ event: "text_stream_complete" });
}
function B(e, t) {
  H = !0, o && o.clear(), s.clearRect(0, 0, l.width, l.height), s.fillStyle = "rgba(0, 0, 0, 0.7)", s.fillRect(0, 0, l.width, l.height), s.font = "48px sans-serif", s.textAlign = "center", s.fillStyle = "#ff4444", s.fillText("⚠", l.width / 2, l.height / 2 - 40), s.font = "bold 24px sans-serif", s.fillStyle = "#ffffff", s.fillText(e, l.width / 2, l.height / 2 + 10), s.font = "16px sans-serif", s.fillStyle = "#aaaaaa", s.fillText(t, l.width / 2, l.height / 2 + 40);
}
const z = 0.3;
let $ = !1;
function we() {
  if (!g || !r || f.length === 0 || !o)
    return;
  const e = r.currentTime - E;
  for (; m < f.length; ) {
    const t = f[m];
    if (e >= t.start) {
      let a = "", u = 0;
      if (m > 0) {
        const w = f[m - 1];
        u = t.start - w.end, u >= z && !$ ? (a = `
`, $ = !0) : (a = " ", $ = !1);
      } else
        $ = !1;
      const v = a + t.word;
      u >= z ? console.log(`[REVEAL] "${t.word}" at ${e.toFixed(2)}s (pause: ${(u * 1e3).toFixed(0)}ms → newline)`) : console.log(`[REVEAL] "${t.word}" at ${e.toFixed(2)}s`), o.appendText(v), m++;
    } else
      break;
  }
}
function X() {
  H || (c && c.readyState === WebSocket.OPEN && Date.now() - P > F && (console.log(`[${n}] No ping received in ${F}ms, connection stale - reconnecting...`), P = Date.now(), c.close()), s.clearRect(0, 0, l.width, l.height), we(), o && (o.isStreaming || o.streamText ? (o.updateStream(), o.drawStream()) : (o.update(), o.draw())), requestAnimationFrame(X));
}
X();
V();
console.log(`[${n}] Browser source initialized`);
