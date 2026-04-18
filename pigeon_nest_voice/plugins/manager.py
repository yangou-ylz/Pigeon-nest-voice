"""插件管理器 — 自动发现、加载和调度插件。"""

import importlib
import inspect
import logging
import pkgutil
from typing import Any

from pigeon_nest_voice.plugins.base import BasePlugin, PluginResult

logger = logging.getLogger(__name__)


class PluginManager:
    """插件管理器。

    职责:
    1. 扫描 plugins/ 目录下所有模块，自动发现 BasePlugin 子类
    2. 按 action 名称注册插件，支持快速查找
    3. 调度执行：根据 action 找到插件并调用 execute()
    """

    def __init__(self):
        self._plugins: dict[str, BasePlugin] = {}    # name → plugin instance
        self._action_map: dict[str, BasePlugin] = {} # action → plugin instance

    def register(self, plugin: BasePlugin):
        """注册一个插件实例。"""
        if not plugin.name:
            logger.warning("插件缺少 name，跳过注册: %s", type(plugin).__name__)
            return
        if plugin.name in self._plugins:
            logger.warning("插件名称冲突，覆盖: %s", plugin.name)

        self._plugins[plugin.name] = plugin
        for action in plugin.actions:
            self._action_map[action] = plugin
        logger.info("注册插件: %s → actions=%s", plugin.name, plugin.actions)

    def auto_discover(self):
        """自动扫描 plugins/ 包下所有模块，发现并注册 BasePlugin 子类。"""
        import pigeon_nest_voice.plugins as plugins_pkg

        for importer, mod_name, is_pkg in pkgutil.iter_modules(plugins_pkg.__path__):
            if mod_name.startswith("_") or mod_name in ("base", "manager"):
                continue
            try:
                module = importlib.import_module(f"pigeon_nest_voice.plugins.{mod_name}")
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (inspect.isclass(attr)
                            and issubclass(attr, BasePlugin)
                            and attr is not BasePlugin
                            and not inspect.isabstract(attr)):
                        instance = attr()
                        self.register(instance)
            except Exception:
                logger.exception("加载插件模块失败: %s", mod_name)

        logger.info("插件自动发现完成: %d 个插件, %d 个动作",
                     len(self._plugins), len(self._action_map))

    def get_plugin(self, action: str) -> BasePlugin | None:
        """根据 action 名称查找插件。"""
        return self._action_map.get(action)

    def has_action(self, action: str) -> bool:
        """检查是否有插件能处理该 action。"""
        return action in self._action_map

    async def execute(self, action: str, params: dict[str, Any]) -> PluginResult | None:
        """执行指定 action，返回 PluginResult，无匹配插件返回 None。"""
        plugin = self._action_map.get(action)
        if not plugin:
            return None
        try:
            logger.info("插件执行: %s.%s(params=%s)", plugin.name, action, params)
            result = await plugin.execute(action, params)
            logger.info("插件完成: %s → %s", action,
                        "成功" if result.success else "失败")
            return result
        except Exception as e:
            logger.exception("插件执行异常: %s.%s", plugin.name, action)
            return PluginResult(success=False, message=f"插件执行出错: {e}")

    @property
    def plugin_count(self) -> int:
        return len(self._plugins)

    @property
    def action_list(self) -> list[str]:
        return list(self._action_map.keys())
