"""LLM 服务抽象基类。所有 LLM 提供者必须继承此类。"""

from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """大语言模型抽象接口。"""

    @abstractmethod
    async def chat(self, messages: list[dict]) -> str:
        """发送对话消息并返回模型回复。

        Args:
            messages: OpenAI 格式的消息列表，例如
                [{"role": "user", "content": "你好"}]

        Returns:
            模型回复的文本内容。
        """

    @abstractmethod
    async def chat_stream(self, messages: list[dict]):
        """流式对话，逐步 yield 文本片段。

        Args:
            messages: OpenAI 格式的消息列表。

        Yields:
            str: 文本片段。
        """
