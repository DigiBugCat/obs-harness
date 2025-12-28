var O = Object.defineProperty;
var R = (T, t, e) => t in T ? O(T, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : T[t] = e;
var h = (T, t, e) => R(T, typeof t != "symbol" ? t + "" : t, e);
class z {
  constructor(t, e, i) {
    h(this, "ctx");
    h(this, "width");
    h(this, "height");
    h(this, "queue");
    h(this, "current");
    h(this, "startTime");
    // Streaming text state
    h(this, "isStreaming");
    h(this, "streamText");
    h(this, "revealIndex");
    h(this, "streamSettings");
    h(this, "lastRevealTime");
    h(this, "revealRate");
    h(this, "streamFadeStart");
    h(this, "streamFadeDuration");
    h(this, "streamOpacity");
    // Max lines to display at once
    h(this, "maxDisplayLines");
    h(this, "hardMaxLines");
    // Fade-out state for clearing old sentences
    h(this, "clearFadeStart");
    h(this, "clearFadeDuration");
    h(this, "pendingSentencesToRemove");
    // Committed sentences (for streaming mode)
    h(this, "committedSentences");
    h(this, "lastCommittedIndex");
    this.ctx = t, this.width = e, this.height = i, this.queue = [], this.current = null, this.startTime = 0, this.isStreaming = !1, this.streamText = "", this.revealIndex = 0, this.streamSettings = null, this.lastRevealTime = 0, this.revealRate = 40, this.streamFadeStart = null, this.streamFadeDuration = 1e3, this.streamOpacity = 1, this.maxDisplayLines = 4, this.hardMaxLines = 7, this.clearFadeStart = null, this.clearFadeDuration = 400, this.pendingSentencesToRemove = null, this.committedSentences = [], this.lastCommittedIndex = 0;
  }
  resize(t, e) {
    this.width = t, this.height = e;
  }
  show(t) {
    const e = {
      text: t.text || "",
      style: t.style || "typewriter",
      duration: t.duration || 3e3,
      x: t.x ?? 0.5,
      y: t.y ?? 0.5,
      fontFamily: t.fontFamily || "Arial",
      fontSize: t.fontSize || 48,
      color: t.color || "#ffffff",
      strokeColor: t.strokeColor || null,
      strokeWidth: t.strokeWidth || 0,
      onComplete: t.onComplete || null,
      // Animation state
      progress: 0,
      chars: t.text.split(""),
      charStates: [],
      // Text wrapping - will be calculated in next()
      lines: [],
      lineHeight: (t.fontSize || 48) * 1.3
    };
    for (let i = 0; i < e.chars.length; i++)
      e.charStates.push({
        visible: !1,
        offset: 0,
        opacity: 0,
        scale: 1
      });
    this.queue.push(e), this.current || this.next();
  }
  clear() {
    this.queue = [], this.current = null;
  }
  next() {
    this.queue.length > 0 ? (this.current = this.queue.shift(), this.startTime = performance.now(), this.current.lines = this.wrapText(this.current)) : this.current = null;
  }
  wrapText(t) {
    this.ctx.font = `${t.fontSize}px ${t.fontFamily}`;
    const e = this.width * 0.9, i = t.text.split(" "), r = [];
    let s = "", a = 0;
    for (let n = 0; n < i.length; n++) {
      const o = i[n], l = s ? s + " " + o : o;
      if (this.ctx.measureText(l).width > e && s) {
        const x = s.split("");
        r.push({
          text: s,
          startIndex: a,
          endIndex: a + x.length
        }), a += x.length + 1, s = o;
      } else
        s = l;
    }
    return s && r.push({
      text: s,
      startIndex: a,
      endIndex: a + s.length
    }), r;
  }
  update() {
    if (!this.current) return;
    const t = performance.now() - this.startTime, e = this.current;
    switch (e.progress = Math.min(t / e.duration, 1), e.style) {
      case "typewriter":
        this.updateTypewriter(e, t);
        break;
      case "fade":
        this.updateFade(e, t);
        break;
      case "slide":
        this.updateSlide(e, t);
        break;
      case "bounce":
        this.updateBounce(e, t);
        break;
      case "wave":
        this.updateWave(e, t);
        break;
      default:
        this.updateTypewriter(e, t);
    }
    e.progress >= 1 && (e.onComplete && e.onComplete(), this.next());
  }
  // =========================================================================
  // Animation Updates
  // =========================================================================
  updateTypewriter(t, e) {
    const i = t.duration * 0.6, r = Math.min(e / i, 1), s = Math.floor(r * t.chars.length);
    for (let n = 0; n < t.chars.length; n++)
      t.charStates[n].visible = n < s, t.charStates[n].opacity = t.charStates[n].visible ? 1 : 0;
    const a = t.duration * 0.8;
    if (e > a) {
      const o = 1 - (e - a) / (t.duration * 0.2);
      for (let l = 0; l < t.chars.length; l++)
        t.charStates[l].visible && (t.charStates[l].opacity = o);
    }
  }
  updateFade(t, e) {
    const i = t.duration * 0.2, r = t.duration * 0.8;
    let s = 1;
    e < i ? s = e / i : e > r && (s = 1 - (e - r) / (t.duration * 0.2));
    for (let a = 0; a < t.chars.length; a++)
      t.charStates[a].visible = !0, t.charStates[a].opacity = s;
  }
  updateSlide(t, e) {
    const i = t.duration * 0.2, r = t.duration * 0.8;
    let s = 0, a = 1;
    if (e < i) {
      const n = e / i;
      s = (1 - this.easeOutCubic(n)) * -this.width * 0.3, a = n;
    } else if (e > r) {
      const n = (e - r) / (t.duration * 0.2);
      s = this.easeInCubic(n) * this.width * 0.3, a = 1 - n;
    }
    for (let n = 0; n < t.chars.length; n++)
      t.charStates[n].visible = !0, t.charStates[n].offset = s, t.charStates[n].opacity = a;
  }
  updateBounce(t, e) {
    const i = t.duration * 0.4, r = t.duration * 0.8;
    for (let s = 0; s < t.chars.length; s++) {
      const a = s / t.chars.length * i * 0.5, n = e - a;
      if (n < 0) {
        t.charStates[s].visible = !1, t.charStates[s].opacity = 0, t.charStates[s].offset = -50;
        continue;
      }
      t.charStates[s].visible = !0;
      const o = i * 0.5;
      if (n < o) {
        const l = n / o, S = this.easeOutBounce(l);
        t.charStates[s].offset = (1 - S) * -50, t.charStates[s].opacity = Math.min(l * 2, 1);
      } else
        t.charStates[s].offset = 0, t.charStates[s].opacity = 1;
    }
    if (e > r) {
      const s = (e - r) / (t.duration * 0.2);
      for (let a = 0; a < t.chars.length; a++)
        t.charStates[a].opacity = 1 - s;
    }
  }
  updateWave(t, e) {
    const i = t.duration * 0.1, r = t.duration * 0.8;
    let s = 1;
    e < i ? s = e / i : e > r && (s = 1 - (e - r) / (t.duration * 0.2));
    const a = 5e-3, n = 15;
    for (let o = 0; o < t.chars.length; o++)
      t.charStates[o].visible = !0, t.charStates[o].opacity = s, t.charStates[o].offset = Math.sin(e * a + o * 0.5) * n;
  }
  // =========================================================================
  // Drawing
  // =========================================================================
  draw() {
    if (!this.current) return;
    const t = this.current, e = this.ctx, i = t.x * this.width, r = t.y * this.height;
    e.font = `${t.fontSize}px ${t.fontFamily}`, e.textAlign = "center", e.textBaseline = "middle";
    const s = t.lines.length * t.lineHeight, a = r - s / 2 + t.lineHeight / 2;
    for (let n = 0; n < t.lines.length; n++) {
      const o = t.lines[n], l = a + n * t.lineHeight, S = e.measureText(o.text).width;
      let x = i - S / 2;
      for (let p = o.startIndex; p < o.endIndex && p < t.chars.length; p++) {
        p - o.startIndex;
        const u = t.charStates[p];
        if (!u.visible || u.opacity <= 0) {
          x += e.measureText(t.chars[p]).width;
          continue;
        }
        const m = t.chars[p], w = e.measureText(m).width, F = x + w / 2 + (u.offset || 0), v = l + (t.style === "wave" || t.style === "bounce" ? u.offset : 0);
        e.save(), e.globalAlpha = u.opacity, t.strokeColor && t.strokeWidth > 0 && (e.strokeStyle = t.strokeColor, e.lineWidth = t.strokeWidth, e.strokeText(m, F, v)), e.fillStyle = t.color, e.fillText(m, F, v), e.restore(), x += w;
      }
    }
  }
  // =========================================================================
  // Easing Functions
  // =========================================================================
  easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }
  easeInCubic(t) {
    return t * t * t;
  }
  easeOutBounce(t) {
    return t < 1 / 2.75 ? 7.5625 * t * t : t < 2 / 2.75 ? 7.5625 * (t -= 1.5 / 2.75) * t + 0.75 : t < 2.5 / 2.75 ? 7.5625 * (t -= 2.25 / 2.75) * t + 0.9375 : 7.5625 * (t -= 2.625 / 2.75) * t + 0.984375;
  }
  // =========================================================================
  // Streaming Text Support
  // =========================================================================
  /**
   * Start streaming text display mode.
   */
  startStream(t) {
    this.isStreaming = !0, this.streamText = "", this.revealIndex = 0, this.clearFadeStart = null, this.pendingSentencesToRemove = null, this.committedSentences = [], this.lastCommittedIndex = 0, this.streamSettings = {
      fontFamily: t.fontFamily || "Arial",
      fontSize: t.fontSize || 48,
      color: t.color || "#ffffff",
      strokeColor: t.strokeColor || null,
      strokeWidth: t.strokeWidth || 0,
      positionX: t.positionX ?? 0.5,
      positionY: t.positionY ?? 0.5,
      instantReveal: t.instantReveal || !1
    }, this.lastRevealTime = performance.now(), this.streamFadeStart = null, this.streamOpacity = 1, this.current = null, this.queue = [];
  }
  /**
   * Append text to the streaming buffer.
   */
  appendText(t) {
    this.isStreaming && (this.streamText += t);
  }
  /**
   * End streaming mode and schedule fade-out.
   */
  endStream(t = 500) {
    setTimeout(() => {
      this.isStreaming = !1, this.streamFadeStart = performance.now();
    }, t);
  }
  /**
   * Clear streaming text immediately.
   */
  clearStream() {
    this.isStreaming = !1, this.streamText = "", this.revealIndex = 0, this.clearFadeStart = null, this.pendingSentencesToRemove = null, this.committedSentences = [], this.lastCommittedIndex = 0, this.streamFadeStart = null, this.streamSettings = null;
  }
  /**
   * Truncate streaming text to only show what was actually spoken.
   * Used when audio is stopped mid-stream.
   */
  truncateToSpoken(t, e = 1500) {
    this.isStreaming && (this.committedSentences = [], this.lastCommittedIndex = 0, this.clearFadeStart = null, this.pendingSentencesToRemove = null, this.streamText = t, this.revealIndex = t.length, console.log(`[TextAnimator] Truncated to spoken: "${t.substring(0, 50)}..." (${t.length} chars)`), setTimeout(() => {
      this.isStreaming && this.streamText === t && (this.streamFadeStart = performance.now());
    }, e), setTimeout(() => {
      this.streamText === t && this.clearStream();
    }, e + this.streamFadeDuration + 100));
  }
  /**
   * Update streaming text state (progressive reveal).
   */
  updateStream() {
    if (this.streamText) {
      if (this.streamFadeStart) {
        const t = performance.now() - this.streamFadeStart;
        if (this.streamOpacity = 1 - t / this.streamFadeDuration, this.streamOpacity <= 0) {
          this.streamText = "", this.streamFadeStart = null, this.streamSettings = null;
          return;
        }
      }
      if (this.streamSettings && this.streamSettings.instantReveal) {
        this.revealIndex = this.streamText.length;
        return;
      }
      if (this.isStreaming || this.revealIndex < this.streamText.length) {
        const t = performance.now(), e = t - this.lastRevealTime, i = Math.floor(e / (1e3 / this.revealRate));
        i > 0 && (this.revealIndex = Math.min(
          this.revealIndex + i,
          this.streamText.length
        ), this.lastRevealTime = t);
      }
    }
  }
  /**
   * Parse text into formatted segments.
   * Supports **bold**, *italic*, ^whisper^, and newlines.
   */
  parseFormattedText(t) {
    const e = [];
    let i = t, r = !1, s = !1, a = !1;
    for (; i.length > 0; ) {
      if (i[0] === `
`) {
        e.push({ text: "", newline: !0, bold: !1, italic: !1, whisper: !1 }), i = i.substring(1);
        continue;
      }
      if (i.startsWith("**")) {
        r = !r, i = i.substring(2);
        continue;
      }
      if (i[0] === "*" && !i.startsWith("**")) {
        s = !s, i = i.substring(1);
        continue;
      }
      if (i[0] === "^") {
        a = !a, i = i.substring(1);
        continue;
      }
      let n = i.length;
      const o = [
        i.indexOf("**"),
        i.indexOf("*"),
        i.indexOf("^"),
        i.indexOf(`
`)
      ].filter((S) => S > 0);
      o.length > 0 && (n = Math.min(...o));
      const l = i.substring(0, n);
      l && e.push({
        text: l,
        bold: r,
        italic: s,
        whisper: a,
        newline: !1
      }), i = i.substring(n);
    }
    return e;
  }
  /**
   * Measure width of formatted segments.
   */
  measureFormattedText(t, e) {
    const i = this.ctx;
    let r = 0;
    for (const s of t) {
      if (s.newline) continue;
      const a = s.italic || s.whisper, n = s.whisper ? e.fontSize * 0.85 : e.fontSize, o = (s.bold ? "bold " : "") + (a ? "italic " : "");
      i.font = `${o}${n}px ${e.fontFamily}`, r += i.measureText(s.text).width;
    }
    return r;
  }
  /**
   * Wrap a paragraph into lines while preserving formatting across line breaks.
   */
  wrapFormattedParagraph(t, e, i, r = !1) {
    const s = this.parseFormattedText(t), a = [];
    let n = [], o = 0;
    for (const l of s) {
      if (l.newline) {
        n.length > 0 && (a.push({ segments: n, isQuote: r }), n = [], o = 0);
        continue;
      }
      const S = l.italic || l.whisper, x = l.whisper ? i.fontSize * 0.85 : i.fontSize, p = (l.bold ? "bold " : "") + (S ? "italic " : "");
      this.ctx.font = `${p}${x}px ${i.fontFamily}`;
      const u = l.text.split(/(\s+)/);
      for (const m of u) {
        if (m === "") continue;
        const w = this.ctx.measureText(m).width;
        o + w > e && n.length > 0 && (a.push({ segments: n, isQuote: r }), n = [], o = 0), (m.trim() || n.length > 0) && (n.push({ text: m, bold: l.bold, italic: l.italic, whisper: l.whisper, newline: !1 }), o += w);
      }
    }
    return n.length > 0 && a.push({ segments: n, isQuote: r }), a;
  }
  /**
   * Get the formatting state (bold/italic) at a given position in the text.
   * Scans from the start to count formatting marker toggles.
   */
  getFormattingStateAt(t, e) {
    let i = !1, r = !1, s = 0;
    for (; s < e && s < t.length; )
      t.substring(s, s + 2) === "**" ? (i = !i, s += 2) : (t[s] === "*" && (r = !r), s += 1);
    return { bold: i, italic: r };
  }
  /**
   * Find sentence ending in text, returns index after the ending or -1.
   */
  findSentenceEnd(t, e = 0) {
    const i = [". ", "! ", "? ", `.
`, `!
`, `?
`, '."', '!"', '?"', ".'", "!'", "?'"];
    let r = -1, s = null;
    for (const a of i) {
      const n = t.indexOf(a, e);
      n !== -1 && (r === -1 || n < r) && (r = n, s = a);
    }
    return r !== -1 && s ? r + s.length : -1;
  }
  /**
   * Draw streaming text with word wrapping and formatting.
   * Uses committed sentences to prevent text from shifting.
   */
  drawStream() {
    if (!this.streamText || !this.streamSettings) return;
    const t = this.streamSettings, e = this.ctx, i = this.width * 0.9, r = t.fontSize * 1.3;
    let s = 1;
    if (this.clearFadeStart !== null && (s = 1 - (performance.now() - this.clearFadeStart) / this.clearFadeDuration, s <= 0)) {
      const c = this.pendingSentencesToRemove || 1;
      this.committedSentences.splice(0, c), this.pendingSentencesToRemove = null, this.clearFadeStart = null, s = 1;
    }
    const a = this.streamText.substring(0, this.revealIndex);
    if (!a) return;
    const n = a.substring(this.lastCommittedIndex);
    let o = 0, l = this.findSentenceEnd(n, o);
    for (; l !== -1; ) {
      const f = n.substring(o, l);
      if (f.trim()) {
        const c = this.getFormattingStateAt(this.streamText, this.lastCommittedIndex + o);
        let d = f;
        c.bold && (d = "**" + d), c.italic && (d = "*" + d);
        const y = d.trimStart().startsWith(">"), b = y ? d.trimStart().substring(1).trimStart() : d, g = this.wrapFormattedParagraph(b, i, t, y);
        this.committedSentences.push({
          lines: g
        });
      }
      for (o = l; o < n.length && /\s/.test(n[o]); )
        o++;
      l = this.findSentenceEnd(n, o);
    }
    this.lastCommittedIndex += o;
    const S = a.substring(this.lastCommittedIndex);
    let x = [];
    if (S.trim()) {
      const f = this.getFormattingStateAt(this.streamText, this.lastCommittedIndex);
      let c = S;
      f.bold && (c = "**" + c), f.italic && (c = "*" + c);
      const d = c.trimStart().startsWith(">"), y = d ? c.trimStart().substring(1).trimStart() : c;
      x = this.wrapFormattedParagraph(y, i, t, d);
    }
    const u = [...this.committedSentences.flatMap((f) => f.lines), ...x], m = u.length;
    if (m >= this.hardMaxLines && this.clearFadeStart === null) {
      this.committedSentences = [], this.lastCommittedIndex = this.revealIndex, this.clearFadeStart = null, this.pendingSentencesToRemove = null, console.log(`[TextAnimator] Hard cap hit (${m} lines) - force clearing`);
      return;
    }
    if (m > this.maxDisplayLines && this.clearFadeStart === null && this.committedSentences.length > 0 && (this.pendingSentencesToRemove = this.committedSentences.length, this.clearFadeStart = performance.now()), u.length === 0) return;
    const w = t.positionX * this.width, v = this.height * 0.08 + r / 2;
    e.save(), e.textAlign = "left", e.textBaseline = "middle", e.globalAlpha = this.streamOpacity * s;
    for (let f = 0; f < u.length; f++) {
      const c = u[f], d = v + f * r, y = this.measureFormattedText(c.segments, t);
      let b = w - y / 2;
      c.isQuote && (e.font = `${t.fontSize}px ${t.fontFamily}`, e.fillStyle = t.quoteColor || "#888888", e.fillText("│ ", b - e.measureText("│ ").width, d));
      for (const g of c.segments) {
        if (g.newline) continue;
        const I = g.italic || g.whisper, C = g.whisper ? t.fontSize * 0.85 : t.fontSize, W = (g.bold ? "bold " : "") + (I ? "italic " : "");
        e.font = `${W}${C}px ${t.fontFamily}`;
        const k = e.measureText(g.text).width;
        t.strokeColor && t.strokeWidth > 0 && (e.strokeStyle = t.strokeColor, e.lineWidth = t.strokeWidth, e.strokeText(g.text, b, d)), g.whisper ? e.fillStyle = t.whisperColor || "rgba(255, 255, 255, 0.6)" : c.isQuote ? e.fillStyle = t.quoteColor || "#aaaaaa" : e.fillStyle = t.color, e.fillText(g.text, b, d), b += k;
      }
    }
    e.restore();
  }
}
typeof window < "u" && (window.TextAnimator = z);
export {
  z as TextAnimator
};
