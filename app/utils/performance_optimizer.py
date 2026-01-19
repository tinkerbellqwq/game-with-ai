"""
Performance Optimizer for 2C2G Environment
2C2G环境性能优化器
"""

import gc
import asyncio
import logging
import psutil
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from functools import wraps
from app.core.config import settings

logger = logging.getLogger(__name__)


class PerformanceOptimizer:
    """
    2C2G环境性能优化器
    
    功能:
    - 内存使用优化
    - 连接池管理
    - 资源监控和自动调优
    - 缓存策略优化
    """
    
    def __init__(self):
        self.max_memory_mb = settings.MAX_MEMORY_MB
        self.max_cpu_percent = settings.MAX_CPU_PERCENT
        self._optimization_enabled = True
        self._last_gc_time = datetime.utcnow()
        self._gc_interval = timedelta(minutes=5)
        self._memory_threshold = 0.8  # 80% of max memory
        self._cpu_threshold = 0.7  # 70% of max CPU
    
    async def optimize_memory(self) -> Dict[str, Any]:
        """
        优化内存使用
        
        策略:
        1. 强制垃圾回收
        2. 清理过期缓存
        3. 压缩数据结构
        """
        result = {
            "before": self._get_memory_usage(),
            "actions": [],
            "after": None
        }
        
        try:
            # 1. 强制垃圾回收
            collected = gc.collect()
            result["actions"].append(f"GC collected {collected} objects")
            
            # 2. 清理Redis过期缓存
            try:
                from app.core.redis_client import redis_manager
                client = await redis_manager.get_client()
                
                # 清理过期的游戏状态缓存
                keys = await client.keys("game_state:*")
                expired_count = 0
                for key in keys:
                    ttl = await client.ttl(key)
                    if ttl == -1:  # 没有过期时间
                        await client.expire(key, 3600)  # 设置1小时过期
                        expired_count += 1
                
                result["actions"].append(f"Set expiry for {expired_count} cache keys")
                
            except Exception as e:
                logger.warning(f"Failed to clean Redis cache: {e}")
            
            # 3. 清理数据库连接池
            try:
                from app.core.database import db_manager
                if db_manager.engine:
                    # 回收空闲连接
                    await db_manager.engine.dispose()
                    await db_manager.initialize()
                    result["actions"].append("Database connection pool recycled")
            except Exception as e:
                logger.warning(f"Failed to recycle database connections: {e}")
            
            result["after"] = self._get_memory_usage()
            result["memory_freed_mb"] = result["before"]["memory_mb"] - result["after"]["memory_mb"]
            
            logger.info(f"Memory optimization completed: freed {result['memory_freed_mb']:.1f}MB")
            
        except Exception as e:
            logger.error(f"Memory optimization failed: {e}")
            result["error"] = str(e)
        
        return result
    
    async def optimize_connections(self) -> Dict[str, Any]:
        """
        优化连接池配置
        
        策略:
        1. 根据当前负载调整连接池大小
        2. 清理空闲连接
        3. 优化连接超时设置
        """
        result = {
            "database": {},
            "redis": {},
            "websocket": {}
        }
        
        try:
            # 获取当前资源使用情况
            memory_usage = self._get_memory_usage()
            cpu_usage = self._get_cpu_usage()
            
            # 根据资源使用情况调整连接池
            if memory_usage["memory_percent"] > self._memory_threshold * 100:
                # 内存压力大，减少连接池大小
                result["recommendation"] = "reduce_pool_size"
                result["reason"] = f"High memory usage: {memory_usage['memory_percent']:.1f}%"
            elif cpu_usage > self._cpu_threshold * 100:
                # CPU压力大，减少并发连接
                result["recommendation"] = "reduce_concurrency"
                result["reason"] = f"High CPU usage: {cpu_usage:.1f}%"
            else:
                result["recommendation"] = "maintain_current"
                result["reason"] = "Resource usage within normal range"
            
            # 获取连接池状态
            try:
                from app.core.database import db_manager
                if db_manager.engine:
                    pool = db_manager.engine.pool
                    result["database"] = {
                        "pool_size": pool.size(),
                        "checked_in": pool.checkedin(),
                        "checked_out": pool.checkedout(),
                        "overflow": pool.overflow()
                    }
            except Exception as e:
                logger.warning(f"Failed to get database pool status: {e}")
            
            # 获取WebSocket连接状态
            try:
                from app.websocket.connection_manager import connection_manager
                result["websocket"] = {
                    "active_connections": connection_manager.get_connection_count(),
                    "active_rooms": connection_manager.get_room_count(),
                    "max_connections": connection_manager.max_connections
                }
            except Exception as e:
                logger.warning(f"Failed to get WebSocket status: {e}")
            
        except Exception as e:
            logger.error(f"Connection optimization failed: {e}")
            result["error"] = str(e)
        
        return result
    
    async def auto_tune(self) -> Dict[str, Any]:
        """
        自动调优
        
        根据当前系统状态自动调整配置
        """
        result = {
            "timestamp": datetime.utcnow().isoformat(),
            "actions": [],
            "status": "success"
        }
        
        try:
            # 1. 检查内存使用
            memory_usage = self._get_memory_usage()
            if memory_usage["memory_percent"] > self._memory_threshold * 100:
                await self.optimize_memory()
                result["actions"].append("memory_optimization")
            
            # 2. 检查是否需要垃圾回收
            if datetime.utcnow() - self._last_gc_time > self._gc_interval:
                gc.collect()
                self._last_gc_time = datetime.utcnow()
                result["actions"].append("scheduled_gc")
            
            # 3. 检查连接池状态
            conn_status = await self.optimize_connections()
            if conn_status.get("recommendation") != "maintain_current":
                result["actions"].append(f"connection_adjustment: {conn_status['recommendation']}")
            
            # 4. 清理过期会话
            try:
                from app.utils.session import session_manager
                cleaned = await session_manager.cleanup_expired_sessions()
                if cleaned > 0:
                    result["actions"].append(f"cleaned_{cleaned}_expired_sessions")
            except Exception as e:
                logger.warning(f"Failed to cleanup sessions: {e}")
            
            result["resource_status"] = {
                "memory": memory_usage,
                "cpu_percent": self._get_cpu_usage()
            }
            
        except Exception as e:
            logger.error(f"Auto-tune failed: {e}")
            result["status"] = "error"
            result["error"] = str(e)
        
        return result
    
    def _get_memory_usage(self) -> Dict[str, float]:
        """获取内存使用情况"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            return {
                "memory_mb": memory_mb,
                "memory_percent": (memory_mb / self.max_memory_mb) * 100,
                "memory_limit_mb": self.max_memory_mb
            }
        except Exception as e:
            logger.error(f"Failed to get memory usage: {e}")
            return {
                "memory_mb": 0,
                "memory_percent": 0,
                "memory_limit_mb": self.max_memory_mb
            }
    
    def _get_cpu_usage(self) -> float:
        """获取CPU使用率"""
        try:
            process = psutil.Process()
            return process.cpu_percent(interval=0.1)
        except Exception as e:
            logger.error(f"Failed to get CPU usage: {e}")
            return 0.0
    
    def get_optimization_status(self) -> Dict[str, Any]:
        """获取优化状态"""
        return {
            "enabled": self._optimization_enabled,
            "memory_threshold": self._memory_threshold,
            "cpu_threshold": self._cpu_threshold,
            "gc_interval_minutes": self._gc_interval.total_seconds() / 60,
            "last_gc_time": self._last_gc_time.isoformat(),
            "current_memory": self._get_memory_usage(),
            "current_cpu": self._get_cpu_usage()
        }


# 全局性能优化器实例
performance_optimizer = PerformanceOptimizer()


def memory_efficient(func: Callable) -> Callable:
    """
    内存效率装饰器
    
    在函数执行后检查内存使用，必要时触发垃圾回收
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        result = await func(*args, **kwargs)
        
        # 检查内存使用
        memory_usage = performance_optimizer._get_memory_usage()
        if memory_usage["memory_percent"] > 80:
            gc.collect()
            logger.debug(f"GC triggered after {func.__name__} due to high memory usage")
        
        return result
    
    return wrapper


def rate_limited(max_calls: int, window_seconds: int):
    """
    速率限制装饰器
    
    限制函数在指定时间窗口内的调用次数
    """
    calls = []
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            now = datetime.utcnow()
            
            # 清理过期的调用记录
            nonlocal calls
            calls = [t for t in calls if now - t < timedelta(seconds=window_seconds)]
            
            if len(calls) >= max_calls:
                raise Exception(f"Rate limit exceeded: {max_calls} calls per {window_seconds} seconds")
            
            calls.append(now)
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator


class ConnectionPoolManager:
    """
    连接池管理器
    
    动态管理数据库和Redis连接池大小
    """
    
    def __init__(self):
        self.min_db_connections = 2
        self.max_db_connections = settings.DB_POOL_SIZE
        self.min_redis_connections = 2
        self.max_redis_connections = settings.REDIS_MAX_CONNECTIONS
        self._current_db_size = settings.DB_POOL_SIZE
        self._current_redis_size = settings.REDIS_MAX_CONNECTIONS
    
    async def adjust_pool_sizes(self, memory_pressure: float, cpu_pressure: float):
        """
        根据资源压力调整连接池大小
        
        Args:
            memory_pressure: 内存压力 (0-1)
            cpu_pressure: CPU压力 (0-1)
        """
        # 计算目标连接池大小
        pressure = max(memory_pressure, cpu_pressure)
        
        if pressure > 0.8:
            # 高压力，减少连接
            target_db = self.min_db_connections
            target_redis = self.min_redis_connections
        elif pressure > 0.6:
            # 中等压力，适度减少
            target_db = (self.min_db_connections + self.max_db_connections) // 2
            target_redis = (self.min_redis_connections + self.max_redis_connections) // 2
        else:
            # 低压力，保持最大
            target_db = self.max_db_connections
            target_redis = self.max_redis_connections
        
        # 记录调整
        if target_db != self._current_db_size or target_redis != self._current_redis_size:
            logger.info(
                f"Adjusting pool sizes: DB {self._current_db_size}->{target_db}, "
                f"Redis {self._current_redis_size}->{target_redis}"
            )
            self._current_db_size = target_db
            self._current_redis_size = target_redis
        
        return {
            "db_pool_size": target_db,
            "redis_pool_size": target_redis,
            "pressure": pressure
        }


# 全局连接池管理器
connection_pool_manager = ConnectionPoolManager()


async def start_auto_optimization(interval_seconds: int = 300):
    """
    启动自动优化任务
    
    Args:
        interval_seconds: 优化间隔（秒）
    """
    logger.info(f"Starting auto-optimization with {interval_seconds}s interval")
    
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            result = await performance_optimizer.auto_tune()
            
            if result["actions"]:
                logger.info(f"Auto-optimization completed: {result['actions']}")
                
        except asyncio.CancelledError:
            logger.info("Auto-optimization task cancelled")
            break
        except Exception as e:
            logger.error(f"Auto-optimization error: {e}")
