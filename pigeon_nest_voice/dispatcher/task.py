"""任务模型 — 状态机、优先级、DAG 分解。

任务生命周期:
    PENDING → VALIDATED → QUEUED → RUNNING → COMPLETED
                                          → FAILED
                                          → CANCELLED
                               → PAUSED → RUNNING (恢复)
"""

import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import IntEnum, Enum
from typing import Any

logger = logging.getLogger(__name__)


class TaskPriority(IntEnum):
    """任务优先级（数值越小优先级越高）。"""
    EMERGENCY = 0       # 紧急停止等安全操作
    CRITICAL = 10       # 关键实时控制
    HIGH = 20           # 用户直接发起的任务
    NORMAL = 50         # 普通任务
    LOW = 80            # 后台维护任务
    IDLE = 100          # 空闲时执行


class TaskStatus(str, Enum):
    """任务状态。"""
    PENDING = "pending"         # 已创建，未验证
    VALIDATED = "validated"     # 安全检查通过
    QUEUED = "queued"           # 已入队，等待调度
    RUNNING = "running"         # 执行中
    PAUSED = "paused"           # 已暂停（可恢复）
    COMPLETED = "completed"     # 成功完成
    FAILED = "failed"           # 执行失败
    CANCELLED = "cancelled"     # 被取消


class SafetyLevel(IntEnum):
    """操作安全等级。"""
    SAFE = 0            # 查询类，无需确认
    NORMAL = 1          # 普通控制，需用户确认
    DANGEROUS = 2       # 危险操作，双重确认 + 超时保护


# 合法的状态转换
_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING:     {TaskStatus.VALIDATED, TaskStatus.CANCELLED},
    TaskStatus.VALIDATED:   {TaskStatus.QUEUED, TaskStatus.CANCELLED},
    TaskStatus.QUEUED:      {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING:     {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.PAUSED},
    TaskStatus.PAUSED:      {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED:   set(),
    TaskStatus.FAILED:      set(),
    TaskStatus.CANCELLED:   set(),
}


@dataclass
class Task:
    """任务实体。

    每个任务代表一个可执行的操作单元，包含完整的状态追踪。
    """
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""                              # 人类可读名称
    action: str = ""                            # 动作标识 (如 "move_arm", "grab")
    params: dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    safety_level: SafetyLevel = SafetyLevel.SAFE
    status: TaskStatus = TaskStatus.PENDING

    # 来源
    session_id: str = ""                        # 关联的会话
    parent_task_id: str = ""                    # 父任务ID（DAG 场景）
    subtask_ids: list[str] = field(default_factory=list)

    # 执行目标
    target_device: str = ""                     # 目标设备名
    executor_type: str = ""                     # 执行器类型 (如 "device", "http", "plugin")

    # 结果
    result: Any = None
    error: str = ""

    # 时间追踪
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    finished_at: float = 0.0
    timeout: float = 30.0                       # 超时（秒），0 表示无超时

    # 重试
    max_retries: int = 0
    retry_count: int = 0

    def transition_to(self, new_status: TaskStatus) -> bool:
        """状态转换（带合法性检查）。

        Returns:
            True 如果转换成功，False 如果非法转换。
        """
        valid = _VALID_TRANSITIONS.get(self.status, set())
        if new_status not in valid:
            logger.warning(
                "非法状态转换: task=%s, %s → %s (合法: %s)",
                self.task_id, self.status, new_status, valid,
            )
            return False

        old = self.status
        self.status = new_status

        if new_status == TaskStatus.RUNNING:
            self.started_at = time.time()
        elif new_status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            self.finished_at = time.time()

        logger.debug("任务状态变更: %s [%s → %s]", self.task_id, old, new_status)
        return True

    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)

    @property
    def elapsed(self) -> float:
        """已运行时间（秒）。"""
        if self.started_at == 0:
            return 0.0
        end = self.finished_at if self.finished_at > 0 else time.time()
        return end - self.started_at

    @property
    def is_timed_out(self) -> bool:
        if self.timeout <= 0 or self.status != TaskStatus.RUNNING:
            return False
        return self.elapsed > self.timeout

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "action": self.action,
            "params": self.params,
            "priority": self.priority.name,
            "safety_level": self.safety_level.name,
            "status": self.status.value,
            "target_device": self.target_device,
            "result": str(self.result) if self.result else None,
            "error": self.error,
            "elapsed": round(self.elapsed, 3),
            "created_at": self.created_at,
        }


@dataclass
class TaskGroup:
    """任务组 — 表示一组需要协调执行的子任务 (DAG)。

    支持:
    - 顺序执行 (sequential): 子任务按序依次执行
    - 并行执行 (parallel): 子任务同时执行
    - 混合: 通过嵌套 TaskGroup 实现
    """
    group_id: str = field(default_factory=lambda: f"grp-{uuid.uuid4().hex[:8]}")
    name: str = ""
    mode: str = "sequential"            # "sequential" | "parallel"
    tasks: list[Task] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING

    def add_task(self, task: Task):
        task.parent_task_id = self.group_id
        self.tasks.append(task)

    @property
    def is_complete(self) -> bool:
        return all(t.is_terminal for t in self.tasks)

    @property
    def has_failure(self) -> bool:
        return any(t.status == TaskStatus.FAILED for t in self.tasks)
