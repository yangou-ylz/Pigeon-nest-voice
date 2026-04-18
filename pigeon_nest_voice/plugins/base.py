"""插件基类 — 所有插件必须继承此类。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginResult:
    """插件执行结果。"""
    success: bool = True
    message: str = ""               # 回复给用户的文字
    data: dict = field(default_factory=dict)  # 附加结构化数据（供前端或其他插件使用）


class BasePlugin(ABC):
    """插件抽象基类。

    每个插件需要声明:
    - name: 插件名称（唯一标识）
    - actions: 该插件能处理的 action 名称列表
    - description: 简短描述

    实现:
    - execute(action, params): 执行插件逻辑，返回 PluginResult
    """

    name: str = ""
    actions: list[str] = []
    description: str = ""

    @abstractmethod
    async def execute(self, action: str, params: dict[str, Any]) -> PluginResult:
        """执行插件动作。

        Args:
            action: 动作名称（如 "query_time"）
            params: 从意图解析中提取的参数

        Returns:
            PluginResult 包含执行结果
        """
        ...
