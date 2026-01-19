"""
Authentication API endpoints
用户认证API端点 - 增强安全功能
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.auth import auth_service
from app.schemas.user import UserCreate, UserLogin, UserResponse, UserToken
from app.models.user import User
from app.utils.security import check_rate_limit

router = APIRouter()
# auto_error=False 使得 HTTPBearer 在没有 token 时不会自动返回 403
# 我们手动处理，统一返回 401 以保持一致性
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Dependency to get current authenticated user with enhanced security"""
    # 检查是否提供了认证凭据
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await auth_service.get_current_user(db, credentials.credentials, request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user with enhanced security validation
    用户注册端点 - 增强安全验证
    
    验证需求: 需求 1.1, 1.2, 10.2
    - 当用户提供有效的用户名、邮箱和密码时，系统应创建新的用户账号
    - 当用户提供已存在的用户名或邮箱时，系统应拒绝注册并显示相应错误信息
    - 当用户输入数据时，系统应验证和清理所有输入内容
    """
    return await auth_service.register_user(db, user_data, request)


@router.post("/login", response_model=UserToken)
async def login(
    login_data: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    User login with enhanced security
    用户登录端点 - 增强安全功能
    
    验证需求: 需求 1.3, 1.4, 10.1, 10.4
    - 当用户提供正确的登录凭据时，系统应验证身份并创建会话
    - 当用户提供错误的登录凭据时，系统应拒绝登录并显示错误信息
    - 当检测到异常请求频率时，系统应实施速率限制
    - 当用户会话管理时，系统应实施安全的会话机制
    """
    return await auth_service.login_user(db, login_data, request)


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    User logout with secure session cleanup
    用户登出端点 - 安全会话清理
    """
    success = await auth_service.logout_user(current_user.id)
    if success:
        return {"message": "登出成功"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登出失败"
        )


@router.get("/profile", response_model=UserResponse)
async def get_profile(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Get current user profile with session validation
    获取当前用户信息 - 会话验证
    
    验证需求: 需求 1.5, 10.4
    - 验证用户会话有效性
    - 当用户会话管理时，系统应实施安全的会话机制
    """
    return UserResponse.model_validate(current_user)


@router.get("/verify")
async def verify_token(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Verify token validity with enhanced security checks
    验证令牌有效性 - 增强安全检查
    
    验证需求: 需求 1.5, 10.4
    - 当用户会话过期时，系统应要求重新登录
    - 当用户会话管理时，系统应实施安全的会话机制
    """
    return {
        "valid": True,
        "user_id": current_user.id,
        "username": current_user.username
    }


@router.post("/refresh")
async def refresh_session(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Refresh user session with security validation
    刷新用户会话 - 安全验证
    
    验证需求: 需求 1.5, 10.4
    - 延长有效会话的过期时间
    - 当用户会话管理时，系统应实施安全的会话机制
    """
    from app.utils.session import session_manager
    
    success = await session_manager.extend_session(current_user.id)
    if success:
        return {"message": "会话已刷新", "user_id": current_user.id}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="会话刷新失败"
        )


@router.get("/security-status")
async def get_security_status(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Get security status for current user session
    获取当前用户会话的安全状态
    """
    from app.utils.session import session_manager
    from app.utils.security import rate_limiter
    
    try:
        # Get session data
        session_data = await session_manager.get_session(current_user.id)
        
        # Get rate limit status
        client_ip = request.client.host if request.client else "unknown"
        rate_status = await rate_limiter.get_rate_limit_status(f"user:{current_user.id}")
        
        return {
            "user_id": current_user.id,
            "session_created": session_data.get("created_at") if session_data else None,
            "last_activity": session_data.get("updated_at") if session_data else None,
            "rate_limit": rate_status,
            "client_ip": client_ip,
            "security_level": "high"
        }
        
    except Exception as e:
        return {
            "user_id": current_user.id,
            "error": str(e),
            "security_level": "unknown"
        }