"""基于 edge-tts 的语音合成服务（免费、高质量中文语音）。"""

import io
import logging
import time

import edge_tts

from pigeon_nest_voice.services.tts.base import BaseTTS, TTSResult
from pigeon_nest_voice.config.settings import settings

logger = logging.getLogger(__name__)


class EdgeTTSService(BaseTTS):
    """使用 Microsoft Edge TTS 进行语音合成。"""

    def __init__(self):
        self._voice = settings.edge_tts_voice
        logger.info("Edge TTS 初始化: voice=%s", self._voice)

    async def synthesize(self, text: str) -> TTSResult:
        t0 = time.perf_counter()
        communicate = edge_tts.Communicate(text, self._voice)
        audio_buf = io.BytesIO()

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buf.write(chunk["data"])

        audio_bytes = audio_buf.getvalue()
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("TTS 合成: %d字 → %.1fKB [%.0fms]",
                    len(text), len(audio_bytes) / 1024, elapsed)
        return TTSResult(audio_bytes=audio_bytes, content_type="audio/mpeg")
