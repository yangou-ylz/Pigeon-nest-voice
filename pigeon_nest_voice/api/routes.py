"""API 路由定义。"""

import base64
import logging
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import Response

from pigeon_nest_voice.api.schemas import (
    ChatRequest, ChatResponse, HealthResponse,
    VoiceResponse, TTSRequest,
)
from pigeon_nest_voice.config.settings import settings
from pigeon_nest_voice.core.engine import PipelineEngine
from pigeon_nest_voice.core.session import SessionManager
from pigeon_nest_voice.services.llm.deepseek import DeepSeekLLM
from pigeon_nest_voice.intelligence.intent.keyword_parser import KeywordIntentParser
from pigeon_nest_voice.intelligence.rules.engine import RuleEngine
from pigeon_nest_voice.plugins.manager import PluginManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# ── 全局实例（应用生命周期内复用） ──
_session_mgr = SessionManager()
_llm = DeepSeekLLM()
_intent_parser = KeywordIntentParser()
_rule_engine = RuleEngine(
    rules_dir=Path(__file__).parent.parent.parent / "rules_config"
)
_plugin_mgr = PluginManager()
_plugin_mgr.auto_discover()
_engine = PipelineEngine(
    llm=_llm,
    session_mgr=_session_mgr,
    intent_parser=_intent_parser,
    rule_engine=_rule_engine,
    plugin_manager=_plugin_mgr,
)

# ── STT / TTS（可选依赖，缺失时仅语音功能不可用） ──
_stt = None
_tts = None

try:
    from pigeon_nest_voice.services.stt.whisper_stt import WhisperSTT
    _stt = WhisperSTT()
except ImportError:
    logger.warning("faster-whisper 未安装，语音识别功能不可用。pip install faster-whisper")

try:
    from pigeon_nest_voice.services.tts.edge_tts_service import EdgeTTSService
    _tts = EdgeTTSService()
except ImportError:
    logger.warning("edge-tts 未安装，语音合成功能不可用。pip install edge-tts")


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        version="0.1.0",
    )


@router.get("/plugins")
async def list_plugins():
    """列出所有已加载的插件。"""
    plugins = []
    for name, plugin in _plugin_mgr._plugins.items():
        plugins.append({
            "name": name,
            "description": plugin.description,
            "actions": plugin.actions,
        })
    return {"plugins": plugins, "total": len(plugins)}


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    logger.info("[POST /chat] message='%s' session=%s", req.message[:60], req.session_id)
    t0 = time.perf_counter()
    try:
        reply, session_id = await _engine.process_text(
            text=req.message,
            session_id=req.session_id,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("[POST /chat] 完成 [%.0fms] reply=%d字", elapsed, len(reply))
        return ChatResponse(reply=reply, session_id=session_id)
    except Exception as e:
        logger.exception("[POST /chat] 失败")
        raise HTTPException(status_code=500, detail=f"对话处理失败: {e}")


@router.post("/voice", response_model=VoiceResponse)
async def voice(
    audio: UploadFile = File(...),
    session_id: str | None = Form(None),
):
    """语音对话: 上传音频 → STT → Pipeline → TTS → 返回文字+语音。"""
    if _stt is None:
        raise HTTPException(status_code=503, detail="语音识别服务未初始化")

    logger.info("[POST /voice] session=%s", session_id)
    t0 = time.perf_counter()
    try:
        audio_bytes = await audio.read()
        logger.info("[POST /voice] 音频大小: %.1fKB", len(audio_bytes) / 1024)
        if len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail="音频数据为空")

        # STT: 音频 → 文字
        recognized = await _stt.transcribe(audio_bytes)
        if not recognized:
            return VoiceResponse(
                reply="抱歉，没有听清，请再说一次。",
                session_id=session_id or "",
                recognized_text="",
            )

        # Pipeline: 文字 → 回复
        reply, sid = await _engine.process_text(recognized, session_id)

        # TTS: 回复 → 语音（如果 TTS 可用）
        audio_b64 = None
        content_type = "audio/mpeg"
        if _tts is not None:
            tts_result = await _tts.synthesize(reply)
            audio_b64 = base64.b64encode(tts_result.audio_bytes).decode()
            content_type = tts_result.content_type

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("[POST /voice] 完成 [%.0fms] 识别='%s' reply=%d字",
                    elapsed, recognized[:40], len(reply))
        return VoiceResponse(
            reply=reply,
            session_id=sid,
            recognized_text=recognized,
            audio_base64=audio_b64,
            audio_content_type=content_type,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[POST /voice] 失败")
        raise HTTPException(status_code=500, detail=f"语音处理失败: {e}")


@router.post("/tts")
async def tts(req: TTSRequest):
    """文字转语音: 返回 MP3 音频流。"""
    if _tts is None:
        raise HTTPException(status_code=503, detail="语音合成服务未初始化")

    try:
        result = await _tts.synthesize(req.text)
        return Response(
            content=result.audio_bytes,
            media_type=result.content_type,
            headers={"Content-Disposition": "inline; filename=speech.mp3"},
        )
    except Exception as e:
        logger.exception("TTS error")
        raise HTTPException(status_code=500, detail=f"语音合成失败: {e}")


# ── 会话管理 ──

@router.get("/sessions")
async def list_sessions():
    """列出所有活跃会话。"""
    return {"sessions": _session_mgr.list_sessions()}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """获取指定会话的详情和历史消息。"""
    session = _session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "session_id": session.session_id,
        "turn_count": session.turn_count,
        "message_count": len(session.messages),
        "has_summary": bool(session.summary),
        "summary": session.summary or "",
        "messages": session.messages[-40:],  # 最多返回最近40条
        "created_at": session.created_at,
        "last_active": session.last_active,
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除指定会话。"""
    if _session_mgr.delete_session(session_id):
        return {"status": "ok", "message": f"会话 {session_id} 已删除"}
    raise HTTPException(status_code=404, detail="会话不存在")
