// ---------------------------------------------------------------------
//   Frontend logic handling UI, audio recording, and API communication.
// ---------------------------------------------------------------------
// ── Global State ─────────────────────────────────────────────────────────────
let abortController = null;
let currentConversationId = null;
let isSTTEnabled = true;

// ── AudioQueue ──────────────────────────────────────────────────────────────
// Decodes base64 WAV chunks and schedules them for gapless sequential playback.
// ---------------------------------------------------------------------
//   Class: AudioQueue (Handles gapless audio playback)
// ---------------------------------------------------------------------
class AudioQueue {
    constructor() {
        this._ctx = null;
        this._nextStart = 0;
        this._isPaused = false;
        this._cancelled = false;
    }

    // ---------------------------------------------------------------------
    //   Gets or creates the AudioContext.
    // ---------------------------------------------------------------------
    _ctx_get() {
        if (!this._ctx) {
            this._ctx = new (window.AudioContext || window.webkitAudioContext)();
            this._nextStart = this._ctx.currentTime;
        }
        return this._ctx;
    }

    // ---------------------------------------------------------------------
    //   Decodes base64 WAV and schedules it for playback.
    // ---------------------------------------------------------------------
    async enqueue(base64Wav) {
        if (this._cancelled) return; // Ignore if cancelled

        try {
            const ctx = this._ctx_get();
            const binary = atob(base64Wav);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
            const audioBuffer = await ctx.decodeAudioData(bytes.buffer);

            // Re-check after async decode
            if (this._cancelled) return;

            const startAt = Math.max(ctx.currentTime, this._nextStart);
            const source = ctx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(ctx.destination);
            source.start(startAt);

            this._nextStart = startAt + audioBuffer.duration;
        } catch (err) {
            console.error("AudioQueue error:", err);
        }
    }

    // ---------------------------------------------------------------------
    //   Pauses audio context.
    // ---------------------------------------------------------------------
    pause() {
        if (this._ctx && this._ctx.state === 'running') {
            this._ctx.suspend();
            this._isPaused = true;
            return true;
        }
        return false;
    }

    // ---------------------------------------------------------------------
    //   Resumes audio context.
    // ---------------------------------------------------------------------
    resume() {
        if (this._ctx && this._ctx.state === 'suspended') {
            this._ctx.resume();
            this._isPaused = false;
            return true;
        }
        return false;
    }

    // ---------------------------------------------------------------------
    //   Stops playback and clears queue.
    // ---------------------------------------------------------------------
    stop() {
        this._cancelled = true;
        if (this._ctx) {
            this._ctx.close();
            this._ctx = null;
        }
        this._nextStart = 0;
        this._isPaused = false;

        // Physically abort the fetch stream
        if (abortController) {
            abortController.abort();
            abortController = null;
        }
    }

    // ---------------------------------------------------------------------
    //   Resets queue state.
    // ---------------------------------------------------------------------
    reset() {
        this._cancelled = false;
        this._nextStart = 0;
    }

    get isPaused() { return this._isPaused; }
}

const audioQueue = new AudioQueue();

// ── UI Actions ─────────────────────────────────────────────────────────────

const chatWindow = () => document.getElementById("chat-window");
const voiceOverlay = () => document.getElementById("voice-overlay");

// ---------------------------------------------------------------------
//   Formats timestamp for display.
// ---------------------------------------------------------------------
function formatTimestamp(dbTimestamp) {
    if (!dbTimestamp) return "Just now";
    try {
        const dt = new Date(dbTimestamp + " UTC");
        if (isNaN(dt)) return "Just now";
        return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return "Just now";
    }
}

// ---------------------------------------------------------------------
//   Formats date for conversation list.
// ---------------------------------------------------------------------
function formatConversationDate(dbTimestamp) {
    if (!dbTimestamp) return "";
    try {
        const dt = new Date(dbTimestamp + " UTC");
        if (isNaN(dt)) return "";

        const now = new Date();
        const isToday = dt.toDateString() === now.toDateString();

        if (isToday) {
            return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } else {
            return dt.toLocaleDateString([], { month: 'short', day: 'numeric' });
        }
    } catch (e) {
        return "";
    }
}

// ---------------------------------------------------------------------
//   Adds a chat bubble to the UI.
// ---------------------------------------------------------------------
function addBubble(type, initialText = "", timestamp = null) {
    const isAI = type === "ai";
    const displayTime = timestamp ? formatTimestamp(timestamp) : new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const wrap = document.createElement("div");
    wrap.className = `message-wrap ${isAI ? 'ai-wrap' : 'user-wrap'}`;
    const msg = document.createElement("div");
    msg.className = `message ${isAI ? 'ai-msg' : 'user-msg'}`;
    msg.textContent = initialText;
    const meta = document.createElement("div");
    meta.className = "msg-meta";
    meta.innerHTML = `<i class="fas ${isAI ? 'fa-robot' : 'fa-user'}"></i> ${isAI ? 'XBot-6' : 'You'} • ${displayTime}`;
    wrap.appendChild(msg);
    wrap.appendChild(meta);
    chatWindow().appendChild(wrap);
    scrollChat();
    return msg;
}

// ---------------------------------------------------------------------
//   Scrolls chat window to bottom.
// ---------------------------------------------------------------------
function scrollChat() {
    const win = chatWindow();
    win.scrollTo({ top: win.scrollHeight, behavior: 'smooth' });
}

// ---------------------------------------------------------------------
//   Updates UI for recording state.
// ---------------------------------------------------------------------
function setRecordingState(isRecording) {
    const overlay = voiceOverlay();
    if (overlay) {
        overlay.style.display = isRecording ? 'flex' : 'none';
        // Update text if a specific container exists, or just the overlay content
        const msgDiv = overlay.querySelector('.voice-msg') || overlay;
        if (isRecording && msgDiv) {
             // Preserve icon if it exists, roughly
             if (!msgDiv.innerHTML.includes("Analyzing")) {
                 msgDiv.innerHTML = '<i class="fas fa-microchip"></i> Analyzing Bio-Digital Waves...';
             }
        }
    }
    const trigger = document.getElementById("voice-trigger");
    if (trigger) {
        if (isRecording) trigger.classList.add('active');
        else trigger.classList.remove('active');
    }
}

// ---------------------------------------------------------------------
//   Reads NDJSON stream from server.
// ---------------------------------------------------------------------
async function streamNDJSON(url, options, onEvent) {
    const response = await fetch(url, options);
    if (!response.ok) {
        throw new Error(`Server Error: ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed) {
                try { onEvent(JSON.parse(trimmed)); } catch (e) { }
            }
        }
    }
}

// ── Core Handlers ────────────────────────────────────────────────────────────

// ---------------------------------------------------------------------
//   Sends text prompt to server and handles streaming response.
// ---------------------------------------------------------------------
async function sendTextPrompt(text) {
    let isNew = false;
    if (!currentConversationId) {
        await createConversation("New Chat");
        isNew = true;
    }

    audioQueue.stop();
    audioQueue.reset();

    abortController = new AbortController();

    addBubble("user", text);
    const aiMsgDiv = addBubble("ai", "");
    let fullText = "";

    try {
        await streamNDJSON(`/process_prompt`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, conv_id: currentConversationId }),
            signal: abortController.signal
        }, (event) => {
            if (event.type === "chunk") {
                fullText += event.text;
                aiMsgDiv.innerHTML = marked.parse(fullText);
                scrollChat();
            } else if (event.type === "audio_chunk") {
                audioQueue.enqueue(event.data);
            }
        });

        // Auto-title if this was the first message
        if (isNew) {
            await autoTitleConversation(currentConversationId, text);
        }
    } catch (err) {
        if (err.name === 'AbortError') {
            console.log("Fetch aborted");
        } else {
            console.error(err);
            aiMsgDiv.textContent = "[Error]";
        }
    }
}

// ---------------------------------------------------------------------
//   Class: Recorder (Handles Audio Recording)
// ---------------------------------------------------------------------
class Recorder {
    constructor() { this.isRecording = false; this.mediaRecorder = null; this.audioChunks = []; }
    // ---------------------------------------------------------------------
    //   Starts microphone recording.
    // ---------------------------------------------------------------------
    async startRecording() {
        if (!isSTTEnabled) return;
        if (this.isRecording) return;
        this.isRecording = true;
        setRecordingState(true);
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            
            // Check if recording was stopped/cancelled while waiting for permission
            if (!this.isRecording) {
                stream.getTracks().forEach(t => t.stop());
                setRecordingState(false);
                return;
            }

            this.mediaRecorder = new MediaRecorder(stream);
            this.mediaRecorder.ondataavailable = (e) => this.audioChunks.push(e.data);
            this.mediaRecorder.onstop = async () => {
                setRecordingState(false);
                const audioBlob = new Blob(this.audioChunks, { type: "audio/wav" });
                const formData = new FormData();
                formData.append("audio", audioBlob, "recording.wav");

                audioQueue.stop();
                audioQueue.reset();
                abortController = new AbortController();

                let isNew = false;
                if (!currentConversationId) {
                    await createConversation("Voice Chat");
                    isNew = true;
                }

                const aiMsgDiv = addBubble("ai", "⏳ Processing...");
                let fullText = "";
                try {
                    await streamNDJSON(`/process_audio?conv_id=${currentConversationId}`, {
                        method: "POST",
                        body: formData,
                        signal: abortController.signal
                    }, (event) => {
                        if (event.type === "transcribed") {
                            const aiWrap = aiMsgDiv.closest('.message-wrap');
                            if (aiMsgDiv.textContent === "⏳ Processing...") {
                                aiMsgDiv.textContent = "";
                            }
                            const userWrap = document.createElement("div");
                            userWrap.className = "message-wrap user-wrap";
                            userWrap.innerHTML = `<div class="message user-msg">${event.text}</div><div class="msg-meta"><i class="fas fa-user"></i> You • Just now</div>`;
                            chatWindow().insertBefore(userWrap, aiWrap);
                            aiMsgDiv.textContent = "";
                            scrollChat();

                            // Capture for auto-titling if new
                            if (isNew) {
                                autoTitleConversation(currentConversationId, event.text);
                                isNew = false; // Prevent multiple title updates if events glitch
                            }
                        } else if (event.type === "chunk") {
                            fullText += event.text;
                            aiMsgDiv.innerHTML = marked.parse(fullText);
                            scrollChat();
                        } else if (event.type === "audio_chunk") {
                            audioQueue.enqueue(event.data);
                        }
                    });
                } catch (err) {
                    if (err.name === 'AbortError') {
                        console.log("Fetch aborted");
                    } else {
                        console.error(err);
                        aiMsgDiv.textContent = "[Error]";
                    }
                }
                this.audioChunks = [];
                stream.getTracks().forEach((t) => t.stop());
                this.isRecording = false;
            };
            this.mediaRecorder.start();
        } catch (err) { setRecordingState(false); this.isRecording = false; }
    }
    // ---------------------------------------------------------------------
    //   Stops microphone recording.
    // ---------------------------------------------------------------------
    stopRecording() { 
        if (this.isRecording) {
            if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
                this.mediaRecorder.stop();
            } else {
                // Cancelled before fully started (e.g. permission prompt)
                this.isRecording = false;
                setRecordingState(false);
            }
        }
    }
}

// ── Conversation Management ──────────────────────────────────────────────────

// ---------------------------------------------------------------------
//   Loads list of conversations from API.
// ---------------------------------------------------------------------
async function loadConversations() {
    const res = await fetch('/api/conversations');
    const convs = await res.json();
    const list = document.getElementById("conversation-list");
    list.innerHTML = "";
    convs.forEach(c => {
        const item = document.createElement("div");
        item.className = `conv-item ${c.id === currentConversationId ? 'active' : ''}`;
        const dateStr = formatConversationDate(c.updated_at || c.created_at);
        item.innerHTML = `
            <div class="conv-info">
                <span class="conv-title">${c.title}</span>
                <span class="conv-date">${dateStr}</span>
            </div>
            <button class="delete-conv-btn" onclick="event.stopPropagation(); deleteConversation(${c.id})">
                <i class="fas fa-trash-alt"></i>
            </button>
        `;
        item.onclick = () => selectConversation(c.id);
        list.appendChild(item);
    });
}

// ---------------------------------------------------------------------
//   Selects and loads a conversation.
// ---------------------------------------------------------------------
async function selectConversation(id) {
    // Ensure id is a number for consistent comparison
    const targetId = Number(id);
    if (currentConversationId === targetId) return;

    console.log(`[UI] Loading conversation: ${targetId}`);
    currentConversationId = targetId;

    // Clear chat window and show loading state
    chatWindow().innerHTML = `
        <div class="message-wrap ai-wrap">
            <div class="message ai-msg">⏳ Synchronizing data stream...</div>
        </div>
    `;

    try {
        // Load messages
        const res = await fetch(`/api/conversations/${targetId}`);
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);

        const messages = await res.json();
        chatWindow().innerHTML = ""; // Clear loader

        if (messages.length === 0) {
            chatWindow().innerHTML = `<div class="message-wrap ai-wrap"><div class="message ai-msg">No messages found.</div></div>`;
        }

        messages.forEach(m => {
            const bubble = addBubble(m.role, "", m.timestamp);
            bubble.innerHTML = marked.parse(m.content);
        });

        loadConversations();
        scrollChat();

        // Close sidebar on mobile after selection
        if (window.innerWidth <= 992) {
            toggleSidebar(false);
        }
    } catch (err) {
        console.error("Failed to load conversation:", err);
        chatWindow().innerHTML = `<div class="message-wrap ai-wrap"><div class="message ai-msg">[ERROR] Failed to load mission history: ${err.message}</div></div>`;
    }
}

// ---------------------------------------------------------------------
//   Auto-generates title for new conversation.
// ---------------------------------------------------------------------
async function autoTitleConversation(id, firstMessage) {
    // Take first 5 words, strip special chars
    const title = firstMessage.split(/\s+/).slice(0, 5).join(" ").replace(/[#*`]/g, "").trim() + (firstMessage.split(/\s+/).length > 5 ? "..." : "");
    if (!title) return;

    await fetch(`/api/conversations/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title })
    });
    loadConversations();
}

// ---------------------------------------------------------------------
//   Creates a new conversation.
// ---------------------------------------------------------------------
async function createConversation(title) {
    const res = await fetch('/api/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title })
    });
    const data = await res.json();
    currentConversationId = data.id;
    loadConversations();
    return data.id;
}

// ---------------------------------------------------------------------
//   Deletes a conversation.
// ---------------------------------------------------------------------
async function deleteConversation(id) {
    if (!confirm("Are you sure you want to delete this mission?")) return;
    await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
    if (currentConversationId === id) {
        currentConversationId = null;
        chatWindow().innerHTML = `
            <div class="message-wrap ai-wrap">
                <div class="message ai-msg">Conversation deleted. Start a new one to continue.</div>
            </div>
        `;
    }
    loadConversations();
}

// ── Settings & Voice Management ──────────────────────────────────────────────

// ---------------------------------------------------------------------
//   Loads settings (Voices, STT/TTS State).
// ---------------------------------------------------------------------
async function loadSettings() {
    // Load Voices
    loadVoices();
    
    try {
        const sttRes = await fetch('/api/settings/stt');
        const sttData = await sttRes.json();
        isSTTEnabled = sttData.enabled;
        
        const ttsRes = await fetch('/api/settings/tts');
        const ttsData = await ttsRes.json();
        
        injectSettingsUI(sttData.enabled, ttsData.enabled);
    } catch (e) {
        console.error("Failed to load settings", e);
    }
}

// ---------------------------------------------------------------------
//   Injects Settings UI elements.
// ---------------------------------------------------------------------
function injectSettingsUI(sttEnabled, ttsEnabled) {
    const voiceSelect = document.getElementById("voice-select");
    if (!voiceSelect) return;
    
    // Prevent duplicate injection
    if (document.getElementById("stt-toggle-wrap")) return;

    const container = document.createElement("div");
    container.className = "system-status-box";
    container.style.marginTop = "20px";
    container.style.marginBottom = "20px";
    container.style.color = "var(--text-primary, #fff)";

    const createToggle = (id, label, checked, endpoint) => {
        const wrap = document.createElement("div");
        wrap.id = id + "-wrap";
        wrap.style.display = "flex";
        wrap.style.justifyContent = "space-between";
        wrap.style.alignItems = "center";
        wrap.style.marginBottom = "12px";

        wrap.innerHTML = `
            <span class="section-label">${label}</span>
            <input type="checkbox" id="${id}" class="status-indicator" ${checked ? "checked" : ""} style="transform: scale(1.2); cursor: pointer;">
        `;

        // Bind event
        wrap.querySelector("input").addEventListener("change", async (e) => {
            if (id === "stt-toggle") isSTTEnabled = e.target.checked;
            await fetch(endpoint, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({enabled: e.target.checked})
            });
        });

        return wrap;
    };

    container.appendChild(createToggle("stt-toggle", "Microphone (STT)", sttEnabled, "/api/settings/stt"));
    container.appendChild(createToggle("tts-toggle", "Voice (TTS)", ttsEnabled, "/api/settings/tts"));

    // Insert before the wrapper (voiceSelect.parentElement) to avoid breaking layout
    voiceSelect.parentElement.parentElement.insertBefore(container, voiceSelect.parentElement);
}

// ---------------------------------------------------------------------
//   Loads available voices into dropdown.
// ---------------------------------------------------------------------
async function loadVoices() {
    const voiceSelect = document.getElementById("voice-select");
    if (!voiceSelect) return;

    try {
        const res = await fetch('/api/tts/voices');
        const data = await res.json();

        voiceSelect.innerHTML = "";
        data.voices.forEach(v => {
            const opt = document.createElement("option");
            opt.value = v;
            opt.textContent = v;
            if (v === data.current) opt.selected = true;
            voiceSelect.appendChild(opt);
        });

        console.log(`[Settings] Loaded ${data.voices.length} voices.`);
    } catch (err) {
        console.error("Failed to load voices:", err);
    }
}

// ---------------------------------------------------------------------
//   Sets the active voice.
// ---------------------------------------------------------------------
async function setVoice(voiceName) {
    try {
        const res = await fetch('/api/tts/voice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ voice: voiceName })
        });
        const data = await res.json();
        if (data.status === 'success') {
            console.log(`[Settings] Voice switched to: ${voiceName}`);
        }
    } catch (err) {
        console.error("Failed to set voice:", err);
    }
}

// ---------------------------------------------------------------------
//   Toggles Settings Sidebar visibility.
// ---------------------------------------------------------------------
function toggleSettings(show) {
    const sidebar = document.getElementById("settings-sidebar");
    if (sidebar) {
        if (show) sidebar.classList.add('active');
        else sidebar.classList.remove('active');
    }
}

// ---------------------------------------------------------------------
//   Toggles Main Sidebar visibility.
// ---------------------------------------------------------------------
function toggleSidebar(show) {
    const sidebar = document.querySelector(".sidebar");
    if (sidebar) {
        if (show) sidebar.classList.add('active');
        else sidebar.classList.remove('active');
    }
}

// ── Bootstrap ────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    // Marked.js configuration
    marked.setOptions({ breaks: true, gfm: true });

    // Recorder instance
    const recorder = new Recorder();

    // DOM elements
    const textInput = document.getElementById("text-input");
    const button = document.getElementById("send-btn");
    const pBtn = document.getElementById("pause-resume-btn");
    const sBtn = document.getElementById("stop-btn");
    const nBtn = document.getElementById("new-chat-btn");

    // Load initial list
    loadConversations();

    // New Chat button
    if (nBtn) {
        nBtn.addEventListener("click", () => {
            if (window.innerWidth <= 992) toggleSidebar(false);
            currentConversationId = null;
            chatWindow().innerHTML = `
                <div class="message-wrap ai-wrap">
                    <div class="message ai-msg">
                        <span style="color: var(--accent-nova); font-weight: 800; font-size: 0.8rem; letter-spacing: 0.2em;">[NEW MISSION]</span><br>
                        Awaiting your command. How shall we proceed?
                    </div>
                </div>
            `;
            loadConversations();
        });
    }

    // Pause/Resume button
    if (pBtn) {
        pBtn.addEventListener("click", () => {
            if (audioQueue.isPaused) {
                audioQueue.resume();
                pBtn.innerHTML = '<i class="fas fa-pause"></i>';
                pBtn.classList.remove('active');
            } else if (audioQueue.pause()) {
                pBtn.innerHTML = '<i class="fas fa-play"></i>';
                pBtn.classList.add('active');
            }
        });
    }

    // Stop button
    if (sBtn) {
        sBtn.addEventListener("click", () => {
            audioQueue.stop();
            if (pBtn) {
                pBtn.innerHTML = '<i class="fas fa-pause"></i>';
                pBtn.classList.remove('active');
            }
        });
    }

    // Mobile Sidebar Toggle
    const menuToggle = document.getElementById("menu-toggle");
    const closeSidebar = document.getElementById("close-sidebar");

    if (menuToggle) {
        menuToggle.addEventListener("click", () => {
            const sidebar = document.querySelector(".sidebar");
            const isOpen = sidebar.classList.contains("active");
            toggleSidebar(!isOpen);
        });
    }

    if (closeSidebar) {
        closeSidebar.addEventListener("click", () => toggleSidebar(false));
    }

    // Settings Sidebar Handlers
    const sBtnToggle = document.getElementById("settings-btn");
    const sSidebarClose = document.getElementById("close-settings");

    if (sBtnToggle) sBtnToggle.addEventListener("click", () => toggleSettings(true));
    if (sSidebarClose) sSidebarClose.addEventListener("click", () => toggleSettings(false));

    // Voice Selection
    const voiceSelect = document.getElementById("voice-select");
    if (voiceSelect) {
        voiceSelect.addEventListener("change", (e) => setVoice(e.target.value));
    }
    // Ctrl + Space to record
    document.addEventListener("keydown", (e) => {
        if (e.ctrlKey && e.code === "Space") { e.preventDefault(); recorder.startRecording(); }
    });

    // Ctrl + Space to stop
    document.addEventListener("keyup", (e) => { if (e.code === "Space") recorder.stopRecording(); });

    // Send button
    if (button) {
        button.addEventListener("click", (e) => {
            e.preventDefault();
            const text = textInput.value.trim();
            if (text) { textInput.value = ""; sendTextPrompt(text); }
        });
    }

    // Enter key to send
    if (textInput) {
        textInput.addEventListener("keydown", (e) => { if (e.code === "Enter") { e.preventDefault(); button.click(); } });
    }

    // Voice Trigger Button
    const voiceTrigger = document.getElementById("voice-trigger");
    if (voiceTrigger) {
        // Use Pointer events for unified input (mouse, touch, pen).
        voiceTrigger.style.touchAction = 'none'; // Prevent scrolling/zooming on this element

        const handleStart = (startEvent) => {
            // Only respond to the primary pointer and not if already recording.
            if (!startEvent.isPrimary || recorder.isRecording) return;
            startEvent.preventDefault();
            recorder.startRecording();

            // This handler will be attached to the window to catch the end event anywhere.
            const handleStop = (stopEvent) => {
                // Ensure we're stopping for the same pointer that started the action.
                if (stopEvent.pointerId !== startEvent.pointerId) return;

                recorder.stopRecording();

                // IMPORTANT: Clean up the global listeners to prevent memory leaks.
                window.removeEventListener('pointerup', handleStop);
                window.removeEventListener('pointercancel', handleStop);
            };

            window.addEventListener('pointerup', handleStop);
            window.addEventListener('pointercancel', handleStop);
        };

        voiceTrigger.addEventListener("pointerdown", handleStart);
        voiceTrigger.addEventListener("contextmenu", (e) => e.preventDefault());
    }

    // Initial Settings Load (Always run to sync STT state)
    loadSettings();
});
