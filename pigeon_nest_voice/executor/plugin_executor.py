"""插件桥接执行器 — 将现有插件系统桥接到新的执行层。"""

import logging

from pigeon_nest_voice.dispatcher.task import Task
from pigeon_nest_voice.executor.base import BaseActionExecutor, ActionResult
from pigeon_nest_voice.plugins.manager import PluginManager

logger = logging.getLogger(__name__)


class PluginActionExecutor(BaseActionExecutor):
    """插件桥接执行器。

    让现有的 PluginManager 中的插件也能通过调度器执行，
    实现新旧系统无缝衔接。
    """

    name = "plugin_executor"
    executor_type = "plugin"

    def __init__(self, plugin_manager: PluginManager):
        self._plugin_mgr = plugin_manager
        self.supported_actions = list(plugin_manager._action_map.keys()) if hasattr(plugin_manager, '_action_map') else []

    async def execute(self, task: Task) -> ActionResult:
        if not self._plugin_mgr.has_action(task.action):
            return ActionResult(
                success=False,
                message=f"插件不支持动作: {task.action}",
            )

        result = await self._plugin_mgr.execute(task.action, task.params)
        if result is None:
            return ActionResult(success=False, message="插件返回空结果")

        return ActionResult(
            success=result.success,
            message=result.message,
            data=result.data,
        )

    async def cancel(self, task: Task):
        # 插件通常是短操作，不支持取消
        pass
