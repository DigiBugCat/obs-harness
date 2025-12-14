/**
 * OBS Browser Source Channel Handler
 * Handles audio playback, streaming, and text overlays via WebSocket
 */

(function() {
    'use strict';

    // Get channel name from URL path
    const pathParts = window.location.pathname.split('/');
    const channelName = pathParts[pathParts.length - 1] || 'default';

    // WebSocket connection
    let ws = null;
    let reconnectTimeout = null;
    const reconnectDelay = 2000;

    // Audio elements
    let currentAudio = null;

    // Streaming audio
    let audioContext = null;
    let streamBuffer = [];
    let isStreaming = false;
    let streamSampleRate = 24000;
    let streamChannels = 1;
    let nextPlayTime = 0;
    let audioStreamEndTime = 0;  // When all scheduled audio will finish
    let firstAudioChunkReceived = false;  // Track if first audio chunk arrived

    // Pending text (waits for audio to start)
    let pendingTextSettings = null;
    let pendingTextChunks = [];

    // Canvas for text overlay
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');

    // Text animator instance
    let textAnimator = null;
    let hasError = false;

    // Resize canvas to match window
    function resizeCanvas() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        if (textAnimator) {
            textAnimator.resize(canvas.width, canvas.height);
        }
    }

    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    // Initialize text animator
    if (typeof TextAnimator !== 'undefined') {
        textAnimator = new TextAnimator(ctx, canvas.width, canvas.height);
    }

    // =========================================================================
    // WebSocket Connection
    // =========================================================================

    function connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/${channelName}`;

        ws = new WebSocket(wsUrl);
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
            console.log(`[${channelName}] Connected to server`);
            if (reconnectTimeout) {
                clearTimeout(reconnectTimeout);
                reconnectTimeout = null;
            }
        };

        ws.onclose = (event) => {
            // Handle channel not found error (don't reconnect)
            if (event.code === 4004) {
                console.error(`[${channelName}] Channel not found. Create it in the dashboard first.`);
                showErrorMessage('Channel not configured', 'Create it in the dashboard first');
                return; // Don't reconnect for unknown channels
            }

            console.log(`[${channelName}] Disconnected from server`);
            scheduleReconnect();
        };

        ws.onerror = (error) => {
            console.error(`[${channelName}] WebSocket error:`, error);
        };

        ws.onmessage = (event) => {
            if (event.data instanceof ArrayBuffer) {
                handleStreamData(event.data);
            } else {
                handleMessage(event.data);
            }
        };
    }

    function scheduleReconnect() {
        if (!reconnectTimeout) {
            reconnectTimeout = setTimeout(() => {
                console.log(`[${channelName}] Attempting to reconnect...`);
                connect();
            }, reconnectDelay);
        }
    }

    function sendEvent(event) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(event));
        }
    }

    // =========================================================================
    // Message Handler
    // =========================================================================

    function handleMessage(data) {
        try {
            const msg = JSON.parse(data);
            console.log(`[${channelName}] Received:`, msg);

            switch (msg.action) {
                case 'play':
                    playAudio(msg);
                    break;
                case 'stop':
                    stopAudio();
                    break;
                case 'volume':
                    setVolume(msg.level);
                    break;
                case 'stream_start':
                    startStream(msg);
                    break;
                case 'stream_end':
                    endStream();
                    break;
                case 'text':
                    showText(msg);
                    break;
                case 'clear_text':
                    clearText();
                    break;
                case 'text_stream_start':
                    startTextStream(msg);
                    break;
                case 'text_chunk':
                    handleTextChunk(msg);
                    break;
                case 'text_stream_end':
                    endTextStream();
                    break;
                default:
                    console.warn(`[${channelName}] Unknown action:`, msg.action);
            }
        } catch (e) {
            console.error(`[${channelName}] Error parsing message:`, e);
        }
    }

    // =========================================================================
    // Audio Playback (File-based)
    // =========================================================================

    function playAudio(msg) {
        // Stop any current audio
        if (currentAudio) {
            currentAudio.pause();
            currentAudio = null;
        }

        currentAudio = new Audio(msg.file);
        currentAudio.volume = msg.volume ?? 1.0;
        currentAudio.loop = msg.loop ?? false;

        currentAudio.onended = () => {
            if (!currentAudio.loop) {
                sendEvent({ event: 'ended', file: msg.file });
            }
        };

        currentAudio.onerror = (e) => {
            sendEvent({ event: 'error', message: `Failed to load: ${msg.file}` });
        };

        currentAudio.play().catch((e) => {
            sendEvent({ event: 'error', message: `Playback failed: ${e.message}` });
        });
    }

    function stopAudio() {
        if (currentAudio) {
            currentAudio.pause();
            currentAudio.currentTime = 0;
            currentAudio = null;
        }
    }

    function setVolume(level) {
        if (currentAudio) {
            currentAudio.volume = Math.max(0, Math.min(1, level));
        }
    }

    // =========================================================================
    // Audio Streaming
    // =========================================================================

    function startStream(msg) {
        // Create audio context if needed
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }

        // Resume audio context if suspended
        if (audioContext.state === 'suspended') {
            audioContext.resume();
        }

        streamSampleRate = msg.sample_rate || 24000;
        streamChannels = msg.channels || 1;
        streamBuffer = [];
        isStreaming = true;
        nextPlayTime = audioContext.currentTime;
        firstAudioChunkReceived = false;

        console.log(`[${channelName}] Stream started: ${streamSampleRate}Hz, ${streamChannels}ch`);
    }

    function handleStreamData(data) {
        if (!isStreaming || !audioContext) return;

        // Convert ArrayBuffer to Int16Array (PCM16 format)
        const int16Data = new Int16Array(data);

        // Convert to Float32 for Web Audio API
        const float32Data = new Float32Array(int16Data.length);
        for (let i = 0; i < int16Data.length; i++) {
            float32Data[i] = int16Data[i] / 32768.0;
        }

        // Create audio buffer
        const samplesPerChannel = float32Data.length / streamChannels;
        const audioBuffer = audioContext.createBuffer(
            streamChannels,
            samplesPerChannel,
            streamSampleRate
        );

        // Fill buffer channels
        for (let channel = 0; channel < streamChannels; channel++) {
            const channelData = audioBuffer.getChannelData(channel);
            for (let i = 0; i < samplesPerChannel; i++) {
                channelData[i] = float32Data[i * streamChannels + channel];
            }
        }

        // Schedule playback
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);

        // Ensure we don't schedule in the past
        if (nextPlayTime < audioContext.currentTime) {
            nextPlayTime = audioContext.currentTime;
        }

        source.start(nextPlayTime);

        // On first audio chunk, trigger pending text display
        if (!firstAudioChunkReceived) {
            firstAudioChunkReceived = true;
            flushPendingText();
        }

        nextPlayTime += audioBuffer.duration;
    }

    // Flush pending text to animator when audio starts
    function flushPendingText() {
        if (!textAnimator || !pendingTextSettings) return;

        // Start the text stream now that audio is playing
        textAnimator.startStream(pendingTextSettings);
        console.log(`[${channelName}] Text stream activated (synced to audio)`);

        // Send any buffered text chunks
        for (const chunk of pendingTextChunks) {
            textAnimator.appendText(chunk);
        }
        pendingTextChunks = [];
        pendingTextSettings = null;
    }

    function endStream() {
        isStreaming = false;
        streamBuffer = [];

        // Calculate when all scheduled audio will finish playing
        if (audioContext && nextPlayTime > audioContext.currentTime) {
            audioStreamEndTime = nextPlayTime;
            const remainingMs = (nextPlayTime - audioContext.currentTime) * 1000;
            console.log(`[${channelName}] Stream ended, audio finishes in ${remainingMs.toFixed(0)}ms`);
        } else {
            audioStreamEndTime = 0;
            console.log(`[${channelName}] Stream ended, no pending audio`);
        }

        // Clear pending text state (it should have been flushed by now)
        pendingTextSettings = null;
        pendingTextChunks = [];

        sendEvent({ event: 'stream_ended' });
    }

    // =========================================================================
    // Text Overlay
    // =========================================================================

    function showText(msg) {
        if (!textAnimator) {
            console.warn(`[${channelName}] TextAnimator not available`);
            return;
        }

        textAnimator.show({
            text: msg.text,
            style: msg.style || 'typewriter',
            duration: msg.duration || 3000,
            x: msg.position_x ?? 0.5,
            y: msg.position_y ?? 0.5,
            fontFamily: msg.font_family || 'Arial',
            fontSize: msg.font_size || 48,
            color: msg.color || '#ffffff',
            strokeColor: msg.stroke_color,
            strokeWidth: msg.stroke_width || 0,
            onComplete: () => {
                sendEvent({ event: 'text_complete' });
            }
        });
    }

    function clearText() {
        if (textAnimator) {
            textAnimator.clear();
        }
    }

    // =========================================================================
    // Streaming Text Overlay
    // =========================================================================

    function startTextStream(msg) {
        if (!textAnimator) {
            console.warn(`[${channelName}] TextAnimator not available`);
            return;
        }

        const settings = {
            fontFamily: msg.font_family || 'Arial',
            fontSize: msg.font_size || 48,
            color: msg.color || '#ffffff',
            strokeColor: msg.stroke_color,
            strokeWidth: msg.stroke_width || 0,
            positionX: msg.position_x ?? 0.5,
            positionY: msg.position_y ?? 0.5,
            instantReveal: msg.instant_reveal || false,
        };

        // If audio hasn't started yet, buffer the text settings
        if (!firstAudioChunkReceived) {
            pendingTextSettings = settings;
            pendingTextChunks = [];
            console.log(`[${channelName}] Text stream pending (waiting for audio)`);
        } else {
            // Audio already playing, start text immediately
            textAnimator.startStream(settings);
            console.log(`[${channelName}] Text stream started (instant=${msg.instant_reveal || false})`);
        }
    }

    function handleTextChunk(msg) {
        if (!textAnimator) return;

        // If text stream hasn't started yet, buffer chunks
        if (pendingTextSettings) {
            pendingTextChunks.push(msg.text);
        } else {
            textAnimator.appendText(msg.text);
        }
    }

    function endTextStream() {
        if (!textAnimator) return;

        // Calculate delay until audio finishes, then linger for 2 seconds
        const lingerTime = 2000;  // How long text stays after audio ends
        let fadeDelay = lingerTime;  // Default if no audio
        if (audioContext && audioStreamEndTime > audioContext.currentTime) {
            // Wait until audio finishes, then linger
            fadeDelay = (audioStreamEndTime - audioContext.currentTime) * 1000 + lingerTime;
        }

        textAnimator.endStream(fadeDelay);
        console.log(`[${channelName}] Text stream ended, fade in ${fadeDelay.toFixed(0)}ms`);
        sendEvent({ event: 'text_stream_complete' });
    }

    // =========================================================================
    // Error Display
    // =========================================================================

    function showErrorMessage(title, subtitle) {
        // Mark as error state to stop animation loop
        hasError = true;

        // Stop any animations
        if (textAnimator) {
            textAnimator.clear();
        }

        // Draw error message on canvas
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Semi-transparent background
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Error icon
        ctx.font = '48px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillStyle = '#ff4444';
        ctx.fillText('\u26A0', canvas.width / 2, canvas.height / 2 - 40);

        // Title
        ctx.font = 'bold 24px sans-serif';
        ctx.fillStyle = '#ffffff';
        ctx.fillText(title, canvas.width / 2, canvas.height / 2 + 10);

        // Subtitle
        ctx.font = '16px sans-serif';
        ctx.fillStyle = '#aaaaaa';
        ctx.fillText(subtitle, canvas.width / 2, canvas.height / 2 + 40);
    }

    // =========================================================================
    // Animation Loop
    // =========================================================================

    function animate() {
        // Don't animate if in error state
        if (hasError) {
            return;
        }

        // Clear canvas
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Update and draw text animator
        if (textAnimator) {
            // Handle streaming text
            if (textAnimator.isStreaming || textAnimator.streamText) {
                textAnimator.updateStream();
                textAnimator.drawStream();
            } else {
                // Handle regular animated text
                textAnimator.update();
                textAnimator.draw();
            }
        }

        requestAnimationFrame(animate);
    }

    // Start animation loop
    animate();

    // Connect to WebSocket
    connect();

    // Log channel info
    console.log(`[${channelName}] Browser source initialized`);
})();
