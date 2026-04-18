"""动作执行器抽象基类。

每个执行器负责一类操作的实际执行逻辑:
- DeviceActionExecutor: 向设备发送控制指令
- HTTPActionExecutor:   发起 HTTP 请求
- PluginActionExecutor: 桥接现有插件系统
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pigeon_nest_voice.dispatcher.task import Task


@dataclass
class ActionResult:
    """动作执行结果。"""
    success: bool = True
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    raw_response: Any = None        # 设备原始响应


class BaseActionExecutor(ABC):
    """动作执行器抽象基类。"""

    name: str = ""
    executor_type: str = ""         # "device" | "http" | "plugin" | "internal"
    supported_actions: list[str] = []

    @abstractmethod
    async def execute(self, task: Task) -> ActionResult:
        """执行任务，返回结果。"""
        ...

    @abstractmethod
    async def cancel(self, task: Task):
        """取消正在执行的任务。"""
        ...

    def can_handle(self, action: str) -> bool:
        """是否能处理该动作。"""
        return action in self.supported_actions
