/**
 * Pigeon Nest Voice — 前端交互逻辑（文本 + 语音）
 */

const chatArea = document.getElementById("chatArea");
const textInput = document.getElementById("textInput");
const sendBtn = document.getElementById("sendBtn");
const micBtn = document.getElementById("micBtn");
const voiceStatus = document.getElementById("voiceStatus");
const voiceStatusText = document.getElementById("voiceStatusText");
const newChatBtn = document.getElementById("newChatBtn");
const sessionInfo = document.getElementById("sessionInfo");

let sessionId = localStorage.getItem("pnv_session_id") || null;
let turnCount = 0;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

// ── 会话管理 ──

/** 保存 sessionId 到 localStorage */
function saveSession(sid) {
    sessionId = sid;
    if (sid) {
        localStorage.setItem("pnv_session_id", sid);
    } else {
        localStorage.removeItem("pnv_session_id");
    }
    updateSessionInfo();
}

/** 更新会话信息显示 */
function updateSessionInfo() {
    if (sessionId) {
        sessionInfo.textContent = `💬 ${turnCount} 轮 · ${sessionId.slice(0, 6)}`;
        sessionInfo.title = `会话: ${sessionId}\n对话轮数: ${turnCount}`;
    } else {
        sessionInfo.textContent = "";
    }
}

/** 开始新对话 */
function startNewChat() {
    saveSession(null);
    turnCount = 0;
    chatArea.innerHTML = "";
    appendMessage("assistant", "你好！我是鸽子窝语音助手，有什么可以帮你的？");
    textInput.focus();
}

newChatBtn.addEventListener("click", startNewChat);

// 页面加载时如有会话，尝试恢复
if (sessionId) {
    fetch(`/api/sessions/${sessionId}`)
        .then(r => r.ok ? r.json() : null)
        .then(data => {
            if (data && data.messages && data.messages.length > 0) {
                turnCount = data.turn_count || 0;
                chatArea.innerHTML = "";  // 清掉默认欢迎语
                // 恢复最近的消息（最多显示最近20轮）
                const msgs = data.messages.slice(-40);
                for (const m of msgs) {
                    appendMessage(m.role === "user" ? "user" : "assistant", m.content);
                }
                if (data.has_summary) {
                    // 在顶部显示摘要提示
                    const hint = document.createElement("div");
                    hint.className = "message system-hint";
                    hint.innerHTML = '<div class="bubble system-bubble">📋 已加载历史摘要，可继续之前的对话</div>';
                    chatArea.insertBefore(hint, chatArea.firstChild);
                }
                updateSessionInfo();
            } else {
                // 会话不存在或为空，重置
                saveSession(null);
            }
        })
        .catch(() => {
            // 获取失败，忽略
            saveSession(null);
        });
}

// ── 消息气泡 ──

/** 向对话区域追加一条消息气泡，返回 bubble 元素 */
function appendMessage(role, text) {
    const msg = document.createElement("div");
    msg.className = `message ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    msg.appendChild(bubble);

    // 为助手消息添加朗读按钮
    if (role === "assistant") {
        const speakBtn = document.createElement("button");
        speakBtn.className = "speak-btn";
        speakBtn.textContent = "🔊";
        speakBtn.title = "朗读";
        speakBtn.addEventListener("click", () => speakText(text, speakBtn));
        msg.appendChild(speakBtn);
    }

    chatArea.appendChild(msg);
    chatArea.scrollTop = chatArea.scrollHeight;
    return bubble;
}

/** 设置发送按钮的启用/禁用状态 */
function setLoading(loading) {
    sendBtn.disabled = loading;
    textInput.disabled = loading;
    micBtn.disabled = loading;
    sendBtn.textContent = loading ? "思考中..." : "发送";
}

// ── 文本对话 ──

async function sendMessage() {
    const text = textInput.value.trim();
    if (!text) return;

    appendMessage("user", text);
    textInput.value = "";
    setLoading(true);

    try {
        const resp = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: text,
                session_id: sessionId,
            }),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const data = await resp.json();
        saveSession(data.session_id);
        turnCount++;
        updateSessionInfo();
        appendMessage("assistant", data.reply);
    } catch (e) {
        appendMessage("assistant", `⚠️ 出错了: ${e.message}`);
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

// ── 语音录制 ──

micBtn.addEventListener("click", toggleRecording);

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
            const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
            await sendVoice(audioBlob);
        };

        mediaRecorder.start();
        isRecording = true;
        micBtn.classList.add("recording");
        micBtn.textContent = "⏹️";
        voiceStatus.classList.add("visible");
        voiceStatusText.textContent = "正在录音...";
    } catch (e) {
        appendMessage("assistant", `⚠️ 无法访问麦克风: ${e.message}`);
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
    }
    isRecording = false;
    micBtn.classList.remove("recording");
    micBtn.textContent = "🎙️";
    voiceStatus.classList.remove("visible");
}

// ── 语音发送 ──

async function sendVoice(audioBlob) {
    const userBubble = appendMessage("user", "🎤 正在识别...");
    setLoading(true);
    voiceStatusText.textContent = "正在识别...";
    voiceStatus.classList.add("visible");

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
        saveSession(data.session_id);
        turnCount++;
        updateSessionInfo();

        // 更新用户气泡显示识别文字
        if (data.recognized_text) {
            userBubble.textContent = `🎤 ${data.recognized_text}`;
        } else {
            userBubble.textContent = "🎤 (未识别)";
        }

        appendMessage("assistant", data.reply);

        // 自动播放语音回复
        if (data.audio_base64) {
            playAudio(data.audio_base64, data.audio_content_type);
        }
    } catch (e) {
        userBubble.textContent = "🎤 (发送失败)";
        appendMessage("assistant", `⚠️ 语音处理出错: ${e.message}`);
    } finally {
        setLoading(false);
        voiceStatus.classList.remove("visible");
    }
}

// ── 音频播放 ──

function playAudio(base64Data, contentType) {
    const audio = new Audio(`data:${contentType};base64,${base64Data}`);
    audio.play().catch((e) => console.warn("Audio playback failed:", e));
    return audio;
}

// ── 朗读文本 ──

let currentAudio = null;

async function speakText(text, btn) {
    // 如果正在播放，点击则停止
    if (currentAudio && !currentAudio.paused) {
        currentAudio.pause();
        currentAudio = null;
        btn.textContent = "🔊";
        return;
    }

    btn.textContent = "⏳";
    btn.disabled = true;

    try {
        const resp = await fetch("/api/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });

        if (!resp.ok) throw new Error(`TTS 失败: HTTP ${resp.status}`);

        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        currentAudio = new Audio(url);

        btn.textContent = "⏹️";
        btn.disabled = false;

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
        btn.disabled = false;
    }
}

/** 朗读文字（调用 /api/tts） */
async function speakText(text, btn) {
    const originalText = btn.textContent;
    btn.textContent = "⏳";
    btn.disabled = true;

    try {
        const resp = await fetch("/api/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.onended = () => URL.revokeObjectURL(url);
        await audio.play();
    } catch (e) {
        console.warn("TTS playback failed:", e);
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}
