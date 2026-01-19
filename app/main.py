"""
FastAPI main application entry point
谁是卧底游戏平台主应用入口 - 增强安全功能
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import init_db, close_db, db_manager
from app.core.redis_client import init_redis, close_redis, redis_manager
from app.api.v1.api import api_router
from app.middleware.security import SecurityMiddleware, LoggingMiddleware
from app.utils.system_health import health_monitor
from app.services.background_tasks import start_background_tasks, stop_background_tasks
import logging
import os

# Configure logging - 同时输出到控制台和文件
log_level = getattr(logging, settings.LOG_LEVEL.upper())
log_format = settings.LOG_FORMAT

# 确保日志目录存在
log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'app.log')

# 创建根日志器
logging.basicConfig(
    level=log_level,
    format=log_format,
    handlers=[
        logging.StreamHandler(),  # 控制台输出
        logging.FileHandler(log_file, encoding='utf-8')  # 文件输出
    ]
)
logger = logging.getLogger(__name__)

# 减少 SQLAlchemy 和 httpx 的日志噪音
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def _process_ai_turn_on_recovery(game_id: str):
    """恢复游戏后处理 AI 回合"""
    try:
        from app.core.database import db_manager
        from app.services.game import GameEngine

        logger.info(f"[AI_RECOVERY] Starting AI turn processing for recovered game {game_id}")

        async with db_manager.get_session() as session:
            game_engine = GameEngine(session)
            result = await game_engine.process_ai_turns(game_id)
            logger.info(f"[AI_RECOVERY] AI turn completed for game {game_id}, result: {result}")

    except Exception as e:
        logger.error(f"[AI_RECOVERY] Failed to process AI turn for game {game_id}: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events with enhanced security and 2C2G optimizations"""
    # Startup
    logger.info("Starting 谁是卧底游戏平台 with enhanced security and 2C2G optimizations...")
    
    # Performance optimization task handle
    optimization_task = None
    
    try:
        # Initialize database with enhanced connection management
        await init_db()
        await init_redis()
        
        # Recover active games from previous session
        try:
            from app.services.game_recovery import recover_all_active_games
            from app.schemas.game import GamePhase
            recovered_games = await recover_all_active_games()
            logger.info(f"Recovered {len(recovered_games)} active games from previous session")

            # 恢复后自动处理等待中的 AI 回合
            for game_state in recovered_games:
                try:
                    logger.info(f"[RECOVERY_DEBUG] Game {game_state.id}: phase={game_state.current_phase}, speaker={game_state.current_speaker}")
                    logger.info(f"[RECOVERY_DEBUG] Game {game_state.id}: players={[{'id': p.id, 'name': p.username, 'is_ai': p.is_ai} for p in game_state.players]}")

                    # 检查是否在发言阶段且当前发言者是 AI
                    if game_state.current_phase == GamePhase.SPEAKING:
                        logger.info(f"[RECOVERY_DEBUG] Game {game_state.id} is in SPEAKING phase")
                        if game_state.current_speaker:
                            current_player = next(
                                (p for p in game_state.players if p.id == game_state.current_speaker),
                                None
                            )
                            logger.info(f"[RECOVERY_DEBUG] Game {game_state.id}: current_player={current_player}")
                            if current_player:
                                logger.info(f"[RECOVERY_DEBUG] Game {game_state.id}: current_player.is_ai={current_player.is_ai}")
                                if current_player.is_ai:
                                    # 异步触发 AI 发言处理
                                    import asyncio
                                    asyncio.create_task(_process_ai_turn_on_recovery(game_state.id))
                                    logger.info(f"Triggered AI turn for recovered game: {game_state.id}")
                                else:
                                    logger.info(f"[RECOVERY_DEBUG] Game {game_state.id}: current speaker is human, waiting for input")
                            else:
                                logger.warning(f"[RECOVERY_DEBUG] Game {game_state.id}: current_speaker not found in players list")
                        else:
                            logger.info(f"[RECOVERY_DEBUG] Game {game_state.id}: no current_speaker set")
                    else:
                        logger.info(f"[RECOVERY_DEBUG] Game {game_state.id}: not in SPEAKING phase, phase is {game_state.current_phase}")
                except Exception as e:
                    logger.error(f"Failed to trigger AI turn for game {game_state.id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Failed to recover active games: {e}")
        
        # Start health monitoring for system stability
        # 开发环境暂时禁用健康监控，避免误报
        if settings.ENVIRONMENT not in ["development", "testing"]:
            await health_monitor.start_monitoring(interval=60)
        
        # Start background tasks
        await start_background_tasks()
        
        # Start performance auto-optimization for 2C2G environment
        # 开发环境暂时禁用性能自动优化
        if settings.ENVIRONMENT not in ["development", "testing"]:
            try:
                from app.utils.performance_optimizer import start_auto_optimization
                import asyncio
                optimization_task = asyncio.create_task(start_auto_optimization(interval_seconds=300))
                logger.info("Performance auto-optimization started for 2C2G environment")
            except Exception as e:
                logger.warning(f"Failed to start performance optimization: {e}")
        
        logger.info("Application startup completed successfully with security and 2C2G optimizations")
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    
    try:
        # Stop performance optimization
        if optimization_task:
            optimization_task.cancel()
            try:
                await optimization_task
            except asyncio.CancelledError:
                pass
        
        await stop_background_tasks()
        health_monitor.stop_monitoring()
        await close_redis()
        await close_db()
        
        logger.info("Application shutdown completed")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


app = FastAPI(
    title="谁是卧底",
    description="Undercover Game Platform - 在线多人谁是卧底游戏 (Enhanced Security)",
    version="1.0.0",
    lifespan=lifespan,
    # 禁用尾部斜杠重定向，避免 307 Redirect 导致 Authorization header 丢失
    redirect_slashes=False
)

# Security middleware (add first for maximum coverage)
app.add_middleware(SecurityMiddleware, enable_rate_limiting=True)
app.add_middleware(LoggingMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "谁是卧底游戏平台 API", 
        "status": "running",
        "security": "enhanced",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Detailed health check with enhanced monitoring"""
    try:
        from app.utils.system_health import get_system_status
        from app.services.game_recovery import get_recovery_status
        from app.utils.resource_monitor import resource_monitor
        
        # Get comprehensive system status
        health_report = await get_system_status()
        
        # Get game recovery status
        recovery_status = await get_recovery_status()
        
        # Get resource usage
        resource_usage = resource_monitor.get_current_usage()
        
        return {
            "status": health_report.get("overall_status", "unknown"),
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
            "security_features": "enabled",
            "database": health_report.get("database", {}),
            "redis": health_report.get("redis", {}),
            "resources": health_report.get("resources", {}),
            "game_recovery": recovery_status,
            "timestamp": health_report.get("timestamp"),
            "health_checks": {
                "database": health_report.get("database", {}).get("status", "unknown"),
                "redis": health_report.get("redis", {}).get("status", "unknown"),
                "resources": health_report.get("resources", {}).get("status", "unknown")
            },
            "resource_usage": {
                "memory_mb": resource_usage.get("memory_mb", 0),
                "cpu_percent": resource_usage.get("cpu_percent", 0)
            },
            "limits": {
                "max_memory_mb": settings.MAX_MEMORY_MB,
                "max_cpu_percent": settings.MAX_CPU_PERCENT
            }
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error",
            "version": "1.0.0",
            "error": str(e)
        }


@app.get("/resources")
async def resources_status():
    """Resource monitoring endpoint for 2C2G environment"""
    try:
        from app.utils.resource_monitor import resource_monitor
        
        usage = resource_monitor.get_current_usage()
        available = resource_monitor.is_resource_available(required_memory_mb=10)
        
        return {
            "usage": usage,
            "available": available,
            "optimized_for": "2C2G server environment"
        }
        
    except Exception as e:
        logger.error(f"Resource status check failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/security-status")
async def security_status():
    """Security system status endpoint"""
    try:
        from app.utils.security import rate_limiter
        from app.utils.session import session_manager
        
        # Get security component status
        active_sessions = await session_manager.get_active_sessions_count()
        
        return {
            "security_middleware": "active",
            "rate_limiting": "enabled",
            "input_validation": "enabled",
            "session_security": "enhanced",
            "encryption": "enabled",
            "active_sessions": active_sessions,
            "environment": settings.ENVIRONMENT
        }
        
    except Exception as e:
        logger.error(f"Security status check failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }