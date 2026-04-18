"""全局配置管理，使用 pydantic-settings 从环境变量/.env 读取配置。"""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """应用配置，所有敏感信息通过 .env 注入。"""

    # ── 服务 ──
    app_name: str = "Pigeon Nest Voice"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # ── LLM ──
    llm_provider: str = "deepseek"          # 当前使用的LLM提供者
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ── STT (Whisper) ──
    stt_provider: str = "whisper"
    whisper_model: str = "medium"            # tiny / base / small / medium / large
    whisper_device: str = "auto"             # auto / cpu / cuda
    whisper_compute_type: str = "auto"       # auto / float16 / int8 / int8_float16

    # ── TTS (Edge) ──
    tts_provider: str = "edge"
    edge_tts_voice: str = "zh-CN-XiaoxiaoNeural"  # 中文女声

    # ── 线程池 ──
    thread_pool_max_workers: int = 8

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


# 全局单例
settings = Settings()
