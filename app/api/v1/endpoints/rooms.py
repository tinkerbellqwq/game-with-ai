"""
Room management API endpoints
房间管理API端点
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.auth import auth_service
from app.api.v1.endpoints.auth import get_current_user
from app.services.room import RoomService
from app.models.user import User
from app.schemas.room import (
    RoomCreate, RoomUpdate, RoomResponse, RoomDetailResponse,
    RoomListResponse, RoomFilters, RoomJoinRequest, RoomJoinResponse,
    RoomAction
)
from app.schemas.common import MessageResponse

router = APIRouter()


async def get_room_service(db: AsyncSession = Depends(get_db)) -> RoomService:
    """获取房间服务依赖"""
    return RoomService(db)


@router.post("/", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    room_data: RoomCreate,
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service)
):
    """
    创建新房间
    
    - **name**: 房间名称
    - **max_players**: 最大玩家数 (3-10)
    - **ai_count**: AI玩家数量 (0-5)
    - **settings**: 房间设置
    """
    try:
        room = await room_service.create_room(room_data, current_user.id)
        return room
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建房间失败: {str(e)}"
        )


@router.get("/", response_model=RoomListResponse)
async def list_rooms(
    status_filter: str = None,
    has_slots: bool = None,
    min_players: int = None,
    max_players: int = None,
    search: str = None,
    page: int = 1,
    page_size: int = 20,
    room_service: RoomService = Depends(get_room_service)
):
    """
    获取房间列表
    
    - **status**: 房间状态过滤 (waiting, starting, playing, finished)
    - **has_slots**: 是否有空位
    - **min_players**: 最小玩家数
    - **max_players**: 最大玩家数
    - **search**: 搜索关键词
    - **page**: 页码
    - **page_size**: 每页数量
    """
    try:
        # 构建过滤条件
        filters = RoomFilters(
            status=status_filter,
            has_slots=has_slots,
            min_players=min_players,
            max_players=max_players,
            search=search,
            page=page,
            page_size=page_size
        )
        
        rooms = await room_service.list_rooms(filters)
        return rooms
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取房间列表失败: {str(e)}"
        )


@router.get("/{room_id}", response_model=RoomDetailResponse)
async def get_room(
    room_id: str,
    room_service: RoomService = Depends(get_room_service)
):
    """
    获取房间详细信息
    
    - **room_id**: 房间ID
    """
    room = await room_service.get_room_detail(room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="房间不存在"
        )
    return room


@router.post("/{room_id}/join", response_model=RoomJoinResponse)
async def join_room(
    room_id: str,
    join_data: RoomJoinRequest = RoomJoinRequest(),
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service)
):
    """
    加入房间

    - **room_id**: 房间ID
    - **password**: 房间密码（如果需要）
    """
    try:
        room = await room_service.join_room(room_id, current_user.id, join_data.password)
        return RoomJoinResponse(
            success=True,
            message="成功加入房间",
            room=room
        )
    except HTTPException as e:
        return RoomJoinResponse(
            success=False,
            message=e.detail,
            room=None
        )
    except Exception as e:
        return RoomJoinResponse(
            success=False,
            message=f"加入房间失败: {str(e)}",
            room=None
        )


@router.post("/{room_id}/leave", response_model=MessageResponse)
async def leave_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service)
):
    """
    离开房间
    
    - **room_id**: 房间ID
    """
    try:
        success = await room_service.leave_room(room_id, current_user.id)
        if success:
            return MessageResponse(message="成功离开房间")
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="离开房间失败"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"离开房间失败: {str(e)}"
        )


@router.put("/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: str,
    room_data: RoomUpdate,
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service)
):
    """
    更新房间设置（仅房主可操作）
    
    - **room_id**: 房间ID
    - **name**: 房间名称
    - **max_players**: 最大玩家数
    - **ai_count**: AI玩家数量
    - **settings**: 房间设置
    """
    try:
        room = await room_service.update_room(room_id, room_data, current_user.id)
        return room
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新房间失败: {str(e)}"
        )


@router.post("/{room_id}/action", response_model=MessageResponse)
async def room_action(
    room_id: str,
    action_data: RoomAction,
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service)
):
    """
    房间操作
    
    - **room_id**: 房间ID
    - **action**: 操作类型 (start_game, kick_player, transfer_owner)
    - **target_user_id**: 目标用户ID（踢人或转移房主时使用）
    """
    try:
        if action_data.action == "start_game":
            success = await room_service.start_game(room_id, current_user.id)
            if success:
                return MessageResponse(message="游戏即将开始")
            
        elif action_data.action == "kick_player":
            if not action_data.target_user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="踢人操作需要指定目标用户ID"
                )
            success = await room_service.kick_player(
                room_id, action_data.target_user_id, current_user.id
            )
            if success:
                return MessageResponse(message="成功踢出玩家")
                
        elif action_data.action == "transfer_owner":
            if not action_data.target_user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="转移房主操作需要指定目标用户ID"
                )
            success = await room_service.transfer_ownership(
                room_id, action_data.target_user_id, current_user.id
            )
            if success:
                return MessageResponse(message="成功转移房主权限")
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的操作类型: {action_data.action}"
            )
            
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="操作失败"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"操作失败: {str(e)}"
        )


@router.delete("/{room_id}", response_model=MessageResponse)
async def delete_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service)
):
    """
    删除房间（仅房主可操作，等同于解散房间）
    
    - **room_id**: 房间ID
    """
    try:
        # 通过让房主离开房间来解散房间
        success = await room_service.leave_room(room_id, current_user.id)
        if success:
            return MessageResponse(message="房间已解散")
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="解散房间失败"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解散房间失败: {str(e)}"
        )


# 后台任务：清理空闲房间
@router.post("/cleanup", response_model=MessageResponse)
async def cleanup_rooms(
    background_tasks: BackgroundTasks,
    room_service: RoomService = Depends(get_room_service)
):
    """
    清理空闲房间（管理员功能）
    """
    try:
        count = await room_service.cleanup_empty_rooms()
        return MessageResponse(message=f"已清理 {count} 个空闲房间")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清理房间失败: {str(e)}"
        )


@router.get("/my-rooms", response_model=List[RoomResponse])
async def get_my_rooms(
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service)
):
    """
    获取我创建的房间列表
    """
    try:
        filters = RoomFilters(page=1, page_size=100)  # 获取所有房间
        all_rooms = await room_service.list_rooms(filters)
        
        # 过滤出当前用户创建的房间
        my_rooms = [room for room in all_rooms.rooms if room.creator_id == current_user.id]
        
        return my_rooms
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取房间列表失败: {str(e)}"
        )


@router.get("/joined-rooms", response_model=List[RoomResponse])
async def get_joined_rooms(
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
    db: AsyncSession = Depends(get_db)
):
    """
    获取我加入的房间列表
    """
    try:
        from sqlalchemy import select
        from app.models.room import Room
        from sqlalchemy.dialects.mysql import JSON

        # 直接查询包含当前用户ID的房间
        # 对于 MySQL JSON 列，使用 JSON_CONTAINS 函数
        stmt = select(Room).where(
            Room.current_players.contains([current_user.id])
        )
        result = await db.execute(stmt)
        rooms = result.scalars().all()

        # 转换为响应格式
        response_rooms = []
        for room in rooms:
            # 获取创建者名称
            creator_stmt = select(User.username).where(User.id == room.creator_id)
            creator_result = await db.execute(creator_stmt)
            creator_name = creator_result.scalar_one_or_none() or "Unknown"

            response_rooms.append(RoomResponse(
                id=room.id,
                name=room.name,
                creator_id=room.creator_id,
                creator_name=creator_name,
                max_players=room.max_players,
                current_players=len(room.current_players) if room.current_players else 0,
                ai_count=room.ai_count,
                status=room.status.value if hasattr(room.status, 'value') else room.status,
                created_at=room.created_at,
                updated_at=room.updated_at
            ))

        return response_rooms
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取房间列表失败: {str(e)}"
        )


@router.get("/statistics", response_model=Dict[str, Any])
async def get_room_statistics(
    room_service: RoomService = Depends(get_room_service)
):
    """
    获取房间统计信息
    """
    try:
        # 获取所有房间
        filters = RoomFilters(page=1, page_size=1000)
        all_rooms = await room_service.list_rooms(filters)

        # 统计各种状态的房间数量
        stats = {
            "total_rooms": all_rooms.total,
            "waiting_rooms": len([r for r in all_rooms.rooms if r.status == "waiting"]),
            "playing_rooms": len([r for r in all_rooms.rooms if r.status == "playing"]),
            "finished_rooms": len([r for r in all_rooms.rooms if r.status == "finished"]),
            "rooms_with_slots": len([r for r in all_rooms.rooms if r.current_players < r.max_players]),
            "average_players": sum(r.current_players for r in all_rooms.rooms) / max(1, len(all_rooms.rooms)),
            "rooms_with_ai": len([r for r in all_rooms.rooms if r.ai_count > 0])
        }

        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计信息失败: {str(e)}"
        )


@router.get("/{room_id}/activity", response_model=Dict[str, Any])
async def get_room_activity(
    room_id: str,
    room_service: RoomService = Depends(get_room_service)
):
    """
    获取房间活动状态
    """
    try:
        activity = await room_service.get_room_activity_status(room_id)
        if not activity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="房间不存在"
            )
        return activity
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取房间活动状态失败: {str(e)}"
        )