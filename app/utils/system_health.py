"""
System health monitoring and recovery utilities
系统健康监控和恢复工具 - 针对2C2G环境优化
"""

import asyncio
import logging
import psutil
import time
from enum import Enum
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.core.config import settings
from app.core.database import db_manager, health_check as db_health_check
from app.core.redis_client import redis_manager, redis_health_check

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status enumeration"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Health check result"""
    name: str
    status: HealthStatus
    message: str = ""
    details: Optional[Dict[str, Any]] = None


class SystemHealthMonitor:
    """System health monitoring and automatic recovery"""
    
    def __init__(self):
        self.monitoring_active = False
        self._monitoring = False
        self.last_cleanup = time.time()
        self.cleanup_interval = settings.CLEANUP_INTERVAL
        self.check_interval = 60  # Default check interval in seconds
        self.health_history = []
        self.max_history_size = 100
        self._last_checks: List[HealthCheck] = []
        self._last_check_time: Optional[datetime] = None
        self._monitor_task: Optional[asyncio.Task] = None
    
    async def get_system_metrics(self) -> Dict[str, Any]:
        """Get current system resource metrics"""
        try:
            # Memory usage
            memory = psutil.virtual_memory()
            memory_mb = memory.used / (1024 * 1024)
            memory_percent = memory.percent
            
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            
            # Process info
            process = psutil.Process()
            process_memory = process.memory_info().rss / (1024 * 1024)  # MB
            process_cpu = process.cpu_percent()
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "memory": {
                    "total_mb": memory.total / (1024 * 1024),
                    "used_mb": memory_mb,
                    "percent": memory_percent,
                    "available_mb": memory.available / (1024 * 1024)
                },
                "cpu": {
                    "percent": cpu_percent,
                    "count": psutil.cpu_count()
                },
                "disk": {
                    "total_gb": disk.total / (1024 * 1024 * 1024),
                    "used_gb": disk.used / (1024 * 1024 * 1024),
                    "percent": disk_percent
                },
                "process": {
                    "memory_mb": process_memory,
                    "cpu_percent": process_cpu,
                    "threads": process.num_threads()
                }
            }
        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            return {"error": str(e)}
    
    async def check_resource_limits(self) -> Dict[str, Any]:
        """Check if system resources are within acceptable limits"""
        metrics = await self.get_system_metrics()
        
        if "error" in metrics:
            return {"status": "error", "metrics": metrics}
        
        warnings = []
        critical = []
        
        # Check memory usage
        memory_mb = metrics["memory"]["used_mb"]
        if memory_mb > settings.MAX_MEMORY_MB * 0.95:  # 95% of limit
            critical.append(f"Memory usage critical: {memory_mb:.1f}MB > {settings.MAX_MEMORY_MB * 0.95:.1f}MB")
        elif memory_mb > settings.MAX_MEMORY_MB * 0.8:  # 80% of limit
            warnings.append(f"Memory usage high: {memory_mb:.1f}MB > {settings.MAX_MEMORY_MB * 0.8:.1f}MB")
        
        # Check CPU usage
        cpu_percent = metrics["cpu"]["percent"]
        if cpu_percent > settings.MAX_CPU_PERCENT * 0.95:  # 95% of limit
            critical.append(f"CPU usage critical: {cpu_percent:.1f}% > {settings.MAX_CPU_PERCENT * 0.95:.1f}%")
        elif cpu_percent > settings.MAX_CPU_PERCENT * 0.8:  # 80% of limit
            warnings.append(f"CPU usage high: {cpu_percent:.1f}% > {settings.MAX_CPU_PERCENT * 0.8:.1f}%")
        
        # Check disk usage
        disk_percent = metrics["disk"]["percent"]
        if disk_percent > 90:
            critical.append(f"Disk usage critical: {disk_percent:.1f}% > 90%")
        elif disk_percent > 80:
            warnings.append(f"Disk usage high: {disk_percent:.1f}% > 80%")
        
        status = "critical" if critical else ("warning" if warnings else "healthy")
        
        return {
            "status": status,
            "metrics": metrics,
            "warnings": warnings,
            "critical": critical
        }
    
    async def get_database_health(self) -> Dict[str, Any]:
        """Get database connection health status"""
        try:
            return await db_health_check()
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def get_redis_health(self) -> Dict[str, Any]:
        """Get Redis connection health status"""
        try:
            return await redis_health_check()
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def comprehensive_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive system health check"""
        health_report = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": "healthy"
        }
        
        # System resources
        resource_check = await self.check_resource_limits()
        health_report["resources"] = resource_check
        
        # Database health
        db_health = await self.get_database_health()
        health_report["database"] = db_health
        
        # Redis health
        redis_health = await self.get_redis_health()
        health_report["redis"] = redis_health
        
        # Determine overall status
        statuses = [
            resource_check.get("status", "unknown"),
            db_health.get("status", "unknown"),
            redis_health.get("status", "unknown")
        ]
        
        if "critical" in statuses or "error" in statuses:
            health_report["overall_status"] = "critical"
        elif "warning" in statuses or "unhealthy" in statuses:
            health_report["overall_status"] = "warning"
        
        # Store in history
        self.health_history.append(health_report)
        if len(self.health_history) > self.max_history_size:
            self.health_history.pop(0)
        
        return health_report
    
    async def cleanup_resources(self) -> Dict[str, Any]:
        """Perform resource cleanup operations"""
        cleanup_report = {
            "timestamp": datetime.utcnow().isoformat(),
            "operations": []
        }
        
        try:
            # Force garbage collection
            import gc
            collected = gc.collect()
            cleanup_report["operations"].append(f"Garbage collection: {collected} objects collected")
            
            # Clean up expired sessions (if session manager has cleanup method)
            try:
                from app.utils.session import session_manager
                if hasattr(session_manager, 'cleanup_expired_sessions'):
                    cleaned_sessions = await session_manager.cleanup_expired_sessions()
                    cleanup_report["operations"].append(f"Cleaned {cleaned_sessions} expired sessions")
            except Exception as e:
                cleanup_report["operations"].append(f"Session cleanup failed: {e}")
            
            # Update last cleanup time
            self.last_cleanup = time.time()
            cleanup_report["status"] = "success"
            
        except Exception as e:
            logger.error(f"Resource cleanup failed: {e}")
            cleanup_report["status"] = "error"
            cleanup_report["error"] = str(e)
        
        return cleanup_report
    
    async def auto_recovery_actions(self, health_report: Dict[str, Any]) -> Dict[str, Any]:
        """Perform automatic recovery actions based on health status"""
        recovery_report = {
            "timestamp": datetime.utcnow().isoformat(),
            "actions": []
        }
        
        try:
            # Check if cleanup is needed
            current_time = time.time()
            if current_time - self.last_cleanup > self.cleanup_interval:
                cleanup_result = await self.cleanup_resources()
                recovery_report["actions"].append(f"Resource cleanup: {cleanup_result['status']}")
            
            # Database recovery
            if health_report.get("database", {}).get("status") == "unhealthy":
                try:
                    await db_manager.health_check()
                    recovery_report["actions"].append("Database reconnection attempted")
                except Exception as e:
                    recovery_report["actions"].append(f"Database recovery failed: {e}")
            
            # Redis recovery
            if health_report.get("redis", {}).get("status") == "unhealthy":
                try:
                    await redis_manager.health_check()
                    recovery_report["actions"].append("Redis reconnection attempted")
                except Exception as e:
                    recovery_report["actions"].append(f"Redis recovery failed: {e}")
            
            # Memory pressure response
            resource_status = health_report.get("resources", {}).get("status")
            if resource_status in ["critical", "warning"]:
                cleanup_result = await self.cleanup_resources()
                recovery_report["actions"].append(f"Emergency cleanup: {cleanup_result['status']}")
            
            recovery_report["status"] = "completed"
            
        except Exception as e:
            logger.error(f"Auto recovery failed: {e}")
            recovery_report["status"] = "error"
            recovery_report["error"] = str(e)
        
        return recovery_report
    
    async def start_monitoring(self, interval: int = 60):
        """Start continuous health monitoring"""
        if self._monitoring:
            logger.warning("Health monitoring already active")
            return
        
        self._monitoring = True
        self.monitoring_active = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop(interval))
        logger.info(f"Starting health monitoring with {interval}s interval")
    
    async def _monitoring_loop(self, interval: int):
        """Internal monitoring loop"""
        try:
            while self._monitoring:
                health_report = await self.comprehensive_health_check()
                
                # Log health status
                status = health_report["overall_status"]
                if status == "critical":
                    logger.error(f"System health critical: {health_report}")
                elif status == "warning":
                    logger.warning(f"System health warning: {health_report}")
                else:
                    logger.debug(f"System health check: {status}")
                
                # Perform auto recovery if needed
                if status in ["critical", "warning"]:
                    recovery_report = await self.auto_recovery_actions(health_report)
                    logger.info(f"Auto recovery actions: {recovery_report}")
                
                await asyncio.sleep(interval)
                
        except asyncio.CancelledError:
            logger.info("Health monitoring cancelled")
        except Exception as e:
            logger.error(f"Health monitoring error: {e}")
        finally:
            self._monitoring = False
            self.monitoring_active = False
    
    async def stop_monitoring(self):
        """Stop health monitoring"""
        self._monitoring = False
        self.monitoring_active = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Health monitoring stopped")
    
    async def run_health_checks(self) -> List[HealthCheck]:
        """Run all health checks and return results"""
        checks = []
        self._last_check_time = datetime.utcnow()
        
        # Resource check
        try:
            resource_result = await self.check_resource_limits()
            resource_status = self._map_status(resource_result.get("status", "unknown"))
            checks.append(HealthCheck(
                name="resources",
                status=resource_status,
                message=f"Memory: {resource_result.get('metrics', {}).get('memory', {}).get('percent', 0):.1f}%",
                details=resource_result.get("metrics")
            ))
        except Exception as e:
            checks.append(HealthCheck(
                name="resources",
                status=HealthStatus.CRITICAL,
                message=str(e)
            ))
        
        # Database check
        try:
            db_result = await self.get_database_health()
            db_status = self._map_status(db_result.get("status", "unknown"))
            checks.append(HealthCheck(
                name="database",
                status=db_status,
                message=db_result.get("message", ""),
                details=db_result
            ))
        except Exception as e:
            checks.append(HealthCheck(
                name="database",
                status=HealthStatus.CRITICAL,
                message=str(e)
            ))
        
        # Redis check
        try:
            redis_result = await self.get_redis_health()
            redis_status = self._map_status(redis_result.get("status", "unknown"))
            checks.append(HealthCheck(
                name="redis",
                status=redis_status,
                message=redis_result.get("message", ""),
                details=redis_result
            ))
        except Exception as e:
            checks.append(HealthCheck(
                name="redis",
                status=HealthStatus.CRITICAL,
                message=str(e)
            ))
        
        # Application check (always healthy if we got this far)
        checks.append(HealthCheck(
            name="application",
            status=HealthStatus.HEALTHY,
            message="Application is running"
        ))
        
        self._last_checks = checks
        return checks
    
    def _map_status(self, status_str: str) -> HealthStatus:
        """Map string status to HealthStatus enum"""
        status_map = {
            "healthy": HealthStatus.HEALTHY,
            "warning": HealthStatus.WARNING,
            "critical": HealthStatus.CRITICAL,
            "error": HealthStatus.CRITICAL,
            "unhealthy": HealthStatus.CRITICAL,
            "unknown": HealthStatus.UNKNOWN
        }
        return status_map.get(status_str.lower(), HealthStatus.UNKNOWN)
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report"""
        # Determine overall status from last checks
        overall_status = HealthStatus.HEALTHY
        if self._last_checks:
            statuses = [check.status for check in self._last_checks]
            if HealthStatus.CRITICAL in statuses:
                overall_status = HealthStatus.CRITICAL
            elif HealthStatus.WARNING in statuses:
                overall_status = HealthStatus.WARNING
            elif HealthStatus.UNKNOWN in statuses:
                overall_status = HealthStatus.UNKNOWN
        
        return {
            "overall_status": overall_status,
            "last_check": self._last_check_time.isoformat() if self._last_check_time else None,
            "checks": {check.name: {"status": check.status, "message": check.message} for check in self._last_checks},
            "environment": settings.ENVIRONMENT,
            "resource_limits": {
                "max_memory_mb": settings.MAX_MEMORY_MB,
                "max_cpu_percent": settings.MAX_CPU_PERCENT,
                "max_rooms": settings.MAX_ROOMS,
                "max_websocket_connections": settings.MAX_WEBSOCKET_CONNECTIONS
            }
        }
    
    def get_health_history(self, limit: int = 10) -> list:
        """Get recent health check history"""
        return self.health_history[-limit:] if self.health_history else []


# Global health monitor instance
health_monitor = SystemHealthMonitor()


# Convenience functions
async def get_system_status() -> Dict[str, Any]:
    """Get current system status"""
    return await health_monitor.comprehensive_health_check()


async def perform_health_check() -> Dict[str, Any]:
    """Perform health check and return status"""
    return await health_monitor.comprehensive_health_check()


async def emergency_cleanup() -> Dict[str, Any]:
    """Perform emergency resource cleanup"""
    return await health_monitor.cleanup_resources()