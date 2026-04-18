"""设备管理器 — 注册、发现、健康监控。"""

import asyncio
import logging
import time

from pigeon_nest_voice.devices.base import BaseDevice, DeviceStatus
from pigeon_nest_voice.dispatcher.events import EventBus

logger = logging.getLogger(__name__)

EVT_DEVICE_ONLINE = "device.online"
EVT_DEVICE_OFFLINE = "device.offline"
EVT_DEVICE_ERROR = "device.error"


class DeviceManager:
    """设备管理器。

    职责:
    - 维护设备注册表
    - 定期心跳检测
    - 通过事件总线广播设备状态变更
    """

    def __init__(self, heartbeat_interval: float = 5.0):
        self._devices: dict[str, BaseDevice] = {}
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_task: asyncio.Task | None = None
        self._running = False
        self._bus = EventBus.get_instance()

    def register(self, device: BaseDevice):
        """注册设备。"""
        self._devices[device.name] = device
        logger.info("设备注册: %s (type=%s, protocol=%s)",
                    device.name, device.info.device_type, device.info.protocol.value)

    def unregister(self, name: str):
        """注销设备。"""
        self._devices.pop(name, None)
        logger.info("设备注销: %s", name)

    def get_device(self, name: str) -> BaseDevice | None:
        return self._devices.get(name)

    def list_devices(self) -> list[dict]:
        return [d.to_dict() for d in self._devices.values()]

    def get_online_devices(self) -> list[BaseDevice]:
        return [d for d in self._devices.values() if d.is_available]

    async def connect_all(self):
        """尝试连接所有已注册的设备。"""
        tasks = [self._try_connect(d) for d in self._devices.values()]
        await asyncio.gather(*tasks)

    async def disconnect_all(self):
        """断开所有设备连接。"""
        for device in self._devices.values():
            try:
                await device.disconnect()
                device.status = DeviceStatus.OFFLINE
            except Exception:
                logger.exception("断开设备 %s 失败", device.name)

    async def emergency_stop_all(self):
        """紧急停止所有设备。"""
        logger.critical("设备管理器: 紧急停止所有设备！")
        tasks = []
        for device in self._devices.values():
            tasks.append(device.emergency_stop())
        await asyncio.gather(*tasks, return_exceptions=True)

    async def start_heartbeat(self):
        """启动心跳检测循环。"""
        if self._running:
            return
        self._running = True
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="device-heartbeat"
        )
        logger.info("设备心跳检测启动: interval=%.1fs", self._heartbeat_interval)

    async def stop_heartbeat(self):
        """停止心跳检测。"""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

    async def _try_connect(self, device: BaseDevice):
        try:
            ok = await device.connect()
            if ok:
                device.status = DeviceStatus.ONLINE
                await self._bus.publish(EVT_DEVICE_ONLINE, device.to_dict())
                logger.info("设备连接成功: %s", device.name)
            else:
                device.status = DeviceStatus.OFFLINE
                logger.warning("设备连接失败: %s", device.name)
        except Exception as e:
            device.status = DeviceStatus.ERROR
            device.error_message = str(e)
            logger.error("设备连接异常: %s — %s", device.name, e)

    async def _heartbeat_loop(self):
        """心跳检测循环。"""
        while self._running:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                for device in list(self._devices.values()):
                    if device.status == DeviceStatus.ESTOP:
                        continue  # E-Stop 中的设备不检测
                    old_status = device.status
                    alive = await device.heartbeat()
                    if old_status == DeviceStatus.ONLINE and not alive:
                        await self._bus.publish(EVT_DEVICE_OFFLINE, device.to_dict())
                        logger.warning("设备离线: %s", device.name)
                    elif old_status != DeviceStatus.ONLINE and alive:
                        await self._bus.publish(EVT_DEVICE_ONLINE, device.to_dict())
                        logger.info("设备恢复上线: %s", device.name)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("心跳检测循环异常")
