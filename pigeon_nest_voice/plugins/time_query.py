"""时间查询插件。"""

from datetime import datetime
from typing import Any

from pigeon_nest_voice.plugins.base import BasePlugin, PluginResult


class TimePlugin(BasePlugin):
    name = "time_query"
    actions = ["query_time"]
    description = "查询当前日期和时间"

    async def execute(self, action: str, params: dict[str, Any]) -> PluginResult:
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekdays[now.weekday()]
        time_str = now.strftime("%H:%M:%S")
        date_str = now.strftime("%Y年%m月%d日")

        message = f"现在是 {date_str} {weekday}，时间 {time_str}。"
        return PluginResult(
            success=True,
            message=message,
            data={"date": date_str, "weekday": weekday, "time": time_str},
        )
