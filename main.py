"""
PyProxyPool 主入口 — FastAPI 版本

替换原 http.server + 多进程架构，改为 FastAPI + uvicorn
保留 SIGHUP 信号处理，Dashboard 不中断
"""
import asyncio
import json
import logging
import signal
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func, select

from database import init_db, dispose_db, get_db, get_db_session
from config import get_settings, reload_settings, settings
from api.auth import verify_token
from api.routes import router, compat_router, admin_router
from api.scheduler import start_scheduler, stop_scheduler
from api.dashboard import DASHBOARD_HTML


# ---- Startup Helpers ----

logger = logging.getLogger(__name__)


async def _clean_stale_running_tasks():
    """服务启动时清理残留的 running 任务（重启后无人认领的）"""
    logger.info('检查残留任务...')
    try:
        session = await get_db_session()
        from models import ScanTask
        stmt = select(ScanTask).where(ScanTask.status == 'running')
        result = await session.execute(stmt)
        stale_tasks = result.scalars().all()
        if stale_tasks:
            from sqlalchemy import update as sa_update
            for t in stale_tasks:
                logger.warning(f'清理残留运行中任务: {t.task_id} (创建时间: {t.created_at})')
                upd = sa_update(ScanTask).where(ScanTask.id == t.id).values(
                    status='failed',
                    invalid=t.invalid + 1 if t.invalid else 1,
                )
                await session.execute(upd)
            await session.commit()
            logger.info(f'已清理 {len(stale_tasks)} 个残留任务')
        else:
            logger.info('无残留任务，一切正常')
        await session.close()
    except Exception as e:
        logger.error(f'清理残留任务时出错: {e}')
        try:
            await session.close()
        except Exception:
            pass


# ---- Logging Setup ----

def setup_logging():
    """配置日志（兼容原 config 设置）"""
    os.makedirs(os.path.dirname(settings.LOG_FILE), exist_ok=True)
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)

    console_level = getattr(logging, settings.LOG_LEVEL_CONSOLE, logging.DEBUG)
    file_level = getattr(logging, settings.LOG_LEVEL_FILE, logging.INFO)
    root_logger.setLevel(min(console_level, file_level))

    formatter = logging.Formatter(settings.LOG_FORMAT)

    console = logging.StreamHandler()
    console.setLevel(console_level)
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    if settings.LOG_ROTATE_BY_SIZE:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            settings.LOG_FILE, maxBytes=settings.LOG_MAX_BYTES,
            backupCount=settings.LOG_BACKUP_COUNT, encoding='utf-8'
        )
    else:
        from logging.handlers import TimedRotatingFileHandler
        file_handler = TimedRotatingFileHandler(
            settings.LOG_FILE, when=settings.LOG_ROTATE_WHEN, interval=1,
            backupCount=settings.LOG_BACKUP_COUNT, encoding='utf-8'
        )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


import os
os.makedirs(os.path.dirname(settings.LOG_FILE), exist_ok=True)
setup_logging()
logger = logging.getLogger(__name__)

# ---- Startup / Shutdown ----

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    启动：初始化数据库 + 启动调度器
    关闭：停止调度器 + 释放连接
    """
    logger.info('='*50)
    logger.info('PyProxyPool v3.0.0 starting...')
    logger.info(f'API: http://{settings.API_HOST}:{settings.API_PORT}')
    logger.info('='*50)

    # 初始化数据库
    await init_db()

    # 初始化 GeoIP 数据库
    from database import init_geoip
    init_geoip()

    # 清理上次启动时残留的 running 任务
    _clean_stale_running_tasks()

    # 启动调度器
    await start_scheduler()

    yield

    # 关闭
    await stop_scheduler()
    await dispose_db()

    logger.info('PyProxyPool shutdown complete')


# ---- FastAPI App ----

app = FastAPI(
    title='PyProxyPool',
    version='3.0.0',
    description='Proxy Intelligence System',
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Register routes
app.include_router(router)
app.include_router(compat_router)

# 管理 API（GeoIP）
app.include_router(admin_router)

# ---- Dashboard (保留 HTML 字符串) ----

@app.get('/', response_class=HTMLResponse)
@app.get('/dashboard', response_class=HTMLResponse)
async def dashboard():
    """返回 Dashboard HTML 页面"""
    return DASHBOARD_HTML


# ---- 日志查看（供 Dashboard 使用） ----

@app.get('/logs')
async def get_logs(lines: int = Query(50, ge=1, le=200)):
    """返回最近的日志行"""
    log_file = settings.LOG_FILE
    try:
        if os.path.isfile(log_file):
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
            return ''.join(all_lines[-lines:])
    except Exception as e:
        return f'读取日志失败: {e}'
    return '暂无日志'


# ---- WebSocket ----

_ws_clients = set()

@app.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点 — 保留原有逻辑"""
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info(f'WebSocket connected: {len(_ws_clients)} clients')

    try:
        while True:
            # 接收消息（可选）
            data = await websocket.receive_text()
            logger.debug(f'WS message: {data}')

            # 回显（简单实现，保持连接活跃）
            await websocket.send_text(json.dumps({
                'type': 'ping',
                'timestamp': datetime.utcnow().isoformat(),
            }))
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)
        logger.info(f'WebSocket disconnected: {len(_ws_clients)} clients')
    except Exception as e:
        logger.error(f'WebSocket error: {e}')
        _ws_clients.discard(websocket)


# ---- Signal Handlers ----

async def _handle_sighup(signum, frame):
    """SIGHUP — 热重载配置"""
    logger.info('SIGHUP received, reloading config...')
    try:
        reload_settings()
        setup_logging()
        logger.info('Config reloaded via SIGHUP')
    except Exception as e:
        logger.error(f'Config reload failed: {e}')


# ---- CLI Entry ----

def main():
    """命令行入口"""
    import argparse
    parser = argparse.ArgumentParser(description='PyProxyPool v3.0.0 - Proxy Intelligence System')
    parser.add_argument('--api-only', action='store_true', help='只启动API服务')
    parser.add_argument('--port', type=int, default=None, help='API端口')
    args = parser.parse_args()

    if args.port:
        settings.API_PORT = args.port

    if args.api_only:
        # 只启动 API（不调度器）
        @asynccontextmanager
        async def api_only_lifespan(app):
            await init_db()
            yield
            await dispose_db()

        api_app = FastAPI(lifespan=api_only_lifespan)
        api_app.include_router(router)
        api_app.include_router(compat_router)
        api_app.add_middleware(
            CORSMiddleware, allow_origins=['*'], allow_methods=['*'],
            allow_headers=['*'], allow_credentials=True,
        )

        @api_app.get('/', response_class=HTMLResponse)
        async def _dashboard():
            return DASHBOARD_HTML

        uvicorn.run(
            api_app,
            host=settings.API_HOST,
            port=settings.API_PORT,
            log_level='info',
        )
    else:
        # 完整模式（API + 调度器）
        uvicorn.run(
            app,
            host=settings.API_HOST,
            port=settings.API_PORT,
            log_level='info',
        )


if __name__ == '__main__':
    main()