"""
Redis client configuration and connection management
Redis客户端配置和连接管理 - 针对2C2G环境优化，增强稳定性和重连机制
"""

import redis.asyncio as redis
from typing import Optional
from app.core.config import settings
import logging
import json
import asyncio
import time
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class RedisManager:
    """Enhanced Redis manager with connection recovery and error handling"""
    
    def __init__(self):
        self.pool: Optional[redis.ConnectionPool] = None
        self.client: Optional[redis.Redis] = None
        self._connection_retries = 0
        self._max_retries = 3
        self._retry_delay = 1.0
        self._health_check_interval = 30
        self._last_health_check = 0
    
    async def initialize(self):
        """Initialize Redis connection pool with enhanced error handling"""
        try:
            # Create connection pool with limited connections for 2C2G
            self.pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                retry_on_timeout=True,
                retry_on_error=[redis.ConnectionError, redis.TimeoutError],
                health_check_interval=30,
                encoding="utf-8",
                decode_responses=True
            )
            
            self.client = redis.Redis(connection_pool=self.pool)
            
            # Test connection
            await self._test_connection()
            logger.info("Redis manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis manager: {e}")
            # Don't raise in development mode to allow testing without Redis
            if settings.ENVIRONMENT == "production":
                raise
    
    async def _test_connection(self) -> bool:
        """Test Redis connection health"""
        try:
            if not self.client:
                return False
                
            await self.client.ping()
            self._connection_retries = 0
            self._last_health_check = time.time()
            return True
            
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis connection test failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Redis connection test: {e}")
            return False
    
    async def _reconnect(self) -> bool:
        """Attempt to reconnect to Redis with exponential backoff"""
        if self._connection_retries >= self._max_retries:
            logger.error("Maximum Redis reconnection attempts exceeded")
            return False
        
        self._connection_retries += 1
        delay = self._retry_delay * (2 ** (self._connection_retries - 1))
        
        logger.info(f"Attempting Redis reconnection {self._connection_retries}/{self._max_retries} after {delay}s")
        await asyncio.sleep(delay)
        
        try:
            # Close old connections and create new ones
            if self.client:
                await self.client.aclose()
            if self.pool:
                await self.pool.aclose()
            
            await self.initialize()
            return True
            
        except Exception as e:
            logger.error(f"Redis reconnection attempt {self._connection_retries} failed: {e}")
            return False
    
    async def health_check(self) -> bool:
        """Perform periodic health check"""
        current_time = time.time()
        if current_time - self._last_health_check < self._health_check_interval:
            return True
        
        if await self._test_connection():
            return True
        
        # Attempt reconnection if health check fails
        return await self._reconnect()
    
    async def get_client(self) -> redis.Redis:
        """Get Redis client with health check"""
        if not await self.health_check():
            raise RuntimeError("Redis connection unavailable")
        return self.client
    
    async def execute_with_retry(self, operation, *args, **kwargs):
        """Execute Redis operation with automatic retry on connection failure"""
        max_attempts = 2
        
        for attempt in range(max_attempts):
            try:
                client = await self.get_client()
                return await operation(client, *args, **kwargs)
            except (redis.ConnectionError, redis.TimeoutError) as e:
                if attempt == max_attempts - 1:
                    logger.error(f"Redis operation failed after {max_attempts} attempts: {e}")
                    raise
                logger.warning(f"Redis operation attempt {attempt + 1} failed, retrying: {e}")
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Redis operation failed with non-connection error: {e}")
                raise
    
    async def close(self):
        """Close Redis connections"""
        if self.client:
            await self.client.aclose()
        if self.pool:
            await self.pool.aclose()
        
        self.client = None
        self.pool = None
        logger.info("Redis connections closed")
    
    # Enhanced Redis operations with error handling
    async def set_session(self, session_id: str, user_data: dict, expire: int = 1800):
        """Store user session data with retry"""
        async def _set_operation(client, session_id, user_data, expire):
            return await client.setex(
                f"session:{session_id}",
                expire,
                json.dumps(user_data)
            )
        
        try:
            await self.execute_with_retry(_set_operation, session_id, user_data, expire)
        except Exception as e:
            logger.error(f"Failed to set session: {e}")
            raise
    
    async def get_session(self, session_id: str) -> Optional[dict]:
        """Retrieve user session data with retry"""
        async def _get_operation(client, session_id):
            data = await client.get(f"session:{session_id}")
            return json.loads(data) if data else None
        
        try:
            return await self.execute_with_retry(_get_operation, session_id)
        except Exception as e:
            logger.error(f"Failed to get session: {e}")
            return None
    
    async def delete_session(self, session_id: str):
        """Delete user session with retry"""
        async def _delete_operation(client, session_id):
            return await client.delete(f"session:{session_id}")
        
        try:
            await self.execute_with_retry(_delete_operation, session_id)
        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            raise
    
    async def set_game_state(self, game_id: str, game_data: dict, expire: int = 3600):
        """Store game state in Redis with retry"""
        async def _set_game_operation(client, game_id, game_data, expire):
            return await client.setex(
                f"game:{game_id}",
                expire,
                json.dumps(game_data, default=str)
            )
        
        try:
            await self.execute_with_retry(_set_game_operation, game_id, game_data, expire)
        except Exception as e:
            logger.error(f"Failed to set game state: {e}")
            raise
    
    async def get_game_state(self, game_id: str) -> Optional[dict]:
        """Retrieve game state from Redis with retry"""
        async def _get_game_operation(client, game_id):
            data = await client.get(f"game:{game_id}")
            return json.loads(data) if data else None
        
        try:
            return await self.execute_with_retry(_get_game_operation, game_id)
        except Exception as e:
            logger.error(f"Failed to get game state: {e}")
            return None
    
    async def delete_game_state(self, game_id: str):
        """Delete game state with retry"""
        async def _delete_game_operation(client, game_id):
            return await client.delete(f"game:{game_id}")
        
        try:
            await self.execute_with_retry(_delete_game_operation, game_id)
        except Exception as e:
            logger.error(f"Failed to delete game state: {e}")
            raise
    
    async def add_to_room(self, room_id: str, user_id: str):
        """Add user to room set with retry"""
        async def _add_room_operation(client, room_id, user_id):
            return await client.sadd(f"room:{room_id}:users", user_id)
        
        try:
            await self.execute_with_retry(_add_room_operation, room_id, user_id)
        except Exception as e:
            logger.error(f"Failed to add user to room: {e}")
            raise
    
    async def remove_from_room(self, room_id: str, user_id: str):
        """Remove user from room set with retry"""
        async def _remove_room_operation(client, room_id, user_id):
            return await client.srem(f"room:{room_id}:users", user_id)
        
        try:
            await self.execute_with_retry(_remove_room_operation, room_id, user_id)
        except Exception as e:
            logger.error(f"Failed to remove user from room: {e}")
            raise
    
    async def get_room_users(self, room_id: str) -> list:
        """Get all users in room with retry"""
        async def _get_room_users_operation(client, room_id):
            return await client.smembers(f"room:{room_id}:users")
        
        try:
            return await self.execute_with_retry(_get_room_users_operation, room_id)
        except Exception as e:
            logger.error(f"Failed to get room users: {e}")
            return []
    
    async def publish_message(self, channel: str, message: dict):
        """Publish message to Redis channel with retry"""
        async def _publish_operation(client, channel, message):
            return await client.publish(channel, json.dumps(message, default=str))
        
        try:
            await self.execute_with_retry(_publish_operation, channel, message)
        except Exception as e:
            logger.error(f"Failed to publish message: {e}")
            raise


# Global Redis manager instance
redis_manager = RedisManager()

# Legacy compatibility functions
async def init_redis():
    """Initialize Redis connection pool with 2C2G optimizations"""
    await redis_manager.initialize()


async def get_redis() -> redis.Redis:
    """Get Redis client instance"""
    return await redis_manager.get_client()


async def close_redis():
    """Close Redis connections"""
    await redis_manager.close()


async def redis_health_check() -> dict:
    """Redis health check for monitoring"""
    try:
        is_healthy = await redis_manager.health_check()
        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "connection_retries": redis_manager._connection_retries,
            "last_health_check": redis_manager._last_health_check
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "connection_retries": redis_manager._connection_retries
        }