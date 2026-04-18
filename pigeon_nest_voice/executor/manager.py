"""执行管理器 — 路由任务到正确的执行器。

职责:
- 维护执行器注册表
- 根据 task.executor_type / task.action 找到合适的执行器
- 统一执行入口，供调度器调用
"""

import logging
from typing import Any

from pigeon_nest_voice.dispatcher.task import Task
from pigeon_nest_voice.executor.base import BaseActionExecutor, ActionResult

logger = logging.getLogger(__name__)


class ExecutionManager:
    """执行管理器 — 调度器与执行器之间的桥梁。"""

    def __init__(self):
        # executor_type → executor 实例
        self._executors: dict[str, BaseActionExecutor] = {}
        # action → executor_type 映射（动作路由表）
        self._action_routes: dict[str, str] = {}

    def register_executor(self, executor: BaseActionExecutor):
        """注册执行器。"""
        self._executors[executor.executor_type] = executor
        for action in executor.supported_actions:
            self._action_routes[action] = executor.executor_type
        logger.info("注册执行器: %s (type=%s, actions=%s)",
                    executor.name, executor.executor_type, executor.supported_actions)

    def get_executor(self, task: Task) -> BaseActionExecutor | None:
        """根据任务找到合适的执行器。

        优先级: task.executor_type > action 路由表
        """
        # 显式指定了执行器类型
        if task.executor_type:
            return self._executors.get(task.executor_type)

        # 通过 action 路由
        executor_type = self._action_routes.get(task.action)
        if executor_type:
            return self._executors.get(executor_type)

        return None

    async def execute(self, task: Task) -> Any:
        """执行任务。

        Returns:
            执行器返回的 ActionResult
        Raises:
            ValueError: 找不到合适的执行器
        """
        executor = self.get_executor(task)
        if not executor:
            raise ValueError(f"找不到能处理 action='{task.action}' 的执行器")

        logger.info("执行任务: %s → 执行器 %s", task.task_id, executor.name)
        result = await executor.execute(task)

        if isinstance(result, ActionResult):
            if not result.success:
                raise RuntimeError(f"执行失败: {result.message}")
            return result
        return result

    async def emergency_stop_all(self):
        """紧急停止：通知所有执行器取消操作。"""
        logger.critical("执行管理器: 紧急停止所有执行器")
        for executor in self._executors.values():
            try:
                # 对于有设备连接的执行器，发送紧急停止
                if hasattr(executor, "emergency_stop"):
                    await executor.emergency_stop()
            except Exception:
                logger.exception("执行器 %s 紧急停止失败", executor.name)

    def list_executors(self) -> list[dict]:
        return [
            {
                "name": e.name,
                "type": e.executor_type,
                "actions": e.supported_actions,
            }
            for e in self._executors.values()
        ]

    def list_routes(self) -> dict[str, str]:
        return dict(self._action_routes)
