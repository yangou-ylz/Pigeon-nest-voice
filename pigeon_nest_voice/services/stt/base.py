"""STT (Speech-to-Text) 服务抽象基类。"""

from abc import ABC, abstractmethod


class BaseSTT(ABC):
    """语音识别基类。"""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        """将音频数据转换为文本。

        Args:
            audio_bytes: 原始音频字节 (支持 webm/wav/mp3 等格式)

        Returns:
            识别出的文本，识别失败返回空字符串。
        """
        ...
