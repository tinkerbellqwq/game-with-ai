#!/usr/bin/env python3
"""
2C2G optimized startup script
2C2G环境优化启动脚本 - 增强版
"""

import uvicorn
import logging
import sys
import gc
import os
import asyncio
from typing import Dict, Any
from app.core.config import settings

# Configure logging for 2C2G environment
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format=settings.LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app.log", mode="a", encoding="utf-8")
    ]
)

logger = logging.getLogger(__name__)


def configure_gc_for_2c2g():
    """
    Configure garbage collection for 2C2G environment
    配置2C2G环境的垃圾回收
    """
    # Set aggressive GC thresholds for memory-constrained environment
    # Default is (700, 10, 10), we use more aggressive settings
    gc.set_threshold(500, 10, 5)
    
    # Force initial garbage collection
    gc.collect()
    
    logger.info(f"GC configured for 2C2G: thresholds={gc.get_threshold()}")


def get_uvicorn_config() -> Dict[str, Any]:
    """
    Get optimized Uvicorn configuration for 2C2G
    获取2C2G优化的Uvicorn配置
    """
    return {
        "host": settings.HOST,
        "port": settings.PORT,
        "workers": settings.WORKERS,  # Single worker for 2C2G
        "reload": settings.DEBUG and settings.ENVIRONMENT == "development",
        "access_log": True,
        "log_level": settings.LOG_LEVEL.lower(),
        # 2C2G specific optimizations
        "loop": "asyncio",  # Use asyncio loop for better memory efficiency
        "http": "h11",  # Use h11 for lower memory footprint
        "ws": "websockets",  # Use websockets library
        "lifespan": "on",  # Enable lifespan events
        # Connection limits for 2C2G
        "limit_concurrency": settings.MAX_WEBSOCKET_CONNECTIONS,
        "limit_max_requests": 5000,  # Restart worker after 5000 requests to prevent memory leaks
        "timeout_keep_alive": 30,
        "timeout_notify": 30,
        # Memory optimizations
        "backlog": 128,  # Reduced backlog for memory efficiency
        # WebSocket optimizations
        "ws_max_size": 1048576,  # 1MB max WebSocket message
        "ws_ping_interval": 30,
        "ws_ping_timeout": 10,
    }


async def check_system_resources() -> bool:
    """
    Check system resources before startup
    启动前检查系统资源
    """
    try:
        import psutil
        
        # Check memory
        memory = psutil.virtual_memory()
        available_mb = memory.available / 1024 / 1024
        total_mb = memory.total / 1024 / 1024
        
        logger.info(f"System memory: {available_mb:.0f}MB available / {total_mb:.0f}MB total")
        
        if available_mb < 500:
            logger.warning(f"Low memory warning: only {available_mb:.0f}MB available")
            return False
        
        # Check CPU
        cpu_count = psutil.cpu_count()
        cpu_percent = psutil.cpu_percent(interval=1)
        
        logger.info(f"CPU: {cpu_count} cores, {cpu_percent}% usage")
        
        if cpu_percent > 80:
            logger.warning(f"High CPU usage warning: {cpu_percent}%")
        
        return True
        
    except ImportError:
        logger.warning("psutil not available, skipping resource check")
        return True
    except Exception as e:
        logger.error(f"Resource check failed: {e}")
        return True  # Continue anyway


def print_startup_banner():
    """Print startup banner with configuration info"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║           谁是卧底游戏平台 - 2C2G Optimized                  ║
╠══════════════════════════════════════════════════════════════╣
║  Environment: {env:<46} ║
║  Memory Limit: {mem:<44} ║
║  CPU Limit: {cpu:<47} ║
║  Max Rooms: {rooms:<47} ║
║  Max WebSocket: {ws:<43} ║
║  DB Pool Size: {db:<44} ║
║  Redis Connections: {redis:<39} ║
╚══════════════════════════════════════════════════════════════╝
    """.format(
        env=settings.ENVIRONMENT,
        mem=f"{settings.MAX_MEMORY_MB}MB",
        cpu=f"{settings.MAX_CPU_PERCENT}%",
        rooms=str(settings.MAX_ROOMS),
        ws=str(settings.MAX_WEBSOCKET_CONNECTIONS),
        db=str(settings.DB_POOL_SIZE),
        redis=str(settings.REDIS_MAX_CONNECTIONS)
    )
    print(banner)


def main():
    """Start the application with 2C2G optimizations"""
    # Print startup banner
    print_startup_banner()
    
    logger.info("Starting 谁是卧底游戏平台 with 2C2G optimizations...")
    
    # Configure GC for 2C2G
    configure_gc_for_2c2g()
    
    # Check system resources
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        resources_ok = loop.run_until_complete(check_system_resources())
        if not resources_ok:
            logger.warning("System resources are low, proceeding with caution")
    finally:
        loop.close()
    
    # Log configuration
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Resource limits: Memory={settings.MAX_MEMORY_MB}MB, CPU={settings.MAX_CPU_PERCENT}%")
    logger.info(f"Game limits: Rooms={settings.MAX_ROOMS}, WebSocket={settings.MAX_WEBSOCKET_CONNECTIONS}")
    logger.info(f"Database: Pool={settings.DB_POOL_SIZE}, Overflow={settings.DB_MAX_OVERFLOW}")
    logger.info(f"Redis: Connections={settings.REDIS_MAX_CONNECTIONS}")
    
    # Get optimized config
    config = get_uvicorn_config()
    
    # Start server
    uvicorn.run("app.main:app", **config)


if __name__ == "__main__":
    main()