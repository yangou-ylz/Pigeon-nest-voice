"""任务调度器 — 优先级队列 + 异步并发执行。

职责:
- 接收 Task，经安全检查后入队
- 按优先级调度任务到执行器
- 管理任务生命周期（超时、重试、取消）
- 通过事件总线广播状态变更
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from pigeon_nest_voice.dispatcher.events import EventBus
from pigeon_nest_voice.dispatcher.task import (
    Task, TaskGroup, TaskStatus, TaskPriority, SafetyLevel,
)

if TYPE_CHECKING:
    from pigeon_nest_voice.executor.manager import ExecutionManager
    from pigeon_nest_voice.safety.guard import SafetyGuard

logger = logging.getLogger(__name__)

# ── 事件名常量 ──
EVT_TASK_SUBMITTED = "task.submitted"
EVT_TASK_VALIDATED = "task.validated"
EVT_TASK_STARTED = "task.started"
EVT_TASK_COMPLETED = "task.completed"
EVT_TASK_FAILED = "task.failed"
EVT_TASK_CANCELLED = "task.cancelled"
EVT_TASK_TIMEOUT = "task.timeout"
EVT_ESTOP = "system.emergency_stop"


class TaskScheduler:
    """核心任务调度器。

    特性:
    - asyncio.PriorityQueue 按优先级调度
    - 并发限制 (max_concurrent) 防止资源过载
    - 超时看门狗自动终止超时任务
    - 紧急停止 (E-Stop) 立即取消所有运行中任务
    """

    def __init__(
        self,
        execution_manager: "ExecutionManager | None" = None,
        safety_guard: "SafetyGuard | None" = None,
        max_concurrent: int = 4,
    ):
        self.execution_manager = execution_manager
        self.safety_guard = safety_guard
        self.max_concurrent = max_concurrent

        self._queue: asyncio.PriorityQueue[tuple[int, float, Task]] = asyncio.PriorityQueue()
        self._running_tasks: dict[str, Task] = {}       # task_id → Task
        self._all_tasks: dict[str, Task] = {}            # 全部任务（含历史）
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running = False
        self._scheduler_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._bus = EventBus.get_instance()

        # E-Stop 状态
        self._estop_active = False

    async def start(self):
        """启动调度器主循环和看门狗。"""
        if self._running:
            return
        self._running = True
        self._estop_active = False
        self._scheduler_task = asyncio.create_task(self._scheduler_loop(), name="task-scheduler")
        self._watchdog_task = asyncio.create_task(self._watchdog_loop(), name="task-watchdog")

        # 订阅紧急停止事件
        self._bus.subscribe(EVT_ESTOP, self._on_estop)

        logger.info("TaskScheduler 启动: max_concurrent=%d", self.max_concurrent)

    async def stop(self):
        """停止调度器，取消所有运行中的任务。"""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
        if self._watchdog_task:
            self._watchdog_task.cancel()

        # 取消所有运行中任务
        for task in list(self._running_tasks.values()):
            await self.cancel_task(task.task_id)

        logger.info("TaskScheduler 已停止")

    async def submit(self, task: Task) -> Task:
        """提交任务到调度器。

        流程: 安全检查 → 入队 → 返回任务对象（可通过 task_id 查询状态）
        """
        if self._estop_active:
            task.status = TaskStatus.CANCELLED
            task.error = "紧急停止生效中，拒绝新任务"
            return task

        self._all_tasks[task.task_id] = task

        # 安全检查
        if self.safety_guard:
            ok, reason = await self.safety_guard.validate(task)
            if not ok:
                task.status = TaskStatus.CANCELLED
                task.error = f"安全检查未通过: {reason}"
                logger.warning("任务被安全守卫拒绝: %s — %s", task.task_id, reason)
                return task

        task.transition_to(TaskStatus.VALIDATED)
        await self._bus.publish(EVT_TASK_VALIDATED, task.to_dict())

        # 入队（优先级, 时间戳用于同优先级FIFO）
        task.transition_to(TaskStatus.QUEUED)
        await self._queue.put((task.priority.value, task.created_at, task))

        await self._bus.publish(EVT_TASK_SUBMITTED, task.to_dict())
        logger.info("任务入队: %s [%s] priority=%s", task.task_id, task.action, task.priority.name)

        return task

    async def submit_group(self, group: TaskGroup) -> TaskGroup:
        """提交任务组。

        sequential: 按顺序逐个提交执行
        parallel: 同时提交所有子任务
        """
        if group.mode == "parallel":
            for task in group.tasks:
                await self.submit(task)
        elif group.mode == "sequential":
            # 顺序执行：先提交第一个，后续通过事件驱动链式提交
            if group.tasks:
                first = group.tasks[0]
                first.params["__group_id"] = group.group_id
                first.params["__group_index"] = 0
                await self.submit(first)
                # 后续任务存入 _all_tasks 但不入队
                for i, task in enumerate(group.tasks[1:], 1):
                    task.params["__group_id"] = group.group_id
                    task.params["__group_index"] = i
                    self._all_tasks[task.task_id] = task
        group.status = TaskStatus.QUEUED
        return group

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务。"""
        task = self._all_tasks.get(task_id)
        if not task or task.is_terminal:
            return False

        task.transition_to(TaskStatus.CANCELLED)
        self._running_tasks.pop(task_id, None)
        await self._bus.publish(EVT_TASK_CANCELLED, task.to_dict())
        logger.info("任务已取消: %s", task_id)
        return True

    async def emergency_stop(self):
        """紧急停止 — 取消所有运行中和排队的任务。"""
        self._estop_active = True
        logger.critical("🚨 紧急停止触发！取消所有任务...")

        # 取消所有运行中任务
        for task in list(self._running_tasks.values()):
            task.transition_to(TaskStatus.CANCELLED)
            task.error = "紧急停止"
        self._running_tasks.clear()

        # 清空队列
        while not self._queue.empty():
            try:
                _, _, task = self._queue.get_nowait()
                task.transition_to(TaskStatus.CANCELLED)
                task.error = "紧急停止"
            except asyncio.QueueEmpty:
                break

        # 通知执行层
        if self.execution_manager:
            await self.execution_manager.emergency_stop_all()

        await self._bus.publish(EVT_ESTOP, {"time": time.time()})

    def get_task(self, task_id: str) -> Task | None:
        return self._all_tasks.get(task_id)

    def get_running_tasks(self) -> list[Task]:
        return list(self._running_tasks.values())

    def get_queue_size(self) -> int:
        return self._queue.qsize()

    def clear_estop(self):
        """解除紧急停止状态。"""
        self._estop_active = False
        logger.info("紧急停止已解除")

    # ── 内部循环 ──

    async def _scheduler_loop(self):
        """主调度循环：从队列取任务，分配执行。"""
        while self._running:
            try:
                # 等待任务（带超时，避免关闭时阻塞）
                try:
                    priority, ts, task = await asyncio.wait_for(
                        self._queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                if self._estop_active or task.is_terminal:
                    continue

                # 并发限制
                await self._semaphore.acquire()
                asyncio.create_task(self._execute_task(task))

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("调度器主循环异常")
                await asyncio.sleep(0.5)

    async def _execute_task(self, task: Task):
        """执行单个任务（在并发限制内）。"""
        try:
            task.transition_to(TaskStatus.RUNNING)
            self._running_tasks[task.task_id] = task
            await self._bus.publish(EVT_TASK_STARTED, task.to_dict())

            if not self.execution_manager:
                task.result = f"[无执行器] 任务 {task.action} 已调度但无执行器"
                task.transition_to(TaskStatus.COMPLETED)
            else:
                # 带超时执行
                if task.timeout > 0:
                    result = await asyncio.wait_for(
                        self.execution_manager.execute(task),
                        timeout=task.timeout,
                    )
                else:
                    result = await self.execution_manager.execute(task)

                task.result = result
                task.transition_to(TaskStatus.COMPLETED)

            await self._bus.publish(EVT_TASK_COMPLETED, task.to_dict())
            logger.info("任务完成: %s [%.1fms]", task.task_id, task.elapsed * 1000)

        except asyncio.TimeoutError:
            task.error = f"执行超时 ({task.timeout}s)"
            task.transition_to(TaskStatus.FAILED)
            await self._bus.publish(EVT_TASK_TIMEOUT, task.to_dict())
            logger.warning("任务超时: %s", task.task_id)

        except asyncio.CancelledError:
            task.transition_to(TaskStatus.CANCELLED)
            await self._bus.publish(EVT_TASK_CANCELLED, task.to_dict())

        except Exception as e:
            task.error = str(e)
            # 重试逻辑
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.QUEUED  # 直接重置，绕过状态机（重试特例）
                await self._queue.put((task.priority.value, task.created_at, task))
                logger.info("任务重试 (%d/%d): %s", task.retry_count, task.max_retries, task.task_id)
            else:
                task.transition_to(TaskStatus.FAILED)
                await self._bus.publish(EVT_TASK_FAILED, task.to_dict())
                logger.error("任务失败: %s — %s", task.task_id, e)

        finally:
            self._running_tasks.pop(task.task_id, None)
            self._semaphore.release()

    async def _watchdog_loop(self):
        """看门狗：定期检查超时任务。"""
        while self._running:
            try:
                await asyncio.sleep(2.0)
                for task in list(self._running_tasks.values()):
                    if task.is_timed_out:
                        logger.warning("看门狗检测到超时任务: %s (%.1fs)", task.task_id, task.elapsed)
                        await self.cancel_task(task.task_id)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("看门狗循环异常")

    async def _on_estop(self, event_name: str, data):
        """响应紧急停止事件。"""
        if not self._estop_active:
            await self.emergency_stop()
