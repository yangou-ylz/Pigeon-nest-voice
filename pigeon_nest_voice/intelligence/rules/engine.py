"""规则引擎 — 加载 YAML 规则配置，根据意图匹配动作。"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class RuleAction:
    """规则匹配后要执行的动作。"""
    type: str                           # reply / http_call / ...
    config: dict = field(default_factory=dict)


@dataclass
class RequiredParam:
    """规则要求的必填参数。"""
    name: str                           # 参数名
    clarify_prompt: str = ""            # 追问提示语
    validator: str = ""                 # 验证器名（预留，如 "non_empty"）


@dataclass
class Rule:
    """一条规则。"""
    name: str
    description: str = ""
    priority: int = 0
    enabled: bool = True
    intent_match: str = ""              # 匹配的意图 action 名
    actions: list[RuleAction] = field(default_factory=list)
    fallback_message: str = ""
    required_params: list[RequiredParam] = field(default_factory=list)

    def check_missing_params(self, params: dict) -> list[RequiredParam]:
        """检查哪些必填参数缺失或为空。"""
        missing = []
        for rp in self.required_params:
            val = params.get(rp.name, "")
            if not val or not str(val).strip():
                missing.append(rp)
        return missing


class RuleEngine:
    """YAML 驱动的规则引擎。

    加载 rules_config/ 下的 YAML 文件，根据意图 action 匹配规则，
    返回对应的动作列表。
    """

    def __init__(self, rules_dir: str | Path | None = None):
        self._rules: list[Rule] = []
        if rules_dir:
            self.load_rules(Path(rules_dir))

    def load_rules(self, rules_dir: Path):
        """加载目录下所有 YAML 规则文件。"""
        if not rules_dir.exists():
            logger.warning("规则目录不存在: %s", rules_dir)
            return

        self._rules.clear()
        for yaml_file in sorted(rules_dir.glob("*.yaml")):
            self._load_file(yaml_file)

        # 按优先级降序排列
        self._rules.sort(key=lambda r: r.priority, reverse=True)
        logger.info("规则引擎: 已加载 %d 条规则", len(self._rules))

    def _load_file(self, path: Path):
        """解析单个 YAML 规则文件。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data or "rules" not in data:
                return
            for raw in data["rules"]:
                rule = Rule(
                    name=raw.get("name", ""),
                    description=raw.get("description", ""),
                    priority=raw.get("priority", 0),
                    enabled=raw.get("enabled", True),
                    intent_match=raw.get("intent_match", ""),
                    fallback_message=raw.get("fallback", {}).get("message", ""),
                )
                for act in raw.get("actions", []):
                    rule.actions.append(RuleAction(
                        type=act.get("type", ""),
                        config={k: v for k, v in act.items() if k != "type"},
                    ))
                for rp in raw.get("required_params", []):
                    rule.required_params.append(RequiredParam(
                        name=rp.get("name", ""),
                        clarify_prompt=rp.get("clarify_prompt", ""),
                        validator=rp.get("validator", ""),
                    ))
                self._rules.append(rule)
                logger.debug("加载规则: %s (priority=%d)", rule.name, rule.priority)
        except Exception:
            logger.exception("加载规则文件失败: %s", path)

    def match(self, action: str, params: dict | None = None) -> Rule | None:
        """根据意图 action 名匹配第一条命中规则。"""
        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.intent_match == action:
                logger.info("规则命中: %s → %s", action, rule.name)
                return rule
        return None

    def execute_reply(self, rule: Rule, params: dict) -> str:
        """执行规则中的 reply 类型动作，渲染模板变量，返回回复文本。"""
        for act in rule.actions:
            if act.type == "reply":
                template = act.config.get("message", "")
                return self._render_template(template, params)
        return rule.fallback_message or f"已识别任务: {rule.name}"

    @staticmethod
    def _render_template(template: str, params: dict) -> str:
        """渲染 {{variable}} 模板变量。"""
        def _replacer(m: re.Match) -> str:
            key = m.group(1).strip()
            # 支持 {{var|default:'值'}}
            if "|default:" in key:
                var, default = key.split("|default:", 1)
                return str(params.get(var.strip(), default.strip().strip("'\"")))
            return str(params.get(key, f"{{{{{key}}}}}"))
        return re.sub(r"\{\{(.+?)\}\}", _replacer, template)

    @property
    def rule_count(self) -> int:
        return len(self._rules)
