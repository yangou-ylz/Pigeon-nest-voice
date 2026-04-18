"""TCP 设备适配器 — 基于 asyncio TCP 的设备通信。

适用场景: 机械臂控制、与另一台主机的 TCP 长连接通信。
"""

import asyncio
import json
import logging
from typing import Any

from pigeon_nest_voice.devices.base import BaseDevice, DeviceInfo, DeviceStatus, CommProtocol
from pigeon_nest_voice.executor.base import ActionResult

logger = logging.getLogger(__name__)


class TCPDevice(BaseDevice):
    """TCP 设备适配器。

    通过 TCP 长连接与远程设备/主机通信。
    消息格式: JSON 行协议 (每条消息以 \\n 结尾)。

    用法:
        info = DeviceInfo(name="arm_01", host="192.168.1.100", port=9000,
                          protocol=CommProtocol.TCP, device_type="robotic_arm")
        arm = TCPDevice(info)
        await arm.connect()
        result = await arm.execute("move_arm", {"x": 100, "y": 200, "z": 50})
    """

    def __init__(self, info: DeviceInfo):
        super().__init__(info)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._recv_timeout: float = 5.0

    async def connect(self) -> bool:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.info.host, self.info.port),
                timeout=5.0,
            )
            self.status = DeviceStatus.ONLINE
            logger.info("TCP 连接成功: %s:%d", self.info.host, self.info.port)
            return True
        except Exception as e:
            self.error_message = str(e)
            self.status = DeviceStatus.OFFLINE
            logger.error("TCP 连接失败: %s:%d — %s", self.info.host, self.info.port, e)
            return False

    async def disconnect(self):
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
        self.status = DeviceStatus.OFFLINE

    async def execute(self, action: str, params: dict[str, Any]) -> ActionResult:
        if not self._writer or self.status != DeviceStatus.ONLINE:
            return ActionResult(success=False, message="设备未连接")

        # 构造消息
        msg = {"action": action, "params": params}
        payload = json.dumps(msg, ensure_ascii=False) + "\n"

        try:
            self._writer.write(payload.encode())
            await self._writer.drain()

            # 等待响应
            raw = await asyncio.wait_for(
                self._reader.readline(),
                timeout=self._recv_timeout,
            )
            if not raw:
                return ActionResult(success=False, message="设备无响应")

            resp = json.loads(raw.decode().strip())
            return ActionResult(
                success=resp.get("success", False),
                message=resp.get("message", ""),
                data=resp.get("data", {}),
                raw_response=resp,
            )
        except asyncio.TimeoutError:
            return ActionResult(success=False, message="设备响应超时")
        except Exception as e:
            self.status = DeviceStatus.ERROR
            self.error_message = str(e)
            return ActionResult(success=False, message=f"通信异常: {e}")

    async def query_status(self) -> DeviceStatus:
        if not self._writer:
            return DeviceStatus.OFFLINE
        try:
            result = await self.execute("ping", {})
            return DeviceStatus.ONLINE if result.success else DeviceStatus.ERROR
        except Exception:
            return DeviceStatus.OFFLINE

    async def emergency_stop(self):
        """紧急停止: 发送 E-Stop 指令后关闭连接。"""
        if self._writer and self.status != DeviceStatus.OFFLINE:
            try:
                msg = json.dumps({"action": "emergency_stop", "params": {}}) + "\n"
                self._writer.write(msg.encode())
                await self._writer.drain()
            except Exception:
                pass
        self.status = DeviceStatus.ESTOP
        logger.critical("TCP 设备 %s 紧急停止", self.name)
