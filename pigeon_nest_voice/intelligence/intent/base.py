"""意图数据结构与解析器抽象基类。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class IntentType(str, Enum):
    """意图类型枚举。"""
    CHAT = "chat"                       # 普通对话
    TASK_FETCH = "task_fetch"           # 取物品
    TASK_QUERY = "task_query"           # 查询类任务
    TASK_CONTROL = "task_control"       # 控制类任务
    UNKNOWN = "unknown"                 # 未识别


@dataclass
class Intent:
    """意图解析结果。"""
    type: IntentType                    # 意图类型
    action: str = ""                    # 对应动作名 (如 "fetch_item")
    params: dict = field(default_factory=dict)  # 提取的参数 (如 {"item": "薯片"})
    confidence: float = 1.0             # 置信度 0~1
    raw_text: str = ""                  # 原始输入文本

    @property
    def is_task(self) -> bool:
        return self.type not in (IntentType.CHAT, IntentType.UNKNOWN)


@dataclass
class PendingTask:
    """会话中等待澄清的任务。

    当意图识别成功但参数不完整时，任务挂起并向用户追问。
    用户回复后，系统尝试将新信息合并到 params 中继续执行。
    """
    intent: Intent                      # 原始意图
    missing_fields: list[str] = field(default_factory=list)  # 待补全的字段
    asked_field: str = ""               # 当前正在追问的字段
    attempts: int = 0                   # 已追问次数（防止死循环）

    MAX_ATTEMPTS: int = 3               # 最多追问次数


class BaseIntentParser(ABC):
    """意图解析器抽象基类。"""

    @abstractmethod
    async def parse(self, text: str) -> Intent:
        """解析用户输入文本，返回意图。"""
        ...
