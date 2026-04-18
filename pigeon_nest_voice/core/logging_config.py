"""统一日志配置模块。

设计目标:
1. 方便人看 — 彩色终端输出, 对齐格式, 中文标签
2. 高效不冗余 — 按模块分级, 关键节点精准打点
3. 信息量大且明确 — 结构化上下文(耗时/参数/结果), 异常含完整 traceback
4. 覆盖全面 — API请求/响应、Pipeline流转、STT/TTS/LLM 调用、会话管理

用法:
    from pigeon_nest_voice.core.logging_config import setup_logging
    setup_logging()  # 在 main.py 调用一次即可
"""

import logging
import logging.handlers
import sys
import time
from pathlib import Path
from typing import Any

from pigeon_nest_voice.config.settings import settings

# ── 日志目录 ──
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────
#  彩色终端 Formatter
# ─────────────────────────────────────────────
class ColorFormatter(logging.Formatter):
    """终端彩色日志格式器, 按级别着色, 模块名缩短。"""

    _COLORS = {
        logging.DEBUG:    "\033[36m",   # 青
        logging.INFO:     "\033[32m",   # 绿
        logging.WARNING:  "\033[33m",   # 黄
        logging.ERROR:    "\033[31m",   # 红
        logging.CRITICAL: "\033[1;31m", # 粗红
    }
    _RESET = "\033[0m"
    _GREY = "\033[90m"

    # 模块名缩写映射, 减少宽度
    _MODULE_SHORT = {
        "pigeon_nest_voice.": "",
        "services.stt.whisper_stt": "stt",
        "services.tts.edge_tts_service": "tts",
        "services.llm.deepseek": "llm",
        "intelligence.intent.keyword_parser": "intent",
        "intelligence.rules.engine": "rules",
        "core.engine": "pipeline",
        "core.session": "session",
        "core.thread_pool": "pool",
        "api.routes": "api",
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self._COLORS.get(record.levelno, "")
        # 缩短模块名
        name = record.name
        for long, short in self._MODULE_SHORT.items():
            if name.startswith(long) or name.endswith(long.lstrip(".")):
                name = short or name.replace("pigeon_nest_voice.", "")
                break
        else:
            name = name.replace("pigeon_nest_voice.", "")

        ts = self.formatTime(record, "%H:%M:%S")
        ms = int(record.msecs)
        level = record.levelname[0]  # I/D/W/E/C 单字母

        msg = record.getMessage()
        line = f"{self._GREY}{ts}.{ms:03d}{self._RESET} {color}{level}{self._RESET} [{color}{name}{self._RESET}] {msg}"

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            line += f"\n{self._GREY}{record.exc_text}{self._RESET}"
        return line


# ─────────────────────────────────────────────
#  文件日志 Formatter (结构化, 无颜色)
# ─────────────────────────────────────────────
FILE_FORMAT = "%(asctime)s │ %(levelname)-5s │ %(name)s │ %(message)s"
FILE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ─────────────────────────────────────────────
#  setup_logging — 唯一入口
# ─────────────────────────────────────────────
def setup_logging(level: str | None = None):
    """初始化全局日志系统。

    Args:
        level: 覆盖日志级别 (DEBUG/INFO/WARNING/ERROR), 默认根据 settings.debug 决定
    """
    root_level = level or ("DEBUG" if settings.debug else "INFO")

    root = logging.getLogger()
    root.setLevel(root_level)
    # 清除已有 handler (避免重复)
    root.handlers.clear()

    # ── 终端 handler ──
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(root_level)
    console.setFormatter(ColorFormatter())
    root.addHandler(console)

    # ── 文件 handler: 按天轮转, 保留 7 天 ──
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "app.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, FILE_DATE_FORMAT))
    root.addHandler(file_handler)

    # ── 错误专用文件: 只记 WARNING+ ──
    err_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "error.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(logging.Formatter(FILE_FORMAT, FILE_DATE_FORMAT))
    root.addHandler(err_handler)

    # ── 第三方库降噪 ──
    for noisy in ("httpx", "httpcore", "urllib3", "faster_whisper",
                   "uvicorn.access", "uvicorn.error", "hpack", "h11"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # ── uvicorn 基础日志保留 INFO ──
    logging.getLogger("uvicorn").setLevel(logging.INFO)

    logging.getLogger("pigeon_nest_voice").info(
        "日志系统就绪 — 级别=%s, 终端+文件(%s)", root_level, LOG_DIR,
    )


# ─────────────────────────────────────────────
#  计时上下文管理器 — 用于测量关键操作耗时
# ─────────────────────────────────────────────
class LogTimer:
    """测量代码块执行耗时并自动记录日志。

    用法:
        with LogTimer(logger, "STT识别"):
            result = model.transcribe(audio)
    """

    def __init__(self, logger_inst: logging.Logger, operation: str,
                 level: int = logging.INFO, **extra: Any):
        self._logger = logger_inst
        self._op = operation
        self._level = level
        self._extra = extra
        self._start: float = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        if exc_type:
            self._logger.error("%s 失败 [%.0fms] — %s: %s",
                               self._op, elapsed_ms, exc_type.__name__, exc_val)
        else:
            parts = [f"{self._op} 完成 [{elapsed_ms:.0f}ms]"]
            for k, v in self._extra.items():
                parts.append(f"{k}={v}")
            self._logger.log(self._level, " ".join(parts))
        self.elapsed_ms = elapsed_ms
        return False
