/**
 * Text Animator for OBS Browser Sources
 * Supports: typewriter, fade, slide, bounce, wave animations
 */

class TextAnimator {
    constructor(ctx, width, height) {
        this.ctx = ctx;
        this.width = width;
        this.height = height;

        this.queue = [];
        this.current = null;
        this.startTime = 0;

        // Streaming text state
        this.isStreaming = false;
        this.streamText = '';
        this.revealIndex = 0;
        this.streamSettings = null;
        this.lastRevealTime = 0;
        this.revealRate = 40; // chars per second
        this.streamFadeStart = null;
        this.streamFadeDuration = 1000;
        this.streamOpacity = 1;

        // Max lines to display at once (cull old sentences when exceeded)
        this.maxDisplayLines = 4;

        // Fade-out state for clearing old sentences
        this.clearFadeStart = null;
        this.clearFadeDuration = 400; // ms
        this.pendingSentencesToRemove = null;

        // Committed sentences - each sentence is an array of lines
        this.committedSentences = [];
        this.lastCommittedIndex = 0; // Index in streamText where we last committed
    }

    resize(width, height) {
        this.width = width;
        this.height = height;
    }

    show(options) {
        const item = {
            text: options.text || '',
            style: options.style || 'typewriter',
            duration: options.duration || 3000,
            x: options.x ?? 0.5,
            y: options.y ?? 0.5,
            fontFamily: options.fontFamily || 'Arial',
            fontSize: options.fontSize || 48,
            color: options.color || '#ffffff',
            strokeColor: options.strokeColor || null,
            strokeWidth: options.strokeWidth || 0,
            onComplete: options.onComplete || null,
            // Animation state
            progress: 0,
            chars: options.text.split(''),
            charStates: [],
            // Text wrapping - will be calculated in next()
            lines: [],
            lineHeight: (options.fontSize || 48) * 1.3,
        };

        // Initialize character states for per-character animations
        for (let i = 0; i < item.chars.length; i++) {
            item.charStates.push({
                visible: false,
                offset: 0,
                opacity: 0,
                scale: 1,
            });
        }

        this.queue.push(item);

        if (!this.current) {
            this.next();
        }
    }

    clear() {
        this.queue = [];
        this.current = null;
    }

    next() {
        if (this.queue.length > 0) {
            this.current = this.queue.shift();
            this.startTime = performance.now();
            // Calculate wrapped lines for the new item
            this.current.lines = this.wrapText(this.current);
        } else {
            this.current = null;
        }
    }

    wrapText(item) {
        // Set up font for measurement
        this.ctx.font = `${item.fontSize}px ${item.fontFamily}`;

        // Use 90% of canvas width as max width, with padding
        const maxWidth = this.width * 0.9;
        const words = item.text.split(' ');
        const lines = [];
        let currentLine = '';
        let charIndex = 0;

        for (let i = 0; i < words.length; i++) {
            const word = words[i];
            const testLine = currentLine ? currentLine + ' ' + word : word;
            const metrics = this.ctx.measureText(testLine);

            if (metrics.width > maxWidth && currentLine) {
                // Push current line and start new one
                const lineChars = currentLine.split('');
                lines.push({
                    text: currentLine,
                    startIndex: charIndex,
                    endIndex: charIndex + lineChars.length,
                });
                charIndex += lineChars.length + 1; // +1 for space
                currentLine = word;
            } else {
                currentLine = testLine;
            }
        }

        // Push the last line
        if (currentLine) {
            lines.push({
                text: currentLine,
                startIndex: charIndex,
                endIndex: charIndex + currentLine.length,
            });
        }

        return lines;
    }

    update() {
        if (!this.current) return;

        const elapsed = performance.now() - this.startTime;
        const item = this.current;
        item.progress = Math.min(elapsed / item.duration, 1);

        // Update based on animation style
        switch (item.style) {
            case 'typewriter':
                this.updateTypewriter(item, elapsed);
                break;
            case 'fade':
                this.updateFade(item, elapsed);
                break;
            case 'slide':
                this.updateSlide(item, elapsed);
                break;
            case 'bounce':
                this.updateBounce(item, elapsed);
                break;
            case 'wave':
                this.updateWave(item, elapsed);
                break;
            default:
                this.updateTypewriter(item, elapsed);
        }

        // Check if animation is complete
        if (item.progress >= 1) {
            if (item.onComplete) {
                item.onComplete();
            }
            this.next();
        }
    }

    // =========================================================================
    // Animation Updates
    // =========================================================================

    updateTypewriter(item, elapsed) {
        // Reveal characters one by one over first 60% of duration
        const revealDuration = item.duration * 0.6;
        const revealProgress = Math.min(elapsed / revealDuration, 1);
        const charsToShow = Math.floor(revealProgress * item.chars.length);

        for (let i = 0; i < item.chars.length; i++) {
            item.charStates[i].visible = i < charsToShow;
            item.charStates[i].opacity = item.charStates[i].visible ? 1 : 0;
        }

        // Fade out in last 20% of duration
        const fadeStart = item.duration * 0.8;
        if (elapsed > fadeStart) {
            const fadeProgress = (elapsed - fadeStart) / (item.duration * 0.2);
            const fadeOpacity = 1 - fadeProgress;
            for (let i = 0; i < item.chars.length; i++) {
                if (item.charStates[i].visible) {
                    item.charStates[i].opacity = fadeOpacity;
                }
            }
        }
    }

    updateFade(item, elapsed) {
        // Fade in over first 20%, hold, fade out over last 20%
        const fadeInEnd = item.duration * 0.2;
        const fadeOutStart = item.duration * 0.8;

        let opacity = 1;
        if (elapsed < fadeInEnd) {
            opacity = elapsed / fadeInEnd;
        } else if (elapsed > fadeOutStart) {
            opacity = 1 - (elapsed - fadeOutStart) / (item.duration * 0.2);
        }

        for (let i = 0; i < item.chars.length; i++) {
            item.charStates[i].visible = true;
            item.charStates[i].opacity = opacity;
        }
    }

    updateSlide(item, elapsed) {
        // Slide in from left over first 20%, hold, slide out right over last 20%
        const slideInEnd = item.duration * 0.2;
        const slideOutStart = item.duration * 0.8;

        let offset = 0;
        let opacity = 1;

        if (elapsed < slideInEnd) {
            const progress = elapsed / slideInEnd;
            const eased = this.easeOutCubic(progress);
            offset = (1 - eased) * -this.width * 0.3;
            opacity = progress;
        } else if (elapsed > slideOutStart) {
            const progress = (elapsed - slideOutStart) / (item.duration * 0.2);
            const eased = this.easeInCubic(progress);
            offset = eased * this.width * 0.3;
            opacity = 1 - progress;
        }

        for (let i = 0; i < item.chars.length; i++) {
            item.charStates[i].visible = true;
            item.charStates[i].offset = offset;
            item.charStates[i].opacity = opacity;
        }
    }

    updateBounce(item, elapsed) {
        // Bounce in characters sequentially
        const bounceInDuration = item.duration * 0.4;
        const fadeOutStart = item.duration * 0.8;

        for (let i = 0; i < item.chars.length; i++) {
            const charDelay = (i / item.chars.length) * bounceInDuration * 0.5;
            const charElapsed = elapsed - charDelay;

            if (charElapsed < 0) {
                item.charStates[i].visible = false;
                item.charStates[i].opacity = 0;
                item.charStates[i].offset = -50;
                continue;
            }

            item.charStates[i].visible = true;

            const charDuration = bounceInDuration * 0.5;
            if (charElapsed < charDuration) {
                const progress = charElapsed / charDuration;
                const bounce = this.easeOutBounce(progress);
                item.charStates[i].offset = (1 - bounce) * -50;
                item.charStates[i].opacity = Math.min(progress * 2, 1);
            } else {
                item.charStates[i].offset = 0;
                item.charStates[i].opacity = 1;
            }
        }

        // Fade out
        if (elapsed > fadeOutStart) {
            const fadeProgress = (elapsed - fadeOutStart) / (item.duration * 0.2);
            for (let i = 0; i < item.chars.length; i++) {
                item.charStates[i].opacity = 1 - fadeProgress;
            }
        }
    }

    updateWave(item, elapsed) {
        // Wave motion on characters
        const fadeInEnd = item.duration * 0.1;
        const fadeOutStart = item.duration * 0.8;

        let baseOpacity = 1;
        if (elapsed < fadeInEnd) {
            baseOpacity = elapsed / fadeInEnd;
        } else if (elapsed > fadeOutStart) {
            baseOpacity = 1 - (elapsed - fadeOutStart) / (item.duration * 0.2);
        }

        const waveSpeed = 0.005;
        const waveHeight = 15;

        for (let i = 0; i < item.chars.length; i++) {
            item.charStates[i].visible = true;
            item.charStates[i].opacity = baseOpacity;
            item.charStates[i].offset = Math.sin(elapsed * waveSpeed + i * 0.5) * waveHeight;
        }
    }

    // =========================================================================
    // Drawing
    // =========================================================================

    draw() {
        if (!this.current) return;

        const item = this.current;
        const ctx = this.ctx;

        // Calculate base position
        const centerX = item.x * this.width;
        const centerY = item.y * this.height;

        // Set font
        ctx.font = `${item.fontSize}px ${item.fontFamily}`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        // Calculate total height of all lines for vertical centering
        const totalHeight = item.lines.length * item.lineHeight;
        const startY = centerY - totalHeight / 2 + item.lineHeight / 2;

        // Draw each line
        for (let lineIdx = 0; lineIdx < item.lines.length; lineIdx++) {
            const line = item.lines[lineIdx];
            const lineY = startY + lineIdx * item.lineHeight;

            // Measure this line's width for horizontal centering
            const lineWidth = ctx.measureText(line.text).width;
            let startX = centerX - lineWidth / 2;

            // Draw each character in this line
            for (let i = line.startIndex; i < line.endIndex && i < item.chars.length; i++) {
                const localIdx = i - line.startIndex;
                const state = item.charStates[i];

                if (!state.visible || state.opacity <= 0) {
                    startX += ctx.measureText(item.chars[i]).width;
                    continue;
                }

                const char = item.chars[i];
                const charWidth = ctx.measureText(char).width;
                const charX = startX + charWidth / 2 + (state.offset || 0);
                const charY = lineY + (item.style === 'wave' || item.style === 'bounce' ? state.offset : 0);

                ctx.save();
                ctx.globalAlpha = state.opacity;

                // Draw stroke if configured
                if (item.strokeColor && item.strokeWidth > 0) {
                    ctx.strokeStyle = item.strokeColor;
                    ctx.lineWidth = item.strokeWidth;
                    ctx.strokeText(char, charX, charY);
                }

                // Draw fill
                ctx.fillStyle = item.color;
                ctx.fillText(char, charX, charY);

                ctx.restore();

                startX += charWidth;
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
        const n1 = 7.5625;
        const d1 = 2.75;

        if (t < 1 / d1) {
            return n1 * t * t;
        } else if (t < 2 / d1) {
            return n1 * (t -= 1.5 / d1) * t + 0.75;
        } else if (t < 2.5 / d1) {
            return n1 * (t -= 2.25 / d1) * t + 0.9375;
        } else {
            return n1 * (t -= 2.625 / d1) * t + 0.984375;
        }
    }

    // =========================================================================
    // Streaming Text Support
    // =========================================================================

    /**
     * Start streaming text display mode.
     * @param {Object} settings - Text styling settings
     */
    startStream(settings) {
        this.isStreaming = true;
        this.streamText = '';
        this.revealIndex = 0;
        this.clearFadeStart = null;
        this.pendingSentencesToRemove = null;
        this.committedSentences = [];
        this.lastCommittedIndex = 0;
        this.streamSettings = {
            fontFamily: settings.fontFamily || 'Arial',
            fontSize: settings.fontSize || 48,
            color: settings.color || '#ffffff',
            strokeColor: settings.strokeColor || null,
            strokeWidth: settings.strokeWidth || 0,
            positionX: settings.positionX ?? 0.5,
            positionY: settings.positionY ?? 0.5,
            instantReveal: settings.instantReveal || false,
        };
        this.lastRevealTime = performance.now();
        this.streamFadeStart = null;
        this.streamOpacity = 1;

        // Clear any existing animation
        this.current = null;
        this.queue = [];
    }

    /**
     * Append text to the streaming buffer.
     * @param {string} text - Text chunk to append
     */
    appendText(text) {
        if (!this.isStreaming) return;
        this.streamText += text;
    }

    /**
     * End streaming mode and schedule fade-out.
     * @param {number} fadeDelay - Delay in ms before starting fade (default 500ms)
     */
    endStream(fadeDelay = 500) {
        // Keep isStreaming true until fadeDelay so appendText() continues to work
        // This allows word-synced reveals to continue until audio finishes
        setTimeout(() => {
            this.isStreaming = false;
            this.streamFadeStart = performance.now();
        }, fadeDelay);
    }

    /**
     * Clear streaming text immediately.
     */
    clearStream() {
        this.isStreaming = false;
        this.streamText = '';
        this.revealIndex = 0;
        this.clearFadeStart = null;
        this.pendingSentencesToRemove = null;
        this.committedSentences = [];
        this.lastCommittedIndex = 0;
        this.streamFadeStart = null;
        this.streamSettings = null;
    }

    /**
     * Update streaming text state (progressive reveal).
     */
    updateStream() {
        if (!this.streamText) return;

        // Handle fade out
        if (this.streamFadeStart) {
            const fadeElapsed = performance.now() - this.streamFadeStart;
            this.streamOpacity = 1 - (fadeElapsed / this.streamFadeDuration);
            if (this.streamOpacity <= 0) {
                this.streamText = '';
                this.streamFadeStart = null;
                this.streamSettings = null;
                return;
            }
        }

        // Instant reveal mode - show all text immediately
        if (this.streamSettings && this.streamSettings.instantReveal) {
            this.revealIndex = this.streamText.length;
            return;
        }

        // Progressive reveal while streaming
        if (this.isStreaming || this.revealIndex < this.streamText.length) {
            const now = performance.now();
            const elapsed = now - this.lastRevealTime;
            const charsToReveal = Math.floor(elapsed / (1000 / this.revealRate));

            if (charsToReveal > 0) {
                this.revealIndex = Math.min(
                    this.revealIndex + charsToReveal,
                    this.streamText.length
                );
                this.lastRevealTime = now;
            }
        }
    }

    /**
     * Parse text into formatted segments.
     * Supports **bold**, *italic*, ^whisper^, and newlines.
     * @param {string} text - Raw text with formatting markers
     * @returns {Array} Array of {text, bold, italic, whisper, newline} segments
     */
    parseFormattedText(text) {
        const segments = [];
        let remaining = text;
        let currentBold = false;
        let currentItalic = false;
        let currentWhisper = false;

        while (remaining.length > 0) {
            // Check for newline
            if (remaining[0] === '\n') {
                segments.push({ text: '', newline: true, bold: false, italic: false, whisper: false });
                remaining = remaining.substring(1);
                continue;
            }

            // Check for bold marker **
            if (remaining.startsWith('**')) {
                currentBold = !currentBold;
                remaining = remaining.substring(2);
                continue;
            }

            // Check for italic marker * (but not **)
            if (remaining[0] === '*' && !remaining.startsWith('**')) {
                currentItalic = !currentItalic;
                remaining = remaining.substring(1);
                continue;
            }

            // Check for whisper marker ^
            if (remaining[0] === '^') {
                currentWhisper = !currentWhisper;
                remaining = remaining.substring(1);
                continue;
            }

            // Find next marker or newline
            let nextMarker = remaining.length;
            const markers = [
                remaining.indexOf('**'),
                remaining.indexOf('*'),
                remaining.indexOf('^'),
                remaining.indexOf('\n')
            ].filter(i => i > 0);

            if (markers.length > 0) {
                nextMarker = Math.min(...markers);
            }

            // Extract text up to next marker
            const chunk = remaining.substring(0, nextMarker);
            if (chunk) {
                segments.push({
                    text: chunk,
                    bold: currentBold,
                    italic: currentItalic,
                    whisper: currentWhisper,
                    newline: false
                });
            }
            remaining = remaining.substring(nextMarker);
        }

        return segments;
    }

    /**
     * Measure width of formatted segments.
     * @param {Array} segments - Parsed segments
     * @param {Object} settings - Font settings
     * @returns {number} Total width in pixels
     */
    measureFormattedText(segments, settings) {
        const ctx = this.ctx;
        let width = 0;

        for (const seg of segments) {
            if (seg.newline) continue;
            // Whisper uses italic and smaller font
            const isItalic = seg.italic || seg.whisper;
            const fontSize = seg.whisper ? settings.fontSize * 0.85 : settings.fontSize;
            const fontStyle = (seg.bold ? 'bold ' : '') + (isItalic ? 'italic ' : '');
            ctx.font = `${fontStyle}${fontSize}px ${settings.fontFamily}`;
            width += ctx.measureText(seg.text).width;
        }

        return width;
    }

    /**
     * Wrap a paragraph into lines while preserving formatting across line breaks.
     * @param {string} paraText - Paragraph text with formatting markers
     * @param {number} maxWidth - Maximum line width in pixels
     * @param {Object} settings - Font settings
     * @param {boolean} isQuote - Whether this is a quote line
     * @returns {Array} Array of lines, each with segments array and isQuote flag
     */
    wrapFormattedParagraph(paraText, maxWidth, settings, isQuote = false) {
        const segments = this.parseFormattedText(paraText);
        const lines = [];
        let currentLine = [];
        let currentLineWidth = 0;

        for (const seg of segments) {
            // Handle explicit newlines - finish current line and start new one
            if (seg.newline) {
                if (currentLine.length > 0) {
                    lines.push({ segments: currentLine, isQuote });
                    currentLine = [];
                    currentLineWidth = 0;
                }
                continue;
            }

            // Set font for accurate measurement (whisper uses smaller font)
            const isItalic = seg.italic || seg.whisper;
            const fontSize = seg.whisper ? settings.fontSize * 0.85 : settings.fontSize;
            const fontStyle = (seg.bold ? 'bold ' : '') + (isItalic ? 'italic ' : '');
            this.ctx.font = `${fontStyle}${fontSize}px ${settings.fontFamily}`;

            // Split segment text by word boundaries (keeping whitespace)
            const parts = seg.text.split(/(\s+)/);

            for (const part of parts) {
                if (part === '') continue;

                const partWidth = this.ctx.measureText(part).width;

                // Check if adding this part would exceed maxWidth
                if (currentLineWidth + partWidth > maxWidth && currentLine.length > 0) {
                    // Push current line and start new one
                    lines.push({ segments: currentLine, isQuote });
                    currentLine = [];
                    currentLineWidth = 0;
                }

                // Add part to current line (preserving formatting from original segment)
                if (part.trim() || currentLine.length > 0) {
                    currentLine.push({ text: part, bold: seg.bold, italic: seg.italic, whisper: seg.whisper, newline: false });
                    currentLineWidth += partWidth;
                }
            }
        }

        // Push final line if non-empty
        if (currentLine.length > 0) {
            lines.push({ segments: currentLine, isQuote });
        }

        return lines;
    }

    /**
     * Get the formatting state (bold/italic) at a given position in the text.
     * Scans from the start to count formatting marker toggles.
     * @param {string} text - The full text
     * @param {number} position - Position to check state at
     * @returns {Object} {bold: boolean, italic: boolean}
     */
    getFormattingStateAt(text, position) {
        let bold = false;
        let italic = false;
        let i = 0;

        while (i < position && i < text.length) {
            if (text.substring(i, i + 2) === '**') {
                bold = !bold;
                i += 2;
            } else if (text[i] === '*') {
                italic = !italic;
                i += 1;
            } else {
                i += 1;
            }
        }

        return { bold, italic };
    }

    /**
     * Find sentence ending in text, returns index after the ending or -1.
     */
    findSentenceEnd(text, startFrom = 0) {
        const endings = ['. ', '! ', '? ', '.\n', '!\n', '?\n', '."', '!"', '?"', ".'", "!'", "?'"];
        let earliest = -1;
        let matchedEnding = null;

        for (const ending of endings) {
            const idx = text.indexOf(ending, startFrom);
            if (idx !== -1 && (earliest === -1 || idx < earliest)) {
                earliest = idx;
                matchedEnding = ending;
            }
        }

        if (earliest !== -1 && matchedEnding) {
            // Return position after the full ending pattern (e.g., after ." not just .)
            return earliest + matchedEnding.length;
        }
        return -1;
    }

    /**
     * Draw streaming text with word wrapping and formatting.
     * Uses committed sentences to prevent text from shifting.
     */
    drawStream() {
        if (!this.streamText || !this.streamSettings) return;

        const settings = this.streamSettings;
        const ctx = this.ctx;
        const maxWidth = this.width * 0.9;
        const lineHeight = settings.fontSize * 1.3;

        // Handle fade-out animation for clearing old sentences
        let clearFadeOpacity = 1;
        if (this.clearFadeStart !== null) {
            const fadeElapsed = performance.now() - this.clearFadeStart;
            clearFadeOpacity = 1 - (fadeElapsed / this.clearFadeDuration);

            if (clearFadeOpacity <= 0) {
                // Fade complete - remove oldest committed sentences
                const sentencesToRemove = this.pendingSentencesToRemove || 1;
                this.committedSentences.splice(0, sentencesToRemove);
                this.pendingSentencesToRemove = null;
                this.clearFadeStart = null;
                clearFadeOpacity = 1;
            }
        }

        // Get revealed text
        const revealedText = this.streamText.substring(0, this.revealIndex);
        if (!revealedText) return;

        // Check for new sentence endings to commit
        const unprocessedText = revealedText.substring(this.lastCommittedIndex);
        let searchPos = 0;
        let sentenceEnd = this.findSentenceEnd(unprocessedText, searchPos);

        while (sentenceEnd !== -1) {
            // Found a sentence ending - commit this sentence
            const sentenceText = unprocessedText.substring(searchPos, sentenceEnd);

            if (sentenceText.trim()) {
                // Get formatting state at start of this sentence
                const formatState = this.getFormattingStateAt(this.streamText, this.lastCommittedIndex + searchPos);
                let textToWrap = sentenceText;
                if (formatState.bold) textToWrap = '**' + textToWrap;
                if (formatState.italic) textToWrap = '*' + textToWrap;

                // Wrap this sentence into lines
                const isQuote = textToWrap.trimStart().startsWith('>');
                const paraText = isQuote ? textToWrap.trimStart().substring(1).trimStart() : textToWrap;
                const wrappedLines = this.wrapFormattedParagraph(paraText, maxWidth, settings, isQuote);

                // Store as a sentence (group of lines)
                this.committedSentences.push({
                    lines: wrappedLines
                });
            }

            searchPos = sentenceEnd;
            // Skip any whitespace after sentence
            while (searchPos < unprocessedText.length && /\s/.test(unprocessedText[searchPos])) {
                searchPos++;
            }
            sentenceEnd = this.findSentenceEnd(unprocessedText, searchPos);
        }

        // Update last committed index
        this.lastCommittedIndex += searchPos;

        // Get current (uncommitted) text
        const currentText = revealedText.substring(this.lastCommittedIndex);
        let currentLines = [];

        if (currentText.trim()) {
            // Get formatting state for current text
            const formatState = this.getFormattingStateAt(this.streamText, this.lastCommittedIndex);
            let textToWrap = currentText;
            if (formatState.bold) textToWrap = '**' + textToWrap;
            if (formatState.italic) textToWrap = '*' + textToWrap;

            const isQuote = textToWrap.trimStart().startsWith('>');
            const paraText = isQuote ? textToWrap.trimStart().substring(1).trimStart() : textToWrap;
            currentLines = this.wrapFormattedParagraph(paraText, maxWidth, settings, isQuote);
        }

        // Flatten committed sentences into lines array
        const committedLines = this.committedSentences.flatMap(s => s.lines);

        // Combine committed + current lines
        const allLines = [...committedLines, ...currentLines];

        // Apply line cap - when total lines exceed max, fade out everything and start fresh
        // (only if we have committed sentences to clear)
        const totalLines = allLines.length;
        if (totalLines > this.maxDisplayLines && this.clearFadeStart === null && this.committedSentences.length > 0) {
            // Fade out all lines, then reset
            this.pendingSentencesToRemove = this.committedSentences.length;
            this.clearFadeStart = performance.now();
        }

        if (allLines.length === 0) return;

        // Calculate position - anchor to top, horizontally centered
        const centerX = settings.positionX * this.width;
        const topY = settings.positionY * this.height;
        const startY = topY + lineHeight / 2;

        // Draw each line
        ctx.save();
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.globalAlpha = this.streamOpacity * clearFadeOpacity;

        for (let i = 0; i < allLines.length; i++) {
            const line = allLines[i];
            const lineY = startY + i * lineHeight;

            // Calculate line width for centering
            const lineWidth = this.measureFormattedText(line.segments, settings);
            let lineX = centerX - lineWidth / 2;

            // Draw quote indicator
            if (line.isQuote) {
                ctx.font = `${settings.fontSize}px ${settings.fontFamily}`;
                ctx.fillStyle = settings.quoteColor || '#888888';
                ctx.fillText('│ ', lineX - ctx.measureText('│ ').width, lineY);
            }

            // Draw each segment
            for (const seg of line.segments) {
                if (seg.newline) continue;

                // Whisper uses italic and smaller font
                const isItalic = seg.italic || seg.whisper;
                const fontSize = seg.whisper ? settings.fontSize * 0.85 : settings.fontSize;
                const fontStyle = (seg.bold ? 'bold ' : '') + (isItalic ? 'italic ' : '');
                ctx.font = `${fontStyle}${fontSize}px ${settings.fontFamily}`;

                const segWidth = ctx.measureText(seg.text).width;

                // Draw stroke if configured
                if (settings.strokeColor && settings.strokeWidth > 0) {
                    ctx.strokeStyle = settings.strokeColor;
                    ctx.lineWidth = settings.strokeWidth;
                    ctx.strokeText(seg.text, lineX, lineY);
                }

                // Draw fill - whisper uses lighter color, quote uses quote color
                if (seg.whisper) {
                    ctx.fillStyle = settings.whisperColor || 'rgba(255, 255, 255, 0.6)';
                } else if (line.isQuote) {
                    ctx.fillStyle = settings.quoteColor || '#aaaaaa';
                } else {
                    ctx.fillStyle = settings.color;
                }
                ctx.fillText(seg.text, lineX, lineY);

                lineX += segWidth;
            }
        }

        ctx.restore();
    }
}

// Export for use in other scripts
if (typeof window !== 'undefined') {
    window.TextAnimator = TextAnimator;
}
