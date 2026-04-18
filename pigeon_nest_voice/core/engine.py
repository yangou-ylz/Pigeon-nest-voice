"""核心流水线引擎 — 编排对话/任务处理流程。"""

import logging

from pigeon_nest_voice.services.llm.base import BaseLLM
from pigeon_nest_voice.core.session import SessionManager
from pigeon_nest_voice.intelligence.intent.base import BaseIntentParser, Intent, IntentType, PendingTask
from pigeon_nest_voice.intelligence.rules.engine import RuleEngine, Rule

logger = logging.getLogger(__name__)


class PipelineEngine:
    """流水线引擎: 文字 → 意图解析 → 对话/任务分支。

    支持多轮澄清:
    ┌──────────┐     ┌────────────────┐
    │ 用户输入  │ ──→ │ 有待澄清任务？  │
    └──────────┘     └────────────────┘
                          │          │
                       有待澄清     无待澄清
                          │          │
                          ▼          ▼
                     合并参数     意图解析
                     重新检查     → 分支处理
                          │
                    ┌─────┴─────┐
                    ▼           ▼
               参数完整     仍有缺失
               → 执行      → 继续追问
    """

    def __init__(
        self,
        llm: BaseLLM,
        session_mgr: SessionManager,
        intent_parser: BaseIntentParser,
        rule_engine: RuleEngine,
    ):
        self.llm = llm
        self.session_mgr = session_mgr
        self.intent_parser = intent_parser
        self.rule_engine = rule_engine

    async def process_text(self, text: str, session_id: str | None = None) -> tuple[str, str]:
        """处理文字输入，返回 (回复文字, session_id)。"""
        session = self.session_mgr.get_or_create(session_id)
        logger.info("收到输入: '%s' (session=%s)", text[:80], session.session_id)

        # ── 优先处理待澄清任务 ──
        if session.pending_task is not None:
            logger.debug("进入澄清流程 (待补字段: %s)", session.pending_task.asked_field)
            reply = self._handle_clarification(text, session)
            return reply, session.session_id

        # ── 正常流程: 意图解析 ──
        intent = await self.intent_parser.parse(text)

        if intent.is_task:
            logger.info("→ 任务分支: action=%s, params=%s", intent.action, intent.params)
            reply = self._handle_task(intent, session)
        else:
            logger.info("→ 对话分支: 交给LLM")
            reply = await self._handle_chat(text, session)

        logger.debug("回复: '%s'", reply[:100] if reply else "")
        return reply, session.session_id

    async def _handle_chat(self, text: str, session) -> str:
        """对话分支: 走 LLM。"""
        session.add_message("user", text)
        messages = self.session_mgr.build_llm_messages(session)
        reply = await self.llm.chat(messages)
        session.add_message("assistant", reply)
        return reply

    def _handle_task(self, intent: Intent, session) -> str:
        """任务分支: 走规则引擎，检查参数完整性。"""
        rule = self.rule_engine.match(intent.action, intent.params)
        if not rule:
            return f"已识别任务「{intent.action}」，参数: {intent.params}，但暂无对应规则。"

        # 检查必填参数
        missing = rule.check_missing_params(intent.params)
        if missing:
            return self._start_clarification(intent, rule, missing, session)

        # 参数完整 → 执行
        return self.rule_engine.execute_reply(rule, intent.params)

    def _start_clarification(self, intent: Intent, rule: Rule,
                             missing: list, session) -> str:
        """参数不完整，挂起任务并追问用户。"""
        first_missing = missing[0]
        pending = PendingTask(
            intent=intent,
            missing_fields=[m.name for m in missing],
            asked_field=first_missing.name,
            attempts=1,
        )
        session.pending_task = pending

        prompt = first_missing.clarify_prompt or f"请补充 {first_missing.name} 信息。"
        logger.info("任务澄清: %s → 缺少 %s，追问用户",
                    rule.name, [m.name for m in missing])
        return prompt

    def _handle_clarification(self, text: str, session) -> str:
        """处理用户对澄清问题的回复。"""
        pending: PendingTask = session.pending_task
        user_reply = text.strip()

        # 用户想取消
        if user_reply in ("取消", "算了", "不要了", "不用了", "没事了"):
            session.clear_pending_task()
            return "好的，已取消任务。"

        # 将回复填入缺失字段
        pending.intent.params[pending.asked_field] = user_reply

        # 重新检查规则
        rule = self.rule_engine.match(pending.intent.action)
        if not rule:
            session.clear_pending_task()
            return "抱歉，找不到对应的规则了。"

        missing = rule.check_missing_params(pending.intent.params)

        if not missing:
            # 所有参数已补全 → 执行任务
            session.clear_pending_task()
            logger.info("任务澄清完成: %s, params=%s",
                        rule.name, pending.intent.params)
            return self.rule_engine.execute_reply(rule, pending.intent.params)

        # 还有缺失 → 继续追问
        pending.attempts += 1
        if pending.attempts > PendingTask.MAX_ATTEMPTS:
            session.clear_pending_task()
            return "多次追问仍无法获取完整信息，任务已取消。如需帮忙，请重新描述您的需求。"

        next_missing = missing[0]
        pending.asked_field = next_missing.name
        pending.missing_fields = [m.name for m in missing]

        prompt = next_missing.clarify_prompt or f"请补充 {next_missing.name} 信息。"
        return prompt
