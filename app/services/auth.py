"""
Authentication service
用户认证服务 - 增强安全功能
"""

from datetime import datetime, timedelta
from typing import Optional
import uuid
import logging
import bcrypt

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status, Request
from jose import JWTError, jwt

from app.core.config import settings
from app.utils.session import session_manager
from app.utils.security import (
    input_validator,
    session_security,
    encryption_manager,
    check_rate_limit
)
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserResponse, UserToken
from app.services.audit_logger import audit_logger, AuditEventType

logger = logging.getLogger(__name__)


class AuthService:
    """Authentication service for user registration, login, and session management"""

    def __init__(self):
        self.max_login_attempts = 5
        self.lockout_duration = 900  # 15 minutes

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt directly"""
        # bcrypt has a 72-byte limit
        password_bytes = password.encode('utf-8')[:72]
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password_bytes, salt).decode('utf-8')

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        try:
            password_bytes = plain_password.encode('utf-8')[:72]
            return bcrypt.checkpw(password_bytes, hashed_password.encode('utf-8'))
        except Exception:
            return False
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[dict]:
        """Verify JWT token and return payload"""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            return payload
        except JWTError:
            return None
    
    async def _check_login_rate_limit(self, identifier: str) -> bool:
        """Check login rate limiting"""
        # Skip rate limiting in development/test environment
        if settings.ENVIRONMENT in ["development", "testing"]:
            return False
        return await check_rate_limit(f"login:{identifier}", limit=5, window=300)  # 5 attempts per 5 minutes
    
    def _validate_registration_data(self, user_data: UserCreate) -> None:
        """
        Validate registration data with enhanced security checks
        验证注册数据的增强安全检查
        
        验证需求: 需求 10.2
        """
        # Validate username
        if not input_validator.validate_username(user_data.username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名格式无效：只能包含字母、数字、下划线和中文，长度2-20字符"
            )
        
        # Validate email
        if not input_validator.validate_email(user_data.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱格式无效"
            )
        
        # Validate password
        if not input_validator.validate_password(user_data.password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="密码格式无效：至少8位，包含字母和数字"
            )
        
        # Sanitize inputs
        user_data.username = input_validator.sanitize_input(user_data.username, 20)
        user_data.email = input_validator.sanitize_input(user_data.email, 100)
    
    async def register_user(self, db: AsyncSession, user_data: UserCreate, request: Request = None) -> UserResponse:
        """
        Register a new user with enhanced security
        验证需求: 需求 1.1, 1.2, 10.2
        """
        try:
            # Rate limiting check
            if request:
                client_ip = request.client.host if request.client else "unknown"
                if await self._check_login_rate_limit(client_ip):
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="注册请求过于频繁，请稍后重试"
                    )
            
            # Validate input data
            self._validate_registration_data(user_data)
            
            # Check if username already exists
            stmt = select(User).where(User.username == user_data.username)
            result = await db.execute(stmt)
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="用户名已存在"
                )
            
            # Check if email already exists
            stmt = select(User).where(User.email == user_data.email)
            result = await db.execute(stmt)
            existing_email = result.scalar_one_or_none()
            
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="邮箱已被注册"
                )
            
            # Create new user
            user_id = str(uuid.uuid4())
            hashed_password = self.hash_password(user_data.password)
            
            db_user = User(
                id=user_id,
                username=user_data.username,
                email=user_data.email,
                password_hash=hashed_password
            )
            
            db.add(db_user)
            await db.commit()
            await db.refresh(db_user)
            
            # Log audit event
            client_ip = request.client.host if request and request.client else None
            await audit_logger.log_event(
                event_type=AuditEventType.USER_REGISTER,
                user_id=user_id,
                details={"username": user_data.username, "email": user_data.email},
                ip_address=client_ip,
                success=True
            )
            
            logger.info(f"User registered successfully: {user_data.username}")
            return UserResponse.model_validate(db_user)
            
        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to register user: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="注册失败，请稍后重试"
            )
    
    async def authenticate_user(self, db: AsyncSession, login_data: UserLogin) -> Optional[User]:
        """
        Authenticate user with username/email and password
        验证需求: 需求 1.3, 1.4
        """
        try:
            # Sanitize login input
            username = input_validator.sanitize_input(login_data.username, 100)
            
            # Try to find user by username or email
            stmt = select(User).where(
                (User.username == username) | 
                (User.email == username)
            )
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return None
            
            if not user.is_active:
                return None
            
            if not self.verify_password(login_data.password, user.password_hash):
                return None
            
            return user
            
        except Exception as e:
            logger.error(f"Failed to authenticate user: {e}")
            return None
    
    async def login_user(self, db: AsyncSession, login_data: UserLogin, request: Request = None) -> UserToken:
        """
        Login user and create secure session
        验证需求: 需求 1.3, 1.4, 10.4
        """
        # Rate limiting check
        if request:
            client_ip = request.client.host if request.client else "unknown"
            if await self._check_login_rate_limit(client_ip):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="登录尝试过于频繁，请稍后重试"
                )
        
        # Authenticate user
        user = await self.authenticate_user(db, login_data)
        
        if not user:
            # Log failed login attempt
            client_ip = request.client.host if request and request.client else None
            await audit_logger.log_event(
                event_type=AuditEventType.USER_LOGIN,
                details={"username": login_data.username, "reason": "invalid_credentials"},
                ip_address=client_ip,
                success=False
            )
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Update last login time
        user.last_login = datetime.utcnow()
        await db.commit()
        
        # Create access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = self.create_access_token(
            data={"sub": user.id, "username": user.username},
            expires_delta=access_token_expires
        )
        
        # Create secure session data
        session_data = {
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "login_time": datetime.utcnow().isoformat(),
            "session_token": session_security.generate_secure_token()
        }
        
        # Add session fingerprint if request available
        if request:
            user_agent = request.headers.get("user-agent", "")
            client_ip = request.client.host if request.client else "unknown"
            session_data["fingerprint"] = session_security.create_session_fingerprint(user_agent, client_ip)
        
        await session_manager.create_session(
            user.id, 
            session_data, 
            expire_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        
        # Log successful login
        client_ip = request.client.host if request and request.client else None
        await audit_logger.log_event(
            event_type=AuditEventType.USER_LOGIN,
            user_id=user.id,
            details={"username": user.username},
            ip_address=client_ip,
            success=True
        )
        
        logger.info(f"User logged in successfully: {user.username}")
        
        return UserToken(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user)
        )
    
    async def logout_user(self, user_id: str) -> bool:
        """
        Logout user and clear session securely
        """
        try:
            await session_manager.delete_session(user_id)
            
            # Log logout event
            await audit_logger.log_event(
                event_type=AuditEventType.USER_LOGOUT,
                user_id=user_id,
                details={},
                success=True
            )
            
            logger.info(f"User logged out successfully: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to logout user: {e}")
            return False
    
    async def get_current_user(self, db: AsyncSession, token: str, request: Request = None) -> Optional[User]:
        """
        Get current user from token with enhanced security checks
        验证需求: 需求 1.5, 10.4
        """
        try:
            payload = self.verify_token(token)
            if payload is None:
                logger.warning("Token verification failed")
                return None

            user_id: str = payload.get("sub")
            if user_id is None:
                logger.warning("No user_id in token payload")
                return None

            # 开发环境下简化验证，只检查 token 有效性和用户存在
            if settings.ENVIRONMENT == "development":
                # 直接从数据库获取用户，跳过 session 验证
                stmt = select(User).where(User.id == user_id)
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()

                if user is None or not user.is_active:
                    logger.warning(f"User not found or inactive: {user_id}")
                    return None

                return user

            # 生产环境：完整的 session 验证
            # Check if session exists in Redis using session manager
            session_data = await session_manager.get_session(user_id)
            if session_data is None:
                logger.warning(f"No session found for user: {user_id}")
                return None

            # Validate session security
            if not await session_security.is_session_secure(session_data):
                await session_manager.delete_session(user_id)
                return None

            # Validate session fingerprint if request available
            if request and "fingerprint" in session_data:
                user_agent = request.headers.get("user-agent", "")
                client_ip = request.client.host if request.client else "unknown"

                if not session_security.validate_session_fingerprint(
                    session_data["fingerprint"], user_agent, client_ip
                ):
                    logger.warning(f"Session fingerprint mismatch for user {user_id}")

                    # Log security violation
                    await audit_logger.log_event(
                        event_type=AuditEventType.SECURITY_VIOLATION,
                        user_id=user_id,
                        details={"reason": "session_fingerprint_mismatch"},
                        ip_address=client_ip,
                        success=False
                    )

                    await session_manager.delete_session(user_id)
                    return None

            # Get user from database
            stmt = select(User).where(User.id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

            if user is None or not user.is_active:
                return None

            return user

        except Exception as e:
            logger.error(f"Failed to get current user: {e}")
            return None


# Global auth service instance
auth_service = AuthService()