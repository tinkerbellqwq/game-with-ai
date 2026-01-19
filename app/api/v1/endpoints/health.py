"""
Health check and system monitoring endpoints
健康检查和系统监控端点
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any

from app.utils.system_health import health_monitor, get_system_status
from app.core.database import health_check as db_health_check
from app.core.redis_client import redis_health_check
from app.utils.security import rate_limiter

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Basic health check endpoint
    基础健康检查端点
    """
    return {
        "status": "healthy",
        "service": "undercover-game-platform",
        "version": "1.0.0"
    }


@router.get("/health/detailed")
async def detailed_health_check():
    """
    Detailed health check with system metrics
    详细健康检查包含系统指标
    
    验证需求: 需求 8.3, 8.5
    """
    try:
        health_report = await get_system_status()
        return health_report
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}"
        )


@router.get("/health/database")
async def database_health():
    """
    Database connection health check
    数据库连接健康检查
    
    验证需求: 需求 8.3
    """
    try:
        db_status = await db_health_check()
        return db_status
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/health/redis")
async def redis_health():
    """
    Redis connection health check
    Redis连接健康检查
    
    验证需求: 需求 8.3
    """
    try:
        redis_status = await redis_health_check()
        return redis_status
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/health/security")
async def security_health():
    """
    Security system health check
    安全系统健康检查
    
    验证需求: 需求 10.1, 10.4
    """
    try:
        # Check rate limiter status
        test_identifier = "health_check_test"
        rate_status = await rate_limiter.get_rate_limit_status(test_identifier)
        
        # Get active sessions count
        from app.utils.session import session_manager
        active_sessions = await session_manager.get_active_sessions_count()
        
        return {
            "status": "healthy",
            "rate_limiter": {
                "status": "operational",
                "test_limit": rate_status.get("limit"),
                "test_remaining": rate_status.get("remaining")
            },
            "session_manager": {
                "status": "operational",
                "active_sessions": active_sessions
            },
            "encryption": {
                "status": "operational"
            }
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/metrics")
async def system_metrics():
    """
    System resource metrics
    系统资源指标
    
    验证需求: 需求 8.1, 8.2
    """
    try:
        metrics = await health_monitor.get_system_metrics()
        return metrics
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get system metrics: {str(e)}"
        )


@router.get("/metrics/history")
async def metrics_history(limit: int = 10):
    """
    Historical system metrics
    历史系统指标
    """
    try:
        history = health_monitor.get_health_history(limit)
        return {
            "history": history,
            "count": len(history)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get metrics history: {str(e)}"
        )


@router.post("/maintenance/cleanup")
async def trigger_cleanup():
    """
    Trigger manual resource cleanup
    触发手动资源清理
    
    验证需求: 需求 8.1, 8.2
    """
    try:
        from app.utils.system_health import emergency_cleanup
        cleanup_result = await emergency_cleanup()
        return cleanup_result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cleanup failed: {str(e)}"
        )


@router.get("/status")
async def service_status():
    """
    Overall service status
    整体服务状态
    """
    try:
        # Get comprehensive health check
        health_report = await get_system_status()
        
        # Determine service status
        overall_status = health_report.get("overall_status", "unknown")
        
        # Get component statuses
        components = {
            "database": health_report.get("database", {}).get("status", "unknown"),
            "redis": health_report.get("redis", {}).get("status", "unknown"),
            "resources": health_report.get("resources", {}).get("status", "unknown")
        }
        
        return {
            "service": "undercover-game-platform",
            "status": overall_status,
            "components": components,
            "timestamp": health_report.get("timestamp"),
            "uptime": "operational"
        }
        
    except Exception as e:
        return {
            "service": "undercover-game-platform",
            "status": "error",
            "error": str(e),
            "components": {
                "database": "unknown",
                "redis": "unknown", 
                "resources": "unknown"
            }
        }


@router.get("/performance")
async def performance_status():
    """
    Performance optimization status
    性能优化状态
    
    验证需求: 需求 8.1, 8.2
    """
    try:
        from app.utils.performance_optimizer import performance_optimizer
        
        status = performance_optimizer.get_optimization_status()
        return {
            "status": "operational",
            "optimization": status
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.post("/performance/optimize")
async def trigger_optimization():
    """
    Trigger manual performance optimization
    触发手动性能优化
    
    验证需求: 需求 8.1, 8.2
    """
    try:
        from app.utils.performance_optimizer import performance_optimizer
        
        result = await performance_optimizer.auto_tune()
        return {
            "status": "success",
            "result": result
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Optimization failed: {str(e)}"
        )


@router.post("/performance/memory")
async def optimize_memory():
    """
    Trigger memory optimization
    触发内存优化
    
    验证需求: 需求 8.2
    """
    try:
        from app.utils.performance_optimizer import performance_optimizer
        
        result = await performance_optimizer.optimize_memory()
        return {
            "status": "success",
            "result": result
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory optimization failed: {str(e)}"
        )


@router.get("/performance/connections")
async def connection_status():
    """
    Connection pool status
    连接池状态
    
    验证需求: 需求 8.1
    """
    try:
        from app.utils.performance_optimizer import performance_optimizer
        
        result = await performance_optimizer.optimize_connections()
        return {
            "status": "success",
            "connections": result
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
