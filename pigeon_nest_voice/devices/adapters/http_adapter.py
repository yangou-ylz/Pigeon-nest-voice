"""HTTP 设备适配器 — 基于 httpx 的设备通信。

适用场景: RESTful API 设备控制、与远程服务通信。
"""

import logging
from typing import Any

import httpx

from pigeon_nest_voice.devices.base import BaseDevice, DeviceInfo, DeviceStatus
from pigeon_nest_voice.executor.base import ActionResult

logger = logging.getLogger(__name__)


class HTTPDevice(BaseDevice):
    """HTTP 设备适配器。

    将设备操作映射为 HTTP POST 请求。

    API 约定:
        POST {base_url}/{action}
        Body: {"params": {...}}
        Response: {"success": bool, "message": str, "data": {...}}
    """

    def __init__(self, info: DeviceInfo, base_url: str = ""):
        super().__init__(info)
        self._base_url = base_url or f"http://{info.host}:{info.port}"
        self._client: httpx.AsyncClient | None = None
        self._timeout = 10.0

    async def connect(self) -> bool:
        try:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
            )
            # 尝试 ping
            resp = await self._client.get("/ping")
            if resp.status_code == 200:
                self.status = DeviceStatus.ONLINE
                return True
            self.status = DeviceStatus.ERROR
            return False
        except Exception as e:
            self.error_message = str(e)
            self.status = DeviceStatus.OFFLINE
            return False

    async def disconnect(self):
        if self._client:
            await self._client.aclose()
            self._client = None
        self.status = DeviceStatus.OFFLINE

    async def execute(self, action: str, params: dict[str, Any]) -> ActionResult:
        if not self._client:
            return ActionResult(success=False, message="HTTP 客户端未初始化")

        try:
            resp = await self._client.post(
                f"/api/{action}",
                json={"params": params},
            )
            data = resp.json()
            return ActionResult(
                success=data.get("success", False),
                message=data.get("message", ""),
                data=data.get("data", {}),
                raw_response=data,
            )
        except httpx.TimeoutException:
            return ActionResult(success=False, message="HTTP 请求超时")
        except Exception as e:
            return ActionResult(success=False, message=f"HTTP 异常: {e}")

    async def query_status(self) -> DeviceStatus:
        if not self._client:
            return DeviceStatus.OFFLINE
        try:
            resp = await self._client.get("/ping")
            return DeviceStatus.ONLINE if resp.status_code == 200 else DeviceStatus.ERROR
        except Exception:
            return DeviceStatus.OFFLINE

    async def emergency_stop(self):
        if self._client:
            try:
                await self._client.post("/api/emergency_stop", json={})
            except Exception:
                pass
        self.status = DeviceStatus.ESTOP
        logger.critical("HTTP 设备 %s 紧急停止", self.name)
