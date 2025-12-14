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
}

// Export for use in other scripts
if (typeof window !== 'undefined') {
    window.TextAnimator = TextAnimator;
}
