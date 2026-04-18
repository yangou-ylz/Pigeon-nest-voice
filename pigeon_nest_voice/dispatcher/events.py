"""进程内事件总线 — 发布/订阅模式，解耦跨层通信。

用法:
    bus = EventBus.get_instance()

    # 订阅
    async def on_task_done(data):
        print(data)
    bus.subscribe("task.completed", on_task_done)

    # 发布
    await bus.publish("task.completed", {"task_id": "abc", "result": ...})

    # 支持通配符订阅
    bus.subscribe("task.*", on_any_task_event)
    bus.subscribe("*", on_everything)
"""

import asyncio
import fnmatch
import logging
import threading
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# 事件处理器类型: 接收事件名和数据，返回协程
EventHandler = Callable[[str, Any], Coroutine[Any, Any, None]]


class EventBus:
    """轻量级进程内异步事件总线。

    特性:
    - 支持精确匹配和通配符 (* 匹配任意事件)
    - 异步处理器并发执行
    - 处理器异常不影响其他处理器
    - 线程安全的单例模式
    """

    _instance: "EventBus | None" = None
    _lock = threading.Lock()

    def __init__(self):
        # event_name → list[handler]
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._wildcard_handlers: list[tuple[str, EventHandler]] = []

    @classmethod
    def get_instance(cls) -> "EventBus":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """重置单例（测试用）。"""
        with cls._lock:
            cls._instance = None

    def subscribe(self, event_pattern: str, handler: EventHandler):
        """订阅事件。

        Args:
            event_pattern: 事件名，支持 fnmatch 通配符 (*, ?)
            handler: 异步处理函数 async def handler(event_name, data)
        """
        if "*" in event_pattern or "?" in event_pattern:
            self._wildcard_handlers.append((event_pattern, handler))
            logger.debug("事件总线: 通配符订阅 '%s'", event_pattern)
        else:
            self._handlers[event_pattern].append(handler)
            logger.debug("事件总线: 精确订阅 '%s'", event_pattern)

    def unsubscribe(self, event_pattern: str, handler: EventHandler):
        """取消订阅。"""
        if "*" in event_pattern or "?" in event_pattern:
            self._wildcard_handlers = [
                (p, h) for p, h in self._wildcard_handlers
                if not (p == event_pattern and h is handler)
            ]
        else:
            handlers = self._handlers.get(event_pattern, [])
            self._handlers[event_pattern] = [h for h in handlers if h is not handler]

    async def publish(self, event_name: str, data: Any = None):
        """发布事件，所有匹配的处理器并发执行。

        Args:
            event_name: 事件名 (如 "task.completed", "device.status_changed")
            data: 事件附带数据
        """
        handlers: list[EventHandler] = []

        # 精确匹配
        handlers.extend(self._handlers.get(event_name, []))

        # 通配符匹配
        for pattern, handler in self._wildcard_handlers:
            if fnmatch.fnmatch(event_name, pattern):
                handlers.append(handler)

        if not handlers:
            return

        logger.debug("事件总线: 发布 '%s' → %d 个处理器", event_name, len(handlers))

        # 并发执行所有处理器，单个失败不影响其他
        results = await asyncio.gather(
            *(self._safe_call(h, event_name, data) for h in handlers),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                logger.error("事件处理器异常 [%s]: %s", event_name, r, exc_info=r)

    @staticmethod
    async def _safe_call(handler: EventHandler, event_name: str, data: Any):
        try:
            await handler(event_name, data)
        except Exception as e:
            logger.error("事件处理器 %s 执行失败: %s", handler.__name__, e, exc_info=True)
            raise
