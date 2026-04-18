"""关键词意图解析器 — 基于关键词/正则匹配快速识别意图。"""

import re
import logging
from typing import NamedTuple

from pigeon_nest_voice.intelligence.intent.base import BaseIntentParser, Intent, IntentType

logger = logging.getLogger(__name__)


class _KeywordRule(NamedTuple):
    """一条关键词匹配规则。"""
    pattern: re.Pattern
    intent_type: IntentType
    action: str
    param_extractor: str | None   # 正则命名组，用于提取参数


# ── 取物品的动词集合（覆盖各种口语化表达）──
#   标准: 拿/取/带
#   口语: 要/给/来/弄/搞/整/夹/抓
#   礼貌: 请帮我拿/麻烦给我/能不能帮我
_FETCH_VERBS = r"拿|取|拿来|取来|带来|带|要|来|弄|搞|整|夹|抓|递|送来"
_FETCH_PREFIX = r"(?:帮我|请帮我|麻烦帮我|请|麻烦|能不能帮我|帮我从\S{0,10})"
# 量词: "一个" "一袋" "一瓶" "点" "些" 等
_FETCH_QUANTIFIER = r"(?:[一两三四五六七八九十\d]*[下个把袋包瓶杯份点些只条块盒箱罐壶碗])*"

# ── 内置关键词规则表（按优先级从高到低排列） ──
_BUILTIN_RULES: list[_KeywordRule] = [
    # ── 取物品模式1: "给我XXX" 系列（给我一个薯片、给我水）──
    _KeywordRule(
        pattern=re.compile(
            rf"(?:请|帮我|麻烦)?给我{_FETCH_QUANTIFIER}(?P<item>.+)",
        ),
        intent_type=IntentType.TASK_FETCH,
        action="fetch_item",
        param_extractor="item",
    ),

    # ── 取物品模式2: 动词系列（拿/取/要/来/弄/搞/整/夹...）──
    _KeywordRule(
        pattern=re.compile(
            rf"{_FETCH_PREFIX}?(?:{_FETCH_VERBS}){_FETCH_QUANTIFIER}(?P<item>.+)",
        ),
        intent_type=IntentType.TASK_FETCH,
        action="fetch_item",
        param_extractor="item",
    ),

    # ── 查询天气 ──
    _KeywordRule(
        pattern=re.compile(r"(?:查|搜索|查一下|查询)?.*天气"),
        intent_type=IntentType.TASK_QUERY,
        action="query_weather",
        param_extractor=None,
    ),

    # ── 查询时间 ──
    _KeywordRule(
        pattern=re.compile(r"(?:现在)?几点|时间"),
        intent_type=IntentType.TASK_QUERY,
        action="query_time",
        param_extractor=None,
    ),

    # ── 控制设备 ──
    _KeywordRule(
        pattern=re.compile(
            r"(?:帮我|请)?(?P<op>打开|关闭|开|关)(?P<device>.+)",
        ),
        intent_type=IntentType.TASK_CONTROL,
        action="control_device",
        param_extractor=None,
    ),
]


class KeywordIntentParser(BaseIntentParser):
    """基于关键词和正则的意图解析器。

    匹配逻辑：按规则优先级从高到低匹配，第一个命中即返回。
    未命中任何规则时返回 CHAT 意图（交给 LLM 对话）。
    """

    def __init__(self, extra_rules: list[_KeywordRule] | None = None):
        self._rules = list(_BUILTIN_RULES)
        if extra_rules:
            self._rules.extend(extra_rules)

    async def parse(self, text: str) -> Intent:
        text_stripped = text.strip()

        for rule in self._rules:
            match = rule.pattern.search(text_stripped)
            if not match:
                continue

            params: dict = {}

            # 控制类特殊处理：提取操作和设备
            if rule.action == "control_device":
                params["operation"] = match.group("op")
                params["device"] = match.group("device").strip()
            elif rule.param_extractor:
                value = match.group(rule.param_extractor)
                if value:
                    params[rule.param_extractor] = value.strip()

            intent = Intent(
                type=rule.intent_type,
                action=rule.action,
                params=params,
                confidence=0.9,
                raw_text=text_stripped,
            )
            logger.info("意图识别: '%s' → %s (action=%s, params=%s)",
                        text_stripped, intent.type.value, intent.action, intent.params)
            return intent

        # 未命中任何规则 → 普通对话
        logger.debug("意图识别: '%s' → chat (无关键词命中)", text_stripped)
        return Intent(
            type=IntentType.CHAT,
            action="",
            params={},
            confidence=1.0,
            raw_text=text_stripped,
        )
        return Intent(
            type=IntentType.CHAT,
            action="",
            params={},
            confidence=1.0,
            raw_text=text_stripped,
        )
