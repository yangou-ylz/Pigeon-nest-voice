"""线程池管理器 — 统一管理异步任务调度。"""

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable

from pigeon_nest_voice.config.settings import settings

logger = logging.getLogger(__name__)


class ThreadPoolManager:
    """全局线程池，用于将阻塞/CPU密集操作卸载到线程中执行。

    使用场景:
    - 同步 SDK 调用（如某些 STT/TTS 库）
    - CPU 密集的规则匹配/文本处理
    - 同步的外部 HTTP 请求

    不需要线程池的场景:
    - httpx.AsyncClient 的异步调用（如 DeepSeek LLM）
    - 原生 async 的库
    """

    _instance: "ThreadPoolManager | None" = None
    _lock = threading.Lock()

    def __init__(self, max_workers: int | None = None):
        self._max_workers = max_workers or settings.thread_pool_max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="pnv-worker",
        )
        self._shutdown = False
        logger.info("ThreadPoolManager 初始化: max_workers=%d", self._max_workers)

    @classmethod
    def get_instance(cls) -> "ThreadPoolManager":
        """获取单例实例（线程安全）。"""
        if cls._instance is None or cls._instance._shutdown:
            with cls._lock:
                if cls._instance is None or cls._instance._shutdown:
                    cls._instance = cls()
        return cls._instance

    async def run_in_thread(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """在线程池中执行同步函数，返回 awaitable 结果。

        用法:
            result = await pool.run_in_thread(blocking_func, arg1, arg2)
        """
        if self._shutdown:
            raise RuntimeError("ThreadPoolManager 已关闭")
        loop = asyncio.get_running_loop()
        if kwargs:
            func = partial(func, **kwargs)
        return await loop.run_in_executor(self._executor, func, *args)

    @property
    def max_workers(self) -> int:
        return self._max_workers

    def shutdown(self, wait: bool = True):
        if self._shutdown:
            return
        self._shutdown = True
        logger.info("ThreadPoolManager 关闭中...")
        self._executor.shutdown(wait=wait)
        logger.info("ThreadPoolManager 已关闭")
