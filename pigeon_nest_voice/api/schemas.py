"""API 请求/响应数据模型。"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求。"""
    message: str = Field(..., min_length=1, max_length=4096, description="用户消息")
    session_id: str | None = Field(None, description="会话ID，为空则自动创建")


class ChatResponse(BaseModel):
    """对话响应。"""
    reply: str = Field(..., description="助手回复")
    session_id: str = Field(..., description="会话ID")


class VoiceResponse(BaseModel):
    """语音对话响应。"""
    reply: str = Field(..., description="助手回复文本")
    session_id: str = Field(..., description="会话ID")
    recognized_text: str = Field("", description="语音识别出的文本")
    audio_base64: str | None = Field(None, description="回复语音 base64")
    audio_content_type: str = Field("audio/mpeg", description="音频 MIME 类型")


class TTSRequest(BaseModel):
    """文本转语音请求。"""
    text: str = Field(..., min_length=1, max_length=4096, description="要合成的文本")


class HealthResponse(BaseModel):
    """健康检查响应。"""
    status: str = "ok"
    app_name: str = ""
    version: str = ""
