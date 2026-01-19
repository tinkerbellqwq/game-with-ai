"""
Session management utilities
会话管理工具
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

from app.core.redis_client import redis_manager
from app.core.config import settings

logger = logging.getLogger(__name__)


class SessionManager:
    """Session management for user authentication and game state"""
    
    def __init__(self):
        self.redis = redis_manager
    
    async def create_session(
        self, 
        user_id: str, 
        session_data: Dict[str, Any], 
        expire_minutes: int = None
    ) -> str:
        """
        Create a new user session
        创建新的用户会话
        
        验证需求: 需求 1.3
        """
        if expire_minutes is None:
            expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        
        session_data.update({
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(minutes=expire_minutes)).isoformat()
        })
        
        await self.redis.set_session(user_id, session_data, expire=expire_minutes * 60)
        logger.info(f"Session created for user: {user_id}")
        return user_id
    
    async def get_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user session data
        获取用户会话数据
        
        验证需求: 需求 1.5
        """
        session_data = await self.redis.get_session(user_id)
        
        if session_data:
            # Check if session has expired
            expires_at = datetime.fromisoformat(session_data.get("expires_at", ""))
            if datetime.utcnow() > expires_at:
                await self.delete_session(user_id)
                logger.info(f"Session expired for user: {user_id}")
                return None
        
        return session_data
    
    async def update_session(
        self, 
        user_id: str, 
        update_data: Dict[str, Any], 
        extend_expiry: bool = True
    ) -> bool:
        """
        Update existing session data
        更新现有会话数据
        """
        try:
            session_data = await self.get_session(user_id)
            if not session_data:
                return False
            
            session_data.update(update_data)
            session_data["updated_at"] = datetime.utcnow().isoformat()
            
            expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES if extend_expiry else None
            if expire_minutes:
                session_data["expires_at"] = (
                    datetime.utcnow() + timedelta(minutes=expire_minutes)
                ).isoformat()
            
            await self.redis.set_session(
                user_id, 
                session_data, 
                expire=expire_minutes * 60 if expire_minutes else 1800
            )
            
            logger.info(f"Session updated for user: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update session for user {user_id}: {e}")
            return False
    
    async def delete_session(self, user_id: str) -> bool:
        """
        Delete user session
        删除用户会话
        """
        try:
            await self.redis.delete_session(user_id)
            logger.info(f"Session deleted for user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete session for user {user_id}: {e}")
            return False
    
    async def is_session_valid(self, user_id: str) -> bool:
        """
        Check if user session is valid
        检查用户会话是否有效
        
        验证需求: 需求 1.5
        """
        session_data = await self.get_session(user_id)
        return session_data is not None
    
    async def extend_session(self, user_id: str, extend_minutes: int = None) -> bool:
        """
        Extend session expiry time
        延长会话过期时间
        """
        if extend_minutes is None:
            extend_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        
        return await self.update_session(
            user_id, 
            {"extended_at": datetime.utcnow().isoformat()}, 
            extend_expiry=True
        )
    
    async def get_active_sessions_count(self) -> int:
        """
        Get count of active sessions (for monitoring)
        获取活跃会话数量（用于监控）
        """
        try:
            client = await self.redis.get_client()
            keys = await client.keys("session:*")
            return len(keys)
        except Exception as e:
            logger.error(f"Failed to get active sessions count: {e}")
            return 0
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions (maintenance task)
        清理过期会话（维护任务）
        """
        try:
            client = await self.redis.get_client()
            keys = await client.keys("session:*")
            cleaned = 0
            
            for key in keys:
                session_data = await client.get(key)
                if session_data:
                    import json
                    data = json.loads(session_data)
                    expires_at = datetime.fromisoformat(data.get("expires_at", ""))
                    
                    if datetime.utcnow() > expires_at:
                        await client.delete(key)
                        cleaned += 1
            
            logger.info(f"Cleaned up {cleaned} expired sessions")
            return cleaned
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {e}")
            return 0


# Global session manager instance
session_manager = SessionManager()