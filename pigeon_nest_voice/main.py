"""Pigeon Nest Voice — 应用入口。"""

import asyncio
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from pigeon_nest_voice.config.settings import settings
from pigeon_nest_voice.core.logging_config import setup_logging

# 日志系统必须在其他模块导入之前初始化
setup_logging()

from pigeon_nest_voice.api.routes import router as api_router, _session_mgr, _task_scheduler, _device_manager
from pigeon_nest_voice.core.thread_pool import ThreadPoolManager

logger = logging.getLogger(__name__)


async def _session_cleanup_loop(interval: int = 300):
    """后台定时清理过期会话（默认每5分钟）。"""
    while True:
        await asyncio.sleep(interval)
        _session_mgr.cleanup_expired()
        logger.debug("过期会话清理完成")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化资源，关闭时释放。"""
    logger.info("🕊️ %s 启动中...", settings.app_name)
    pool = ThreadPoolManager.get_instance()
    cleanup_task = asyncio.create_task(_session_cleanup_loop())

    # 启动调度系统
    await _task_scheduler.start()
    await _device_manager.start_heartbeat()

    logger.info("✅ 服务就绪: http://%s:%d", settings.host, settings.port)
    yield
    logger.info("🔄 服务关闭中...")
    cleanup_task.cancel()

    # 停止调度系统
    await _task_scheduler.stop()
    await _device_manager.stop_heartbeat()
    await _device_manager.disconnect_all()

    pool.shutdown(wait=True)
    logger.info("👋 服务已关闭")


app = FastAPI(
    title=settings.app_name,
    description="本地智能语音助手",
    version="0.1.0",
    lifespan=lifespan,
)

# 先挂载 API 路由（必须在静态文件之前，否则会被静态文件 catch-all 拦截）
app.include_router(api_router)

# 挂载前端静态文件
web_dir = Path(__file__).parent / "web"
app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")


def main():
    """启动服务。"""
    uvicorn.run(
        "pigeon_nest_voice.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
