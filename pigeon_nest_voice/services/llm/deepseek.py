"""DeepSeek LLM 适配器。"""

import logging
import time

import httpx
from pigeon_nest_voice.services.llm.base import BaseLLM
from pigeon_nest_voice.config.settings import settings

logger = logging.getLogger(__name__)


class DeepSeekLLM(BaseLLM):
    """DeepSeek API 实现。"""

    def __init__(self):
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url
        self.model = settings.deepseek_model
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        logger.info("DeepSeek LLM 初始化: model=%s, base_url=%s", self.model, self.base_url)

    async def chat(self, messages: list[dict]) -> str:
        logger.debug("LLM请求: %d条消息, 最后一条=%s",
                      len(messages), messages[-1]["content"][:80] if messages else "")
        t0 = time.perf_counter()
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
            }
            resp = await self._client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("LLM响应: %d字 [%.0fms] tokens(in=%s, out=%s)",
                        len(reply), elapsed,
                        usage.get("prompt_tokens", "?"),
                        usage.get("completion_tokens", "?"))
            return reply
        except Exception:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.exception("LLM请求失败 [%.0fms]", elapsed)
            raise

    async def chat_stream(self, messages: list[dict]):
        logger.debug("LLM流式请求: %d条消息", len(messages))
        t0 = time.perf_counter()
        total_chars = 0
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": True,
            }
            async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:]
                    if chunk.strip() == "[DONE]":
                        break
                    import json
                    data = json.loads(chunk)
                    delta = data["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        total_chars += len(content)
                        yield content
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("LLM流式完成: %d字 [%.0fms]", total_chars, elapsed)
        except Exception:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.exception("LLM流式请求失败 [%.0fms]", elapsed)
            raise

    async def close(self):
        await self._client.aclose()
