"""
Security utilities and protection mechanisms
安全工具和防护机制 - 速率限制、输入验证、加密等
"""

import hashlib
import hmac
import secrets
import time
import re
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import asyncio
from collections import defaultdict, deque

from app.core.config import settings
from app.core.redis_client import redis_manager

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiting implementation with Redis backend"""
    
    def __init__(self):
        self.redis = redis_manager
        self.local_cache = defaultdict(lambda: deque())
        self.cache_cleanup_interval = 300  # 5 minutes
        self.last_cleanup = time.time()
    
    async def is_rate_limited(
        self, 
        identifier: str, 
        limit: int = None, 
        window: int = None,
        use_redis: bool = True
    ) -> bool:
        """
        Check if identifier is rate limited
        检查标识符是否被速率限制
        
        验证需求: 需求 10.1
        """
        if limit is None:
            limit = settings.RATE_LIMIT_REQUESTS
        if window is None:
            window = settings.RATE_LIMIT_WINDOW
        
        current_time = time.time()
        
        if use_redis:
            return await self._redis_rate_limit(identifier, limit, window, current_time)
        else:
            return self._local_rate_limit(identifier, limit, window, current_time)
    
    async def _redis_rate_limit(self, identifier: str, limit: int, window: int, current_time: float) -> bool:
        """Redis-based rate limiting"""
        try:
            client = await self.redis.get_client()
            key = f"rate_limit:{identifier}"
            
            # Use sliding window with Redis sorted sets
            # Remove old entries
            await client.zremrangebyscore(key, 0, current_time - window)
            
            # Count current requests
            current_count = await client.zcard(key)
            
            if current_count >= limit:
                logger.warning(f"Rate limit exceeded for {identifier}: {current_count}/{limit}")
                return True
            
            # Add current request
            await client.zadd(key, {str(current_time): current_time})
            await client.expire(key, window)
            
            return False
            
        except Exception as e:
            logger.error(f"Redis rate limiting failed: {e}")
            # Fallback to local rate limiting
            return self._local_rate_limit(identifier, limit, window, current_time)
    
    def _local_rate_limit(self, identifier: str, limit: int, window: int, current_time: float) -> bool:
        """Local memory-based rate limiting (fallback)"""
        # Cleanup old entries periodically
        if current_time - self.last_cleanup > self.cache_cleanup_interval:
            self._cleanup_local_cache(current_time)
        
        requests = self.local_cache[identifier]
        
        # Remove old requests outside the window
        while requests and requests[0] < current_time - window:
            requests.popleft()
        
        if len(requests) >= limit:
            logger.warning(f"Rate limit exceeded (local) for {identifier}: {len(requests)}/{limit}")
            return True
        
        # Add current request
        requests.append(current_time)
        return False
    
    def _cleanup_local_cache(self, current_time: float):
        """Clean up old entries from local cache"""
        window = settings.RATE_LIMIT_WINDOW
        for identifier, requests in list(self.local_cache.items()):
            while requests and requests[0] < current_time - window:
                requests.popleft()
            
            # Remove empty deques
            if not requests:
                del self.local_cache[identifier]
        
        self.last_cleanup = current_time
    
    async def get_rate_limit_status(self, identifier: str) -> Dict[str, Any]:
        """Get current rate limit status for identifier"""
        try:
            client = await self.redis.get_client()
            key = f"rate_limit:{identifier}"
            current_time = time.time()
            window = settings.RATE_LIMIT_WINDOW
            
            # Remove old entries
            await client.zremrangebyscore(key, 0, current_time - window)
            
            # Get current count and remaining
            current_count = await client.zcard(key)
            remaining = max(0, settings.RATE_LIMIT_REQUESTS - current_count)
            
            # Get oldest request time for reset calculation
            oldest_requests = await client.zrange(key, 0, 0, withscores=True)
            reset_time = None
            if oldest_requests:
                reset_time = oldest_requests[0][1] + window
            
            return {
                "identifier": identifier,
                "limit": settings.RATE_LIMIT_REQUESTS,
                "remaining": remaining,
                "reset_time": reset_time,
                "window": window
            }
            
        except Exception as e:
            logger.error(f"Failed to get rate limit status: {e}")
            return {
                "identifier": identifier,
                "limit": settings.RATE_LIMIT_REQUESTS,
                "remaining": settings.RATE_LIMIT_REQUESTS,
                "reset_time": None,
                "window": settings.RATE_LIMIT_WINDOW,
                "error": str(e)
            }


class InputValidator:
    """Input validation and sanitization utilities"""
    
    # Common regex patterns
    USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\u4e00-\u9fff]{2,20}$')
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    PASSWORD_PATTERN = re.compile(r'^(?=.*[a-zA-Z])(?=.*\d)[a-zA-Z\d@$!%*?&]{8,128}$')
    
    # Dangerous patterns to filter
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
        r"(--|#|/\*|\*/)",
        r"(\b(OR|AND)\s+\d+\s*=\s*\d+)",
        r"(\bUNION\s+SELECT\b)",
    ]
    
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"<iframe[^>]*>.*?</iframe>",
        r"<object[^>]*>.*?</object>",
        r"<embed[^>]*>.*?</embed>",
    ]
    
    @classmethod
    def validate_username(cls, username: str) -> bool:
        """
        Validate username format
        验证用户名格式
        
        验证需求: 需求 10.2
        """
        if not username or not isinstance(username, str):
            return False
        return bool(cls.USERNAME_PATTERN.match(username))
    
    @classmethod
    def validate_email(cls, email: str) -> bool:
        """
        Validate email format
        验证邮箱格式
        
        验证需求: 需求 10.2
        """
        if not email or not isinstance(email, str):
            return False
        return bool(cls.EMAIL_PATTERN.match(email))
    
    @classmethod
    def validate_password(cls, password: str) -> bool:
        """
        Validate password strength
        验证密码强度
        
        验证需求: 需求 10.2
        """
        if not password or not isinstance(password, str):
            return False
        return bool(cls.PASSWORD_PATTERN.match(password))
    
    @classmethod
    def sanitize_input(cls, text: str, max_length: int = 1000) -> str:
        """
        Sanitize user input to prevent injection attacks
        清理用户输入以防止注入攻击
        
        验证需求: 需求 10.2
        """
        if not text or not isinstance(text, str):
            return ""
        
        # Truncate to max length
        text = text[:max_length]
        
        # Remove null bytes
        text = text.replace('\x00', '')
        
        # Check for SQL injection patterns
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"Potential SQL injection detected: {pattern}")
                # Remove the dangerous pattern
                text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Check for XSS patterns
        for pattern in cls.XSS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"Potential XSS detected: {pattern}")
                # Remove the dangerous pattern
                text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Basic HTML entity encoding for remaining < and >
        text = text.replace('<', '&lt;').replace('>', '&gt;')
        
        return text.strip()
    
    @classmethod
    def validate_game_input(cls, text: str) -> bool:
        """
        Validate game-related input (speeches, votes, etc.)
        验证游戏相关输入
        
        验证需求: 需求 10.2
        """
        if not text or not isinstance(text, str):
            return False
        
        # Check length
        if len(text) > 500:  # Max speech length
            return False
        
        # Check for dangerous patterns
        for pattern in cls.SQL_INJECTION_PATTERNS + cls.XSS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return False
        
        return True
    
    @classmethod
    def validate_room_name(cls, name: str) -> bool:
        """Validate room name"""
        if not name or not isinstance(name, str):
            return False
        
        # Length check
        if len(name) < 2 or len(name) > 50:
            return False
        
        # Allow letters, numbers, spaces, and some special characters
        pattern = re.compile(r'^[a-zA-Z0-9\s\u4e00-\u9fff_\-\.]{2,50}$')
        return bool(pattern.match(name))


class EncryptionManager:
    """Encryption and decryption utilities for sensitive data"""
    
    def __init__(self):
        self._fernet = None
        self._initialize_encryption()
    
    def _initialize_encryption(self):
        """Initialize encryption with key derived from secret"""
        try:
            # Derive key from secret
            password = settings.SECRET_KEY.encode()
            salt = b'undercover_game_salt'  # In production, use random salt stored securely
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password))
            self._fernet = Fernet(key)
            
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            self._fernet = None
    
    def encrypt_sensitive_data(self, data: str) -> Optional[str]:
        """
        Encrypt sensitive data
        加密敏感数据
        
        验证需求: 需求 10.3
        """
        if not self._fernet or not data:
            return None
        
        try:
            encrypted_data = self._fernet.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted_data).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return None
    
    def decrypt_sensitive_data(self, encrypted_data: str) -> Optional[str]:
        """
        Decrypt sensitive data
        解密敏感数据
        
        验证需求: 需求 10.3
        """
        if not self._fernet or not encrypted_data:
            return None
        
        try:
            decoded_data = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = self._fernet.decrypt(decoded_data)
            return decrypted_data.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None
    
    def hash_sensitive_data(self, data: str, salt: str = None) -> str:
        """
        Hash sensitive data with salt
        使用盐值哈希敏感数据
        
        验证需求: 需求 10.3
        """
        if salt is None:
            salt = secrets.token_hex(16)
        
        # Combine data with salt and secret key
        combined = f"{data}{salt}{settings.SECRET_KEY}"
        hashed = hashlib.sha256(combined.encode()).hexdigest()
        
        return f"{salt}:{hashed}"
    
    def verify_hashed_data(self, data: str, hashed_data: str) -> bool:
        """Verify hashed data"""
        try:
            salt, expected_hash = hashed_data.split(':', 1)
            actual_hash = self.hash_sensitive_data(data, salt)
            return hmac.compare_digest(actual_hash, hashed_data)
        except Exception as e:
            logger.error(f"Hash verification failed: {e}")
            return False


class SessionSecurity:
    """Session security management"""
    
    def __init__(self):
        self.encryption_manager = EncryptionManager()
    
    def generate_secure_token(self, length: int = 32) -> str:
        """
        Generate cryptographically secure token
        生成加密安全令牌
        
        验证需求: 需求 10.4
        """
        return secrets.token_urlsafe(length)
    
    def create_session_fingerprint(self, user_agent: str, ip_address: str) -> str:
        """
        Create session fingerprint for additional security
        创建会话指纹以增强安全性
        
        验证需求: 需求 10.4
        """
        fingerprint_data = f"{user_agent}:{ip_address}:{settings.SECRET_KEY}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()
    
    def validate_session_fingerprint(
        self, 
        stored_fingerprint: str, 
        user_agent: str, 
        ip_address: str
    ) -> bool:
        """Validate session fingerprint"""
        current_fingerprint = self.create_session_fingerprint(user_agent, ip_address)
        return hmac.compare_digest(stored_fingerprint, current_fingerprint)
    
    async def is_session_secure(self, session_data: Dict[str, Any]) -> bool:
        """
        Check if session meets security requirements
        检查会话是否满足安全要求
        
        验证需求: 需求 10.4
        """
        try:
            # Check session age
            created_at = datetime.fromisoformat(session_data.get("created_at", ""))
            max_age = timedelta(hours=24)  # Maximum session age
            
            if datetime.utcnow() - created_at > max_age:
                logger.warning("Session exceeded maximum age")
                return False
            
            # Check for required fields
            required_fields = ["user_id", "created_at", "login_time"]
            for field in required_fields:
                if field not in session_data:
                    logger.warning(f"Session missing required field: {field}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Session security check failed: {e}")
            return False


# Global instances
rate_limiter = RateLimiter()
input_validator = InputValidator()
encryption_manager = EncryptionManager()
session_security = SessionSecurity()


# Convenience functions
async def check_rate_limit(identifier: str, limit: int = None, window: int = None) -> bool:
    """Check if identifier is rate limited"""
    return await rate_limiter.is_rate_limited(identifier, limit, window)


def validate_and_sanitize_input(text: str, max_length: int = 1000) -> str:
    """Validate and sanitize user input"""
    return input_validator.sanitize_input(text, max_length)


def encrypt_data(data: str) -> Optional[str]:
    """Encrypt sensitive data"""
    return encryption_manager.encrypt_sensitive_data(data)


def decrypt_data(encrypted_data: str) -> Optional[str]:
    """Decrypt sensitive data"""
    return encryption_manager.decrypt_sensitive_data(encrypted_data)


def generate_secure_token(length: int = 32) -> str:
    """Generate secure token"""
    return session_security.generate_secure_token(length)