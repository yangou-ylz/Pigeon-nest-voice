"""系统信息插件。"""

import platform
import shutil
import os
from typing import Any

from pigeon_nest_voice.plugins.base import BasePlugin, PluginResult


class SystemInfoPlugin(BasePlugin):
    name = "system_info"
    actions = ["query_system"]
    description = "查询系统运行状态（CPU、内存、磁盘等）"

    async def execute(self, action: str, params: dict[str, Any]) -> PluginResult:
        # 基础系统信息
        uname = platform.uname()
        disk = shutil.disk_usage("/")

        # 读取 /proc 获取内存和负载
        mem_info = self._get_memory_info()
        load_avg = os.getloadavg()

        parts = [
            f"🖥️ 系统: {uname.system} {uname.release}",
            f"📛 主机: {uname.node}",
            f"🧠 CPU: {os.cpu_count()} 核, 负载 {load_avg[0]:.1f}/{load_avg[1]:.1f}/{load_avg[2]:.1f}",
        ]

        if mem_info:
            parts.append(
                f"💾 内存: {mem_info['used_gb']:.1f}G / {mem_info['total_gb']:.1f}G "
                f"({mem_info['percent']:.0f}%)"
            )

        parts.append(
            f"💿 磁盘(/): {disk.used / (1 << 30):.1f}G / {disk.total / (1 << 30):.1f}G "
            f"({disk.used / disk.total * 100:.0f}%)"
        )

        return PluginResult(
            success=True,
            message="\n".join(parts),
            data={"cpu_count": os.cpu_count(), "load": load_avg[0]},
        )

    @staticmethod
    def _get_memory_info() -> dict | None:
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            info = {}
            for line in lines:
                if line.startswith(("MemTotal:", "MemAvailable:")):
                    key, val = line.split(":")
                    info[key.strip()] = int(val.strip().split()[0])
            total_kb = info.get("MemTotal", 0)
            avail_kb = info.get("MemAvailable", 0)
            used_kb = total_kb - avail_kb
            return {
                "total_gb": total_kb / (1 << 20),
                "used_gb": used_kb / (1 << 20),
                "percent": (used_kb / total_kb * 100) if total_kb else 0,
            }
        except Exception:
            return None
