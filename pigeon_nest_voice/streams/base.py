"""流管道基础设施 — 为实时数据流（视频、传感器）提供统一抽象。

当前为地基，后续扩展:
- 视频流 (摄像头 → YOLO 检测 → 标注帧 → 前端显示)
- 传感器流 (力矩、位置 → 实时监控)
- 多流合并/分发

架构:
    StreamSource → [StreamProcessor] → [StreamProcessor] → StreamSink
    (生产者)      (处理链，可插拔)                          (消费者)
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class StreamFrame:
    """流中的一帧数据。"""
    frame_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    stream_name: str = ""
    data: Any = None                    # 原始数据（bytes/ndarray/dict 等）
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class StreamSource(ABC):
    """流数据源（生产者）。"""
    name: str = ""

    @abstractmethod
    async def start(self):
        """开始产生数据。"""
        ...

    @abstractmethod
    async def stop(self):
        """停止。"""
        ...

    @abstractmethod
    async def read_frame(self) -> StreamFrame | None:
        """读取一帧数据。返回 None 表示流已结束。"""
        ...


class StreamProcessor(ABC):
    """流处理器（可插拔的中间环节）。"""
    name: str = ""

    @abstractmethod
    async def process(self, frame: StreamFrame) -> StreamFrame | None:
        """处理一帧数据。返回 None 表示丢弃该帧。"""
        ...


class StreamSink(ABC):
    """流消费者（终端）。"""
    name: str = ""

    @abstractmethod
    async def write_frame(self, frame: StreamFrame):
        """消费一帧数据。"""
        ...


class StreamPipeline:
    """流管道 — 串联 Source → Processors → Sink。

    用法:
        pipeline = StreamPipeline("camera_pipeline")
        pipeline.set_source(CameraSource(...))
        pipeline.add_processor(YOLODetector(...))
        pipeline.set_sink(WebSocketSink(...))
        await pipeline.start()
    """

    def __init__(self, name: str = ""):
        self.name = name or f"pipeline-{uuid.uuid4().hex[:6]}"
        self._source: StreamSource | None = None
        self._processors: list[StreamProcessor] = []
        self._sink: StreamSink | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._frame_count = 0

    def set_source(self, source: StreamSource):
        self._source = source

    def add_processor(self, processor: StreamProcessor):
        self._processors.append(processor)

    def set_sink(self, sink: StreamSink):
        self._sink = sink

    async def start(self):
        """启动管道。"""
        if not self._source:
            raise ValueError("管道缺少数据源")
        self._running = True
        await self._source.start()
        self._task = asyncio.create_task(self._run_loop(), name=f"stream-{self.name}")
        logger.info("流管道启动: %s (processors=%d)", self.name, len(self._processors))

    async def stop(self):
        """停止管道。"""
        self._running = False
        if self._source:
            await self._source.stop()
        if self._task:
            self._task.cancel()
        logger.info("流管道停止: %s (已处理 %d 帧)", self.name, self._frame_count)

    async def _run_loop(self):
        while self._running:
            try:
                frame = await self._source.read_frame()
                if frame is None:
                    await asyncio.sleep(0.001)
                    continue

                # 通过处理链
                for processor in self._processors:
                    frame = await processor.process(frame)
                    if frame is None:
                        break  # 帧被丢弃

                # 送到消费者
                if frame and self._sink:
                    await self._sink.write_frame(frame)

                self._frame_count += 1

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("流管道 %s 处理异常", self.name)
                await asyncio.sleep(0.01)


class StreamManager:
    """流管道管理器。"""

    def __init__(self):
        self._pipelines: dict[str, StreamPipeline] = {}

    def register(self, pipeline: StreamPipeline):
        self._pipelines[pipeline.name] = pipeline

    async def start_all(self):
        for p in self._pipelines.values():
            await p.start()

    async def stop_all(self):
        for p in self._pipelines.values():
            await p.stop()

    def get_pipeline(self, name: str) -> StreamPipeline | None:
        return self._pipelines.get(name)

    def list_pipelines(self) -> list[str]:
        return list(self._pipelines.keys())
