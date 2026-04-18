"""会话管理器 — 维护对话历史和上下文。"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 当消息数超过此阈值时，将早期消息压缩为摘要
_SUMMARY_THRESHOLD = 30
# 压缩后保留的最近消息轮数
_KEEP_RECENT_ROUNDS = 8


@dataclass
class Session:
    """单个会话。"""
    session_id: str
    messages: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    pending_task: Any = None            # PendingTask | None，任务澄清中间状态
    summary: str = ""                   # 早期对话摘要（压缩后产生）
    turn_count: int = 0                 # 总交互轮数

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        self.last_active = time.time()
        if role == "user":
            self.turn_count += 1

    def get_messages(self, max_rounds: int = 20) -> list[dict]:
        """获取最近 max_rounds 轮对话（1轮 = 1条user + 1条assistant）。"""
        max_msgs = max_rounds * 2
        if len(self.messages) <= max_msgs:
            return list(self.messages)
        return self.messages[-max_msgs:]

    def needs_summary(self) -> bool:
        """当消息数超过阈值时需要压缩。"""
        return len(self.messages) > _SUMMARY_THRESHOLD

    def compress(self, new_summary: str):
        """压缩历史: 保留最近几轮，其余合入 summary。"""
        keep_count = _KEEP_RECENT_ROUNDS * 2
        self.summary = new_summary
        self.messages = self.messages[-keep_count:]
        logger.info("会话 %s 已压缩, 摘要长度=%d, 剩余消息=%d",
                     self.session_id, len(new_summary), len(self.messages))

    def get_history_text(self, max_msgs: int = 40) -> str:
        """获取可读的对话历史文本（用于摘要生成）。"""
        msgs = self.messages[:max_msgs] if len(self.messages) > max_msgs else self.messages
        lines = []
        for m in msgs:
            prefix = "用户" if m["role"] == "user" else "助手"
            lines.append(f"{prefix}: {m['content']}")
        return "\n".join(lines)

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

    def get_session(self, session_id: str) -> Session | None:
        """获取已有会话，不存在返回 None。"""
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        """删除指定会话。"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info("删除会话: %s", session_id)
            return True
        return False

    def list_sessions(self) -> list[dict]:
        """列出所有活跃会话的摘要信息。"""
        result = []
        for sid, s in self._sessions.items():
            # 取最后一条用户消息作为预览
            preview = ""
            for m in reversed(s.messages):
                if m["role"] == "user":
                    preview = m["content"][:50]
                    break
            result.append({
                "session_id": sid,
                "turn_count": s.turn_count,
                "message_count": len(s.messages),
                "has_summary": bool(s.summary),
                "preview": preview,
                "created_at": s.created_at,
                "last_active": s.last_active,
            })
        result.sort(key=lambda x: x["last_active"], reverse=True)
        return result

    def build_llm_messages(self, session: Session) -> list[dict]:
        """构建发给 LLM 的完整消息列表（含 system prompt + 摘要）。"""
        msgs = [{"role": "system", "content": self.SYSTEM_PROMPT}]

        # 如有历史摘要，注入上下文
        if session.summary:
            msgs.append({
                "role": "system",
                "content": f"以下是之前对话的摘要，请参考：\n{session.summary}",
            })

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
