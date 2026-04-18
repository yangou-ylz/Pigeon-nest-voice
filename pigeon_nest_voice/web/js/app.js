/**
 * Pigeon Nest Voice — 前端交互逻辑（文本 + 语音）
 */

const chatArea = document.getElementById("chatArea");
const textInput = document.getElementById("textInput");
const sendBtn = document.getElementById("sendBtn");
const micBtn = document.getElementById("micBtn");
const voiceStatus = document.getElementById("voiceStatus");
const voiceStatusText = document.getElementById("voiceStatusText");

let sessionId = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

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
        sessionId = data.session_id;
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
        sessionId = data.session_id;

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
