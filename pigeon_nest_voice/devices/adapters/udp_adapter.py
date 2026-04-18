"""UDP 设备适配器 — 基于 asyncio UDP 的设备通信。

适用场景: 低延迟实时控制指令、传感器数据快速传输。
"""

import asyncio
import json
import logging
from typing import Any

from pigeon_nest_voice.devices.base import BaseDevice, DeviceInfo, DeviceStatus
from pigeon_nest_voice.executor.base import ActionResult

logger = logging.getLogger(__name__)


class _UDPProtocol(asyncio.DatagramProtocol):
    """内部 UDP 协议处理。"""

    def __init__(self):
        self.transport: asyncio.DatagramTransport | None = None
        self._response_future: asyncio.Future | None = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if self._response_future and not self._response_future.done():
            self._response_future.set_result(data)

    def error_received(self, exc):
        if self._response_future and not self._response_future.done():
            self._response_future.set_exception(exc)

    def connection_lost(self, exc):
        pass


class UDPDevice(BaseDevice):
    """UDP 设备适配器。

    无连接模式，适合高频低延迟通信。
    """

    def __init__(self, info: DeviceInfo):
        super().__init__(info)
        self._protocol: _UDPProtocol | None = None
        self._transport: asyncio.DatagramTransport | None = None
        self._recv_timeout: float = 2.0

    async def connect(self) -> bool:
        try:
            loop = asyncio.get_running_loop()
            transport, protocol = await loop.create_datagram_endpoint(
                _UDPProtocol,
                remote_addr=(self.info.host, self.info.port),
            )
            self._transport = transport
            self._protocol = protocol
            self.status = DeviceStatus.ONLINE
            logger.info("UDP 端点就绪: %s:%d", self.info.host, self.info.port)
            return True
        except Exception as e:
            self.error_message = str(e)
            self.status = DeviceStatus.OFFLINE
            return False

    async def disconnect(self):
        if self._transport:
            self._transport.close()
            self._transport = None
        self.status = DeviceStatus.OFFLINE

    async def execute(self, action: str, params: dict[str, Any]) -> ActionResult:
        if not self._transport or not self._protocol:
            return ActionResult(success=False, message="UDP 端点未就绪")

        msg = json.dumps({"action": action, "params": params}, ensure_ascii=False)

        try:
            loop = asyncio.get_running_loop()
            self._protocol._response_future = loop.create_future()
            self._transport.sendto(msg.encode())

            raw = await asyncio.wait_for(
                self._protocol._response_future,
                timeout=self._recv_timeout,
            )
            resp = json.loads(raw.decode())
            return ActionResult(
                success=resp.get("success", False),
                message=resp.get("message", ""),
                data=resp.get("data", {}),
                raw_response=resp,
            )
        except asyncio.TimeoutError:
            return ActionResult(success=False, message="UDP 响应超时")
        except Exception as e:
            return ActionResult(success=False, message=f"UDP 通信异常: {e}")

    async def query_status(self) -> DeviceStatus:
        if not self._transport:
            return DeviceStatus.OFFLINE
        result = await self.execute("ping", {})
        return DeviceStatus.ONLINE if result.success else DeviceStatus.OFFLINE

    async def emergency_stop(self):
        if self._transport:
            try:
                msg = json.dumps({"action": "emergency_stop", "params": {}})
                self._transport.sendto(msg.encode())
            except Exception:
                pass
        self.status = DeviceStatus.ESTOP
        logger.critical("UDP 设备 %s 紧急停止", self.name)
