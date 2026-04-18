"""会话管理器 — 维护对话历史和上下文。"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """单个会话。"""
    session_id: str
    messages: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    pending_task: Any = None            # PendingTask | None，任务澄清中间状态

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        self.last_active = time.time()

    def get_messages(self, max_rounds: int = 20) -> list[dict]:
        """获取最近 max_rounds 轮对话（1轮 = 1条user + 1条assistant）。"""
        max_msgs = max_rounds * 2
        if len(self.messages) <= max_msgs:
            return list(self.messages)
        return self.messages[-max_msgs:]

    def clear_pending_task(self):
        self.pending_task = None


class SessionManager:
    """会话管理器，基于内存存储。"""

    SYSTEM_PROMPT = (
        "你是鸽子窝语音助手（Pigeon Nest Voice），一个友好、专业的中文智能语音助手。"
        "请用简洁的中文回答用户的问题。"
    )

    def __init__(self, max_rounds: int = 20, expire_seconds: int = 3600):
        self._sessions: dict[str, Session] = {}
        self._max_rounds = max_rounds
        self._expire_seconds = expire_seconds

    def get_or_create(self, session_id: str | None = None) -> Session:
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            session.last_active = time.time()
            return session
        new_id = session_id or uuid.uuid4().hex[:12]
        session = Session(session_id=new_id)
        self._sessions[new_id] = session
        logger.info("新建会话: %s (当前活跃: %d)", new_id, len(self._sessions))
        return session

    def build_llm_messages(self, session: Session) -> list[dict]:
        """构建发给 LLM 的完整消息列表（含 system prompt）。"""
        msgs = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        msgs.extend(session.get_messages(self._max_rounds))
        return msgs

    def cleanup_expired(self):
        """清理过期会话。"""
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s.last_active > self._expire_seconds
        ]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.info("清理过期会话: %d 个, 剩余: %d", len(expired), len(self._sessions))
