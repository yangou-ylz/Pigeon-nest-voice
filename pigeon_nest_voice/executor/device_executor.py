"""设备动作执行器 — 将任务转发到设备管理器执行。"""

import logging
from typing import Any

from pigeon_nest_voice.dispatcher.task import Task
from pigeon_nest_voice.executor.base import BaseActionExecutor, ActionResult

logger = logging.getLogger(__name__)


class DeviceActionExecutor(BaseActionExecutor):
    """设备控制执行器。

    桥接调度层和设备层：从 task 中提取目标设备和参数，
    调用 DeviceManager 执行实际操作。
    """

    name = "device_executor"
    executor_type = "device"
    supported_actions = [
        "move_arm", "set_position", "grab", "release",
        "get_position", "get_sensor", "set_speed", "set_mode",
        "calibrate", "reset_device", "query_status",
    ]

    def __init__(self, device_manager=None):
        self._device_manager = device_manager

    def set_device_manager(self, dm):
        self._device_manager = dm

    async def execute(self, task: Task) -> ActionResult:
        if not self._device_manager:
            return ActionResult(
                success=False,
                message="设备管理器未初始化",
            )

        device_name = task.target_device
        if not device_name:
            # 尝试从 params 获取
            device_name = task.params.get("device", "")

        if not device_name:
            return ActionResult(
                success=False,
                message=f"任务 {task.action} 未指定目标设备",
            )

        device = self._device_manager.get_device(device_name)
        if not device:
            return ActionResult(
                success=False,
                message=f"设备 '{device_name}' 未注册或离线",
            )

        logger.info("设备执行: %s → %s.%s(%s)",
                    task.task_id, device_name, task.action, task.params)

        result = await device.execute(task.action, task.params)
        return result

    async def cancel(self, task: Task):
        if self._device_manager and task.target_device:
            device = self._device_manager.get_device(task.target_device)
            if device:
                await device.emergency_stop()

    async def emergency_stop(self):
        """紧急停止所有设备。"""
        if self._device_manager:
            await self._device_manager.emergency_stop_all()
