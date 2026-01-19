"""
Settlement API endpoints
积分结算系统API端点
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, List, Optional

from app.core.database import get_db
from app.services.settlement import get_settlement_service
from app.api.v1.endpoints.auth import get_current_user
from app.models.user import User

router = APIRouter()


@router.post("/games/{game_id}/settlement", response_model=Dict)
async def apply_game_settlement(
    game_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    应用游戏积分结算
    """
    settlement_service = get_settlement_service(db)
    
    try:
        settlement_results = await settlement_service.apply_settlement(game_id)
        return {
            "success": True,
            "game_id": game_id,
            "settlement_results": settlement_results
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="结算处理失败"
        )


@router.get("/games/{game_id}/settlement", response_model=Dict)
async def get_game_settlement(
    game_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取游戏积分结算结果（不执行结算）
    """
    settlement_service = get_settlement_service(db)
    
    try:
        settlement_results = await settlement_service.calculate_game_settlement(game_id)
        return {
            "game_id": game_id,
            "settlement_results": settlement_results
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取结算信息失败"
        )


@router.get("/games/{game_id}/players/{player_id}/performance", response_model=Dict)
async def get_player_performance(
    game_id: str,
    player_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取玩家在特定游戏中的表现分析
    """
    settlement_service = get_settlement_service(db)
    
    try:
        performance = await settlement_service.get_player_performance_analysis(game_id, player_id)
        return performance
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取表现分析失败"
        )


@router.get("/games/{game_id}/mvp", response_model=Dict)
async def get_game_mvp(
    game_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取游戏MVP分析
    """
    settlement_service = get_settlement_service(db)
    
    try:
        mvp_analysis = await settlement_service.get_mvp_analysis(game_id)
        if not mvp_analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="游戏未结束或无MVP数据"
            )
        return mvp_analysis
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取MVP分析失败"
        )


@router.get("/users/{user_id}/score", response_model=Dict)
async def get_user_real_time_score(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取用户实时积分
    """
    # 只允许查看自己的积分或管理员查看
    if current_user.id != user_id:
        # 这里可以添加管理员权限检查
        pass
    
    settlement_service = get_settlement_service(db)
    
    try:
        score = await settlement_service.get_real_time_score(user_id)
        if score is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        return {
            "user_id": user_id,
            "score": score
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取积分失败"
        )


@router.get("/users/{user_id}/stats", response_model=Dict)
async def get_user_real_time_stats(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取用户实时统计数据
    """
    # 只允许查看自己的统计或管理员查看
    if current_user.id != user_id:
        # 这里可以添加管理员权限检查
        pass
    
    settlement_service = get_settlement_service(db)
    
    try:
        stats = await settlement_service.get_real_time_user_stats(user_id)
        if not stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        return {
            "user_id": user_id,
            "stats": stats
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取统计数据失败"
        )


@router.post("/users/{user_id}/stats/recalculate", response_model=Dict)
async def recalculate_user_stats(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    重新计算用户统计数据（管理员功能）
    """
    # 这里应该添加管理员权限检查
    # if not current_user.is_admin:
    #     raise HTTPException(status_code=403, detail="权限不足")
    
    settlement_service = get_settlement_service(db)
    
    try:
        recalculated_stats = await settlement_service.recalculate_user_stats(user_id)
        return {
            "success": True,
            "user_id": user_id,
            "recalculated_stats": recalculated_stats
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="重新计算统计数据失败"
        )


@router.delete("/users/{user_id}/cache", response_model=Dict)
async def invalidate_user_cache(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    清除用户缓存（管理员功能）
    """
    # 这里应该添加管理员权限检查
    # if not current_user.is_admin:
    #     raise HTTPException(status_code=403, detail="权限不足")
    
    settlement_service = get_settlement_service(db)
    
    try:
        await settlement_service.invalidate_user_cache(user_id)
        return {
            "success": True,
            "message": f"用户 {user_id} 的缓存已清除"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="清除缓存失败"
        )


@router.get("/settlement/history", response_model=List[Dict])
async def get_settlement_history(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取结算历史记录（管理员功能）
    """
    # 这里应该添加管理员权限检查
    # if not current_user.is_admin:
    #     raise HTTPException(status_code=403, detail="权限不足")
    
    settlement_service = get_settlement_service(db)
    
    try:
        history = await settlement_service.get_settlement_history(limit)
        return history
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取结算历史失败"
        )