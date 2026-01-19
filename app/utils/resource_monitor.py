"""
Resource monitoring utilities for 2C2G environment
2C2G环境资源监控工具
"""

import psutil
import asyncio
import logging
from typing import Dict, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class ResourceMonitor:
    """Monitor system resources and enforce 2C2G limits"""
    
    def __init__(self):
        self.max_memory_mb = settings.MAX_MEMORY_MB
        self.max_cpu_percent = settings.MAX_CPU_PERCENT
        self.cleanup_interval = settings.CLEANUP_INTERVAL
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
    
    async def start_monitoring(self):
        """Start resource monitoring"""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Resource monitoring started for 2C2G environment")
    
    async def stop_monitoring(self):
        """Stop resource monitoring"""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Resource monitoring stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self._monitoring:
            try:
                await self._check_resources()
                await asyncio.sleep(self.cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in resource monitoring: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _check_resources(self):
        """Check current resource usage"""
        try:
            # Get current process
            process = psutil.Process()
            
            # Check memory usage
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            # Check CPU usage
            cpu_percent = process.cpu_percent(interval=1)
            
            # Log resource usage
            logger.info(f"Resource usage - Memory: {memory_mb:.1f}MB/{self.max_memory_mb}MB, CPU: {cpu_percent:.1f}%/{self.max_cpu_percent}%")
            
            # Check if limits are exceeded
            if memory_mb > self.max_memory_mb:
                logger.warning(f"Memory usage ({memory_mb:.1f}MB) exceeds limit ({self.max_memory_mb}MB)")
                await self._handle_memory_pressure()
            
            if cpu_percent > self.max_cpu_percent:
                logger.warning(f"CPU usage ({cpu_percent:.1f}%) exceeds limit ({self.max_cpu_percent}%)")
                await self._handle_cpu_pressure()
                
        except Exception as e:
            logger.error(f"Failed to check resources: {e}")
    
    async def _handle_memory_pressure(self):
        """Handle high memory usage"""
        try:
            # Force garbage collection
            import gc
            gc.collect()
            
            # Clear Redis cache if available
            try:
                from app.core.redis_client import redis_manager
                client = await redis_manager.get_client()
                # Clear expired keys
                await client.execute_command("MEMORY", "PURGE")
                logger.info("Cleared Redis memory cache")
            except Exception as e:
                logger.debug(f"Could not clear Redis cache: {e}")
            
            logger.info("Applied memory pressure relief measures")
            
        except Exception as e:
            logger.error(f"Failed to handle memory pressure: {e}")
    
    async def _handle_cpu_pressure(self):
        """Handle high CPU usage"""
        try:
            # Add small delay to reduce CPU pressure
            await asyncio.sleep(0.1)
            logger.info("Applied CPU pressure relief measures")
            
        except Exception as e:
            logger.error(f"Failed to handle CPU pressure: {e}")
    
    def get_current_usage(self) -> Dict[str, float]:
        """Get current resource usage"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            cpu_percent = process.cpu_percent()
            
            return {
                "memory_mb": memory_mb,
                "memory_percent": (memory_mb / self.max_memory_mb) * 100,
                "cpu_percent": cpu_percent,
                "memory_limit_mb": self.max_memory_mb,
                "cpu_limit_percent": self.max_cpu_percent
            }
        except Exception as e:
            logger.error(f"Failed to get resource usage: {e}")
            return {
                "memory_mb": 0,
                "memory_percent": 0,
                "cpu_percent": 0,
                "memory_limit_mb": self.max_memory_mb,
                "cpu_limit_percent": self.max_cpu_percent
            }
    
    def is_resource_available(self, required_memory_mb: float = 0) -> bool:
        """Check if resources are available for new operations"""
        try:
            current = self.get_current_usage()
            
            # Check if we have enough memory for the operation
            if current["memory_mb"] + required_memory_mb > self.max_memory_mb:
                return False
            
            # Check if CPU is not overloaded
            if current["cpu_percent"] > self.max_cpu_percent * 0.9:  # 90% threshold
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to check resource availability: {e}")
            return False


# Global resource monitor instance
resource_monitor = ResourceMonitor()