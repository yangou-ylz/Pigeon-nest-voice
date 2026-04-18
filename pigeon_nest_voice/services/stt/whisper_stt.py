"""基于 faster-whisper 的本地语音识别服务。"""

import asyncio
import logging
import tempfile
import threading
import time

from opencc import OpenCC

from pigeon_nest_voice.services.stt.base import BaseSTT
from pigeon_nest_voice.config.settings import settings
from pigeon_nest_voice.core.thread_pool import ThreadPoolManager

logger = logging.getLogger(__name__)

# 繁体→简体转换器（全局复用）
_t2s = OpenCC("t2s")

# 引导 Whisper 输出简体中文的提示词
_INITIAL_PROMPT = "以下是普通话的句子，使用简体中文。"


class WhisperSTT(BaseSTT):
    """使用 faster-whisper (CTranslate2) 进行本地语音识别。

    模型采用延迟加载: 首次调用 transcribe() 时才下载/加载模型,
    避免阻塞服务启动。
    """

    def __init__(self):
        self._model = None
        self._lock = threading.Lock()
        logger.info("WhisperSTT 初始化 (模型将在首次使用时加载)")

    def _ensure_model(self):
        """双重检查锁，确保模型只加载一次。"""
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            from faster_whisper import WhisperModel
            model_size = settings.whisper_model
            device = settings.whisper_device
            compute_type = settings.whisper_compute_type
            logger.info(
                "加载 Whisper 模型: %s (device=%s, compute=%s)",
                model_size, device, compute_type,
            )
            t0 = time.perf_counter()
            self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("Whisper 模型加载完成 [%.0fms]", elapsed)

    def _transcribe_sync(self, audio_bytes: bytes) -> str:
        """同步识别（在线程池中执行）。"""
        self._ensure_model()
        logger.debug("STT 开始识别: 音频 %.1fKB", len(audio_bytes) / 1024)
        t0 = time.perf_counter()
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as f:
            f.write(audio_bytes)
            f.flush()
            segments, info = self._model.transcribe(
                f.name,
                language="zh",
                beam_size=5,
                vad_filter=True,
                initial_prompt=_INITIAL_PROMPT,
                condition_on_previous_text=False,
            )
            text = "".join(seg.text for seg in segments).strip()

        # 强制繁体→简体转换
        text = _t2s.convert(text)

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "STT 识别: '%s' (lang=%s, prob=%.2f) [%.0fms]",
            text, info.language, info.language_probability, elapsed,
        )
        return text

    async def transcribe(self, audio_bytes: bytes) -> str:
        loop = asyncio.get_event_loop()
        pool = ThreadPoolManager.get_instance()
        return await loop.run_in_executor(pool._executor, self._transcribe_sync, audio_bytes)
