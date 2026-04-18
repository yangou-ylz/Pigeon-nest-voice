"""TTS (Text-to-Speech) 服务抽象基类。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TTSResult:
    """语音合成结果。"""
    audio_bytes: bytes
    content_type: str  # e.g. "audio/mpeg"


class BaseTTS(ABC):
    """语音合成基类。"""

    @abstractmethod
    async def synthesize(self, text: str) -> TTSResult:
        """将文本合成为语音。

        Args:
            text: 要合成的文本

        Returns:
            TTSResult 包含音频字节和 MIME 类型。
        """
        ...
