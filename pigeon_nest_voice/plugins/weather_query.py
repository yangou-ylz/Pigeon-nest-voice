"""天气查询插件（示例，返回模拟数据）。"""

from datetime import datetime
from typing import Any

from pigeon_nest_voice.plugins.base import BasePlugin, PluginResult


class WeatherPlugin(BasePlugin):
    name = "weather_query"
    actions = ["query_weather"]
    description = "查询天气信息（当前为模拟数据，可接入真实API）"

    async def execute(self, action: str, params: dict[str, Any]) -> PluginResult:
        # TODO: 接入真实天气 API（如和风天气、OpenWeatherMap）
        city = params.get("city", "当前城市")
        now = datetime.now()
        hour = now.hour

        if 6 <= hour < 12:
            period = "上午"
        elif 12 <= hour < 18:
            period = "下午"
        else:
            period = "晚上"

        message = (
            f"📍 {city}天气（模拟数据）：{period}多云转晴，气温 18~26°C，"
            f"湿度 55%，东南风 2级。\n"
            f"💡 提示：这是模拟数据，如需真实天气请配置天气 API。"
        )
        return PluginResult(
            success=True,
            message=message,
            data={"city": city, "temp_range": "18~26", "weather": "多云转晴"},
        )
