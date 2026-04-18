"""设备抽象基类。

所有物理设备必须实现此接口，无论底层通信协议是什么。
适配器模式：BaseDevice 定义统一接口，具体通信由适配器实现。
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pigeon_nest_voice.executor.base import ActionResult

logger = logging.getLogger(__name__)


class DeviceStatus(str, Enum):
    """设备状态。"""
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    ERROR = "error"
    ESTOP = "estop"             # 紧急停止状态


class CommProtocol(str, Enum):
    """通信协议。"""
    TCP = "tcp"
    UDP = "udp"
    HTTP = "http"
    MQTT = "mqtt"
    LCM = "lcm"
    SERIAL = "serial"


@dataclass
class DeviceInfo:
    """设备信息。"""
    name: str                               # 唯一标识
    device_type: str = ""                   # 设备类型 (如 "robotic_arm")
    protocol: CommProtocol = CommProtocol.TCP
    host: str = ""                          # 目标主机
    port: int = 0                           # 目标端口
    capabilities: list[str] = field(default_factory=list)  # 能力列表
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseDevice(ABC):
    """设备抽象基类。

    所有物理设备（机械臂、传感器、摄像头等）必须实现此接口。
    适配器只需关注通信细节，上层统一调用。
    """

    def __init__(self, info: DeviceInfo):
        self.info = info
        self.status = DeviceStatus.UNKNOWN
        self.last_heartbeat: float = 0.0
        self.error_message: str = ""

    @property
    def name(self) -> str:
        return self.info.name

    @property
    def is_available(self) -> bool:
        return self.status in (DeviceStatus.ONLINE,)

    @abstractmethod
    async def connect(self) -> bool:
        """建立连接。返回 True 表示成功。"""
        ...

    @abstractmethod
    async def disconnect(self):
        """断开连接。"""
        ...

    @abstractmethod
    async def execute(self, action: str, params: dict[str, Any]) -> ActionResult:
        """执行动作指令。

        Args:
            action: 动作名 (如 "move_arm", "grab")
            params: 参数字典

        Returns:
            ActionResult 执行结果
        """
        ...

    @abstractmethod
    async def query_status(self) -> DeviceStatus:
        """查询设备当前状态。"""
        ...

    async def emergency_stop(self):
        """紧急停止。默认将状态标记为 ESTOP，子类应覆盖实现真正的停止逻辑。"""
        self.status = DeviceStatus.ESTOP
        logger.critical("设备 %s 紧急停止", self.name)

    async def heartbeat(self) -> bool:
        """心跳检测。返回 True 表示设备在线。"""
        try:
            status = await self.query_status()
            self.last_heartbeat = time.time()
            self.status = status
            return status != DeviceStatus.OFFLINE
        except Exception as e:
            self.status = DeviceStatus.OFFLINE
            self.error_message = str(e)
            return False

    def to_dict(self) -> dict:
        return {
            "name": self.info.name,
            "type": self.info.device_type,
            "protocol": self.info.protocol.value,
            "host": self.info.host,
            "port": self.info.port,
            "status": self.status.value,
            "capabilities": self.info.capabilities,
            "last_heartbeat": self.last_heartbeat,
            "error": self.error_message,
        }
