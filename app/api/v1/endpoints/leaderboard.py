"""
Leaderboard API endpoints
排行榜API端点
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.auth import AuthService
from app.services.leaderboard import leaderboard_service
from app.schemas.user import UserResponse
from app.schemas.leaderboard import (
    LeaderboardResponse, LeaderboardQuery, UserRankInfo, PersonalStats
)

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(security)
) -> UserResponse:
    """Get current authenticated user"""
    auth_service = AuthService()
    user = await auth_service.get_current_user(db, token.credentials)
    
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials"
        )
    
    return UserResponse.from_orm(user)


@router.get("/", response_model=LeaderboardResponse)
async def get_leaderboard(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页大小"),
    sort_by: str = Query(default="score", description="排序字段"),
    order: str = Query(default="desc", description="排序方向"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取排行榜
    
    - **page**: 页码 (默认: 1)
    - **page_size**: 每页大小 (默认: 20, 最大: 100)
    - **sort_by**: 排序字段 (默认: score)
    - **order**: 排序方向 (desc/asc, 默认: desc)
    """
    try:
        # 验证排序字段
        valid_sort_fields = ["score", "games_played", "games_won", "created_at"]
        if sort_by not in valid_sort_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sort field. Must be one of: {', '.join(valid_sort_fields)}"
            )
        
        # 验证排序方向
        if order.lower() not in ["asc", "desc"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid order. Must be 'asc' or 'desc'"
            )
        
        query = LeaderboardQuery(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            order=order
        )
        
        leaderboard = await leaderboard_service.get_leaderboard(query, db)
        return leaderboard
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting leaderboard: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/my-rank", response_model=UserRankInfo)
async def get_my_rank(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取当前用户的排名信息
    """
    try:
        user_rank = await leaderboard_service.get_user_rank(current_user.id, db)
        
        if not user_rank:
            raise HTTPException(status_code=404, detail="User rank not found")
        
        return user_rank
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user rank for {current_user.id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/user/{user_id}/rank", response_model=UserRankInfo)
async def get_user_rank(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定用户的排名信息
    
    - **user_id**: 用户ID
    """
    try:
        user_rank = await leaderboard_service.get_user_rank(user_id, db)
        
        if not user_rank:
            raise HTTPException(status_code=404, detail="User not found or inactive")
        
        return user_rank
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user rank for {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/my-stats", response_model=PersonalStats)
async def get_my_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取当前用户的详细统计信息
    """
    try:
        personal_stats = await leaderboard_service.get_personal_stats(current_user.id, db)
        
        if not personal_stats:
            raise HTTPException(status_code=404, detail="User stats not found")
        
        return personal_stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting personal stats for {current_user.id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/user/{user_id}/stats", response_model=PersonalStats)
async def get_user_stats(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定用户的详细统计信息
    
    - **user_id**: 用户ID
    """
    try:
        personal_stats = await leaderboard_service.get_personal_stats(user_id, db)
        
        if not personal_stats:
            raise HTTPException(status_code=404, detail="User not found or inactive")
        
        return personal_stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting personal stats for {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/refresh-cache")
async def refresh_leaderboard_cache(
    current_user: UserResponse = Depends(get_current_user)
):
    """
    刷新排行榜缓存 (管理员功能)
    """
    try:
        # TODO: 添加管理员权限检查
        await leaderboard_service.invalidate_leaderboard_cache()
        
        return {"message": "Leaderboard cache refreshed successfully"}
        
    except Exception as e:
        logger.error(f"Error refreshing leaderboard cache: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")