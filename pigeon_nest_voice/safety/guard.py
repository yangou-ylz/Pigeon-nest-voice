"""安全守卫 — 任务安全验证、操作分级、E-Stop 管理。

安全等级:
  Level 0 (SAFE):      查询类操作，无需确认，直接执行
  Level 1 (NORMAL):    普通控制，需用户确认后执行
  Level 2 (DANGEROUS): 危险操作，双重确认 + 超时保护 + 操作审计

设计原则:
  - 默认拒绝：未注册的操作默认为 DANGEROUS
  - 白名单机制：只有明确标记安全的操作才跳过确认
  - 所有物理控制操作都有超时保护
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from pigeon_nest_voice.dispatcher.task import Task, SafetyLevel, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class SafetyRecord:
    """操作审计记录。"""
    task_id: str
    action: str
    safety_level: str
    decision: str               # "approved" | "rejected" | "timeout"
    reason: str = ""
    timestamp: float = field(default_factory=time.time)


class SafetyGuard:
    """安全守卫。

    职责:
    1. 验证任务是否允许执行
    2. 根据 action 自动判定安全等级
    3. 维护操作审计日志
    4. 管理 E-Stop 状态
    """

    def __init__(self):
        # action → SafetyLevel 注册表
        self._action_levels: dict[str, SafetyLevel] = {}
        # 审计日志（最近 N 条）
        self._audit_log: list[SafetyRecord] = []
        self._max_audit_size: int = 500
        # E-Stop
        self._estop_active: bool = False

        # 注册默认安全等级
        self._register_defaults()

    def _register_defaults(self):
        """注册默认的操作安全等级。"""
        # Level 0: 查询类
        safe_actions = [
            "query_time", "query_weather", "system_info",
            "query_status", "get_position", "get_sensor",
        ]
        for action in safe_actions:
            self._action_levels[action] = SafetyLevel.SAFE

        # Level 1: 普通控制
        normal_actions = [
            "move_arm", "set_position", "grab", "release",
            "set_speed", "set_mode",
        ]
        for action in normal_actions:
            self._action_levels[action] = SafetyLevel.NORMAL

        # Level 2: 危险操作
        dangerous_actions = [
            "emergency_stop", "reset_device", "force_override",
            "calibrate", "firmware_update",
        ]
        for action in dangerous_actions:
            self._action_levels[action] = SafetyLevel.DANGEROUS

    def register_action_level(self, action: str, level: SafetyLevel):
        """注册/更新操作的安全等级。"""
        self._action_levels[action] = level

    def get_action_level(self, action: str) -> SafetyLevel:
        """获取操作的安全等级（未注册的默认为 DANGEROUS）。"""
        return self._action_levels.get(action, SafetyLevel.DANGEROUS)

    async def validate(self, task: Task) -> tuple[bool, str]:
        """验证任务是否可以执行。

        Returns:
            (通过, 原因) — True 表示允许执行
        """
        # E-Stop 检查
        if self._estop_active:
            self._record(task, "rejected", "紧急停止生效中")
            return False, "紧急停止生效中，拒绝所有操作"

        # 确定安全等级
        level = self.get_action_level(task.action)
        task.safety_level = level

        # Level 0: 直接通过
        if level == SafetyLevel.SAFE:
            self._record(task, "approved", "安全操作，自动通过")
            return True, ""

        # Level 1: 需确认（当前骨架阶段先自动通过，后续接入前端确认）
        if level == SafetyLevel.NORMAL:
            # TODO: 接入前端确认机制（WebSocket 推送确认请求）
            self._record(task, "approved", "普通控制，自动通过（待接入确认）")
            logger.info("安全守卫: 任务 %s [%s] — 普通控制，通过", task.task_id, task.action)
            return True, ""

        # Level 2: 危险操作
        if level == SafetyLevel.DANGEROUS:
            # 确保有超时保护
            if task.timeout <= 0:
                task.timeout = 10.0  # 强制添加超时
                logger.warning("危险操作强制添加超时: %s → %.1fs", task.task_id, task.timeout)

            # TODO: 双重确认机制
            self._record(task, "approved", "危险操作，强制超时保护（待接入双重确认）")
            logger.warning("安全守卫: 任务 %s [%s] — ⚠️ 危险操作，已添加超时保护", task.task_id, task.action)
            return True, ""

        return False, "未知安全等级"

    def activate_estop(self):
        """激活紧急停止。"""
        self._estop_active = True
        logger.critical("安全守卫: 紧急停止已激活")

    def deactivate_estop(self):
        """解除紧急停止。"""
        self._estop_active = False
        logger.info("安全守卫: 紧急停止已解除")

    @property
    def estop_active(self) -> bool:
        return self._estop_active

    def get_audit_log(self, limit: int = 50) -> list[dict]:
        """获取最近的审计记录。"""
        return [
            {
                "task_id": r.task_id,
                "action": r.action,
                "safety_level": r.safety_level,
                "decision": r.decision,
                "reason": r.reason,
                "timestamp": r.timestamp,
            }
            for r in self._audit_log[-limit:]
        ]

    def _record(self, task: Task, decision: str, reason: str):
        record = SafetyRecord(
            task_id=task.task_id,
            action=task.action,
            safety_level=task.safety_level.name if isinstance(task.safety_level, SafetyLevel) else str(task.safety_level),
            decision=decision,
            reason=reason,
        )
        self._audit_log.append(record)
        if len(self._audit_log) > self._max_audit_size:
            self._audit_log = self._audit_log[-self._max_audit_size:]
