/**
 * Pigeon Nest Voice — 高级前端交互
 * 粒子背景 · 波形可视化 · 打字动画 · 主题切换 · 会话管理
 */

// ── DOM ──
const $ = (sel) => document.querySelector(sel);
const chatArea = $("#chatArea");
const textInput = $("#textInput");
const sendBtn = $("#sendBtn");
const micBtn = $("#micBtn");
const newChatBtn = $("#newChatBtn");
const sessionInfo = $("#sessionInfo");
const welcomeScreen = $("#welcomeScreen");
const voiceOverlay = $("#voiceOverlay");
const voiceStatusText = $("#voiceStatusText");
const voiceCancelBtn = $("#voiceCancelBtn");
const waveformCanvas = $("#waveformCanvas");
const particleCanvas = $("#particleCanvas");
const themeToggle = $("#themeToggle");
const sidebarToggle = $("#sidebarToggle");
const sidebar = $("#sidebar");
const toastContainer = $("#toastContainer");

// ── 状态 ──
let sessionId = localStorage.getItem("pnv_session_id") || null;
let turnCount = 0;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let audioContext = null;
let analyser = null;
let waveformAnimId = null;
let currentAudio = null;

// ══════════════════════════════════════
//  粒子背景
// ══════════════════════════════════════
(function initParticles() {
    const ctx = particleCanvas.getContext("2d");
    let w, h, particles = [];
    const COUNT = 50;

    function resize() {
        w = particleCanvas.width = window.innerWidth;
        h = particleCanvas.height = window.innerHeight;
    }

    function createParticle() {
        return {
            x: Math.random() * w,
            y: Math.random() * h,
            r: Math.random() * 1.5 + 0.5,
            dx: (Math.random() - 0.5) * 0.4,
            dy: (Math.random() - 0.5) * 0.4,
            alpha: Math.random() * 0.5 + 0.1,
        };
    }

    function draw() {
        ctx.clearRect(0, 0, w, h);
        const isLight = document.documentElement.dataset.theme === "light";
        const color = isLight ? "0,0,0" : "99,102,241";

        for (const p of particles) {
            p.x += p.dx;
            p.y += p.dy;
            if (p.x < 0 || p.x > w) p.dx *= -1;
            if (p.y < 0 || p.y > h) p.dy *= -1;

            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${color}, ${p.alpha})`;
            ctx.fill();
        }

        // 连线
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 150) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(${color}, ${0.06 * (1 - dist / 150)})`;
                    ctx.stroke();
                }
            }
        }
        requestAnimationFrame(draw);
    }

    resize();
    for (let i = 0; i < COUNT; i++) particles.push(createParticle());
    window.addEventListener("resize", resize);
    draw();
})();

// ══════════════════════════════════════
//  主题切换
// ══════════════════════════════════════
function initTheme() {
    const saved = localStorage.getItem("pnv_theme");
    if (saved) document.documentElement.dataset.theme = saved;
}

themeToggle.addEventListener("click", () => {
    const current = document.documentElement.dataset.theme;
    const next = current === "light" ? "" : "light";
    if (next) {
        document.documentElement.dataset.theme = next;
        localStorage.setItem("pnv_theme", next);
    } else {
        delete document.documentElement.dataset.theme;
        localStorage.removeItem("pnv_theme");
    }
});

initTheme();

// ══════════════════════════════════════
//  侧边栏
// ══════════════════════════════════════
sidebarToggle.addEventListener("click", () => {
    sidebar.classList.toggle("open");
});

// 点击侧栏外关闭（移动端）
document.addEventListener("click", (e) => {
    if (window.innerWidth <= 768 && sidebar.classList.contains("open")) {
        if (!sidebar.contains(e.target) && e.target !== sidebarToggle && !sidebarToggle.contains(e.target)) {
            sidebar.classList.remove("open");
        }
    }
});

// ══════════════════════════════════════
//  Toast 通知
// ══════════════════════════════════════
function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// ══════════════════════════════════════
//  会话管理
// ══════════════════════════════════════
function saveSession(sid) {
    sessionId = sid;
    if (sid) {
        localStorage.setItem("pnv_session_id", sid);
    } else {
        localStorage.removeItem("pnv_session_id");
    }
    updateSessionInfo();
}

function updateSessionInfo() {
    if (sessionId) {
        sessionInfo.textContent = `${turnCount} 轮 · ${sessionId.slice(0, 6)}`;
    } else {
        sessionInfo.textContent = "无活跃会话";
    }
}

function startNewChat() {
    saveSession(null);
    turnCount = 0;
    chatArea.innerHTML = "";
    // 重新插入欢迎屏
    chatArea.innerHTML = `
        <div class="welcome-screen" id="welcomeScreen">
            <div class="welcome-icon">🕊️</div>
            <h2>欢迎使用鸽子窝语音助手</h2>
            <p>输入文字或点击麦克风开始对话</p>
            <div class="quick-actions">
                <button class="quick-btn" data-msg="现在几点了">🕐 现在几点</button>
                <button class="quick-btn" data-msg="今天天气怎么样">🌤️ 查天气</button>
                <button class="quick-btn" data-msg="系统状态">💻 系统状态</button>
            </div>
        </div>`;
    bindQuickActions();
    textInput.focus();
    showToast("已创建新对话", "success");
}

newChatBtn.addEventListener("click", startNewChat);

// 快捷按钮
function bindQuickActions() {
    document.querySelectorAll(".quick-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            textInput.value = btn.dataset.msg;
            sendMessage();
        });
    });
}
bindQuickActions();

// 页面加载恢复会话
if (sessionId) {
    fetch(`/api/sessions/${encodeURIComponent(sessionId)}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
            if (data && data.messages && data.messages.length > 0) {
                turnCount = data.turn_count || 0;
                chatArea.innerHTML = "";
                const msgs = data.messages.slice(-40);
                for (const m of msgs) {
                    appendMessage(m.role === "user" ? "user" : "assistant", m.content);
                }
                if (data.has_summary) {
                    const hint = document.createElement("div");
                    hint.className = "message system-hint";
                    hint.innerHTML = '<div class="bubble system-bubble">📋 已加载历史摘要，可继续对话</div>';
                    chatArea.insertBefore(hint, chatArea.firstChild);
                }
                updateSessionInfo();
            } else {
                saveSession(null);
            }
        })
        .catch(() => saveSession(null));
} else {
    updateSessionInfo();
}

// ══════════════════════════════════════
//  消息渲染
// ══════════════════════════════════════
function hideWelcome() {
    const ws = chatArea.querySelector(".welcome-screen");
    if (ws) ws.remove();
}

function appendMessage(role, text) {
    hideWelcome();

    const msg = document.createElement("div");
    msg.className = `message ${role}`;

    // 头像
    const avatar = document.createElement("div");
    avatar.className = "msg-avatar";
    avatar.textContent = role === "user" ? "👤" : "🕊️";

    // 内容容器
    const content = document.createElement("div");
    content.className = "msg-content";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    content.appendChild(bubble);

    // 助手消息的操作按钮
    if (role === "assistant") {
        const actions = document.createElement("div");
        actions.className = "msg-actions";

        const speakBtn = document.createElement("button");
        speakBtn.className = "msg-action-btn";
        speakBtn.textContent = "🔊";
        speakBtn.title = "朗读";
        speakBtn.addEventListener("click", () => speakText(text, speakBtn));

        const copyBtn = document.createElement("button");
        copyBtn.className = "msg-action-btn";
        copyBtn.textContent = "📋";
        copyBtn.title = "复制";
        copyBtn.addEventListener("click", () => {
            navigator.clipboard.writeText(text).then(() => {
                copyBtn.textContent = "✅";
                setTimeout(() => (copyBtn.textContent = "📋"), 1500);
            });
        });

        actions.appendChild(speakBtn);
        actions.appendChild(copyBtn);
        content.appendChild(actions);
    }

    msg.appendChild(avatar);
    msg.appendChild(content);
    chatArea.appendChild(msg);
    chatArea.scrollTop = chatArea.scrollHeight;
    return bubble;
}

/** 显示打字指示器 */
function showTyping() {
    hideWelcome();
    const msg = document.createElement("div");
    msg.className = "message assistant";
    msg.id = "typingMsg";

    const avatar = document.createElement("div");
    avatar.className = "msg-avatar";
    avatar.textContent = "🕊️";

    const content = document.createElement("div");
    content.className = "msg-content";

    const bubble = document.createElement("div");
    bubble.className = "bubble typing-indicator";
    bubble.innerHTML = "<span></span><span></span><span></span>";
    content.appendChild(bubble);

    msg.appendChild(avatar);
    msg.appendChild(content);
    chatArea.appendChild(msg);
    chatArea.scrollTop = chatArea.scrollHeight;
}

function hideTyping() {
    const t = document.getElementById("typingMsg");
    if (t) t.remove();
}

function setLoading(loading) {
    sendBtn.disabled = loading;
    textInput.disabled = loading;
    micBtn.disabled = loading;
}

// ══════════════════════════════════════
//  文本对话
// ══════════════════════════════════════
async function sendMessage() {
    const text = textInput.value.trim();
    if (!text) return;

    appendMessage("user", text);
    textInput.value = "";
    autoResizeInput();
    setLoading(true);
    showTyping();

    try {
        const resp = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text, session_id: sessionId }),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const data = await resp.json();
        hideTyping();
        saveSession(data.session_id);
        turnCount++;
        updateSessionInfo();
        appendMessage("assistant", data.reply);
    } catch (e) {
        hideTyping();
        appendMessage("assistant", `⚠️ 出错了: ${e.message}`);
        showToast(`请求失败: ${e.message}`, "error");
    } finally {
        setLoading(false);
        textInput.focus();
    }
}

sendBtn.addEventListener("click", sendMessage);
textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// 自动调节 textarea 高度
function autoResizeInput() {
    textInput.style.height = "auto";
    textInput.style.height = Math.min(textInput.scrollHeight, 120) + "px";
}
textInput.addEventListener("input", autoResizeInput);

// ══════════════════════════════════════
//  语音录制 + 波形可视化
// ══════════════════════════════════════
micBtn.addEventListener("click", toggleRecording);
voiceCancelBtn.addEventListener("click", cancelRecording);

async function toggleRecording() {
    if (isRecording) {
        stopRecording();
    } else {
        await startRecording();
    }
}

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
            ? "audio/webm;codecs=opus"
            : "audio/webm";
        mediaRecorder = new MediaRecorder(stream, { mimeType });
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach((t) => t.stop());
            stopWaveform();
            voiceOverlay.classList.remove("visible");
            if (audioChunks.length > 0) {
                const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
                await sendVoice(audioBlob);
            }
        };

        mediaRecorder.start();
        isRecording = true;
        micBtn.classList.add("recording");
        voiceOverlay.classList.add("visible");
        voiceStatusText.textContent = "正在录音...";

        // 波形可视化
        startWaveform(stream);
    } catch (e) {
        appendMessage("assistant", `⚠️ 无法访问麦克风: ${e.message}`);
        showToast("麦克风访问失败", "error");
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
    }
    isRecording = false;
    micBtn.classList.remove("recording");
}

function cancelRecording() {
    audioChunks = [];  // 清空，onstop 里就不会发送
    stopRecording();
    voiceOverlay.classList.remove("visible");
    showToast("录音已取消", "info");
}

// 波形可视化
function startWaveform(stream) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioContext.createAnalyser();
    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);
    analyser.fftSize = 256;

    const ctx = waveformCanvas.getContext("2d");
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function draw() {
        waveformAnimId = requestAnimationFrame(draw);
        analyser.getByteFrequencyData(dataArray);

        const w = waveformCanvas.width;
        const h = waveformCanvas.height;
        ctx.clearRect(0, 0, w, h);

        const barWidth = (w / bufferLength) * 2;
        let x = 0;

        for (let i = 0; i < bufferLength; i++) {
            const v = dataArray[i] / 255;
            const barHeight = v * h * 0.8;

            const gradient = ctx.createLinearGradient(0, h, 0, h - barHeight);
            gradient.addColorStop(0, "rgba(99, 102, 241, 0.6)");
            gradient.addColorStop(1, "rgba(236, 72, 153, 0.8)");
            ctx.fillStyle = gradient;

            const r = 2;
            ctx.beginPath();
            ctx.roundRect(x, h - barHeight, barWidth - 1, barHeight, r);
            ctx.fill();
            x += barWidth;
        }
    }
    draw();
}

function stopWaveform() {
    if (waveformAnimId) cancelAnimationFrame(waveformAnimId);
    if (audioContext) audioContext.close().catch(() => {});
    audioContext = null;
    analyser = null;
}

// ── 语音发送 ──
async function sendVoice(audioBlob) {
    const userBubble = appendMessage("user", "🎤 正在识别...");
    setLoading(true);
    showTyping();

    const formData = new FormData();
    formData.append("audio", audioBlob, "recording.webm");
    if (sessionId) formData.append("session_id", sessionId);

    try {
        const resp = await fetch("/api/voice", {
            method: "POST",
            body: formData,
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const data = await resp.json();
        hideTyping();
        saveSession(data.session_id);
        turnCount++;
        updateSessionInfo();

        userBubble.textContent = data.recognized_text
            ? `🎤 ${data.recognized_text}`
            : "🎤 (未识别)";

        appendMessage("assistant", data.reply);

        if (data.audio_base64) {
            playAudio(data.audio_base64, data.audio_content_type);
        }
    } catch (e) {
        hideTyping();
        userBubble.textContent = "🎤 (发送失败)";
        appendMessage("assistant", `⚠️ 语音处理出错: ${e.message}`);
        showToast("语音处理失败", "error");
    } finally {
        setLoading(false);
    }
}

// ── 音频播放 ──
function playAudio(base64Data, contentType) {
    const audio = new Audio(`data:${contentType};base64,${base64Data}`);
    audio.play().catch((e) => console.warn("Audio playback failed:", e));
    return audio;
}

// ── 朗读 ──
async function speakText(text, btn) {
    if (currentAudio && !currentAudio.paused) {
        currentAudio.pause();
        currentAudio = null;
        btn.textContent = "🔊";
        return;
    }

    btn.textContent = "⏳";
    try {
        const resp = await fetch("/api/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        currentAudio = new Audio(url);
        btn.textContent = "⏹️";

        currentAudio.addEventListener("ended", () => {
            btn.textContent = "🔊";
            currentAudio = null;
            URL.revokeObjectURL(url);
        });

        currentAudio.addEventListener("error", () => {
            btn.textContent = "🔊";
            currentAudio = null;
            URL.revokeObjectURL(url);
        });

        await currentAudio.play();
    } catch (e) {
        console.warn("TTS error:", e);
        btn.textContent = "🔊";
        showToast("朗读失败", "error");
    }
}
