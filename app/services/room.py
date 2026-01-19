"""
Room management service
房间管理服务 - 异步版本
"""

import uuid
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, func, select, delete
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.models.room import Room, RoomStatus
from app.models.user import User
from app.models.ai_player import AIPlayer
from app.schemas.room import (
    RoomCreate, RoomUpdate, RoomResponse, RoomDetailResponse,
    RoomFilters, PlayerInfo, RoomListResponse
)
from app.services.audit_logger import audit_logger, AuditEventType

logger = logging.getLogger(__name__)


class RoomService:
    """房间管理服务类 - 异步版本"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_room(self, room_data: RoomCreate, creator_id: str) -> RoomResponse:
        """
        创建新房间
        验证需求: 需求 2.1 - 当玩家创建房间时，系统应生成唯一房间ID并设置房间参数
        """
        # 验证创建者存在
        stmt = select(User).where(User.id == creator_id)
        result = await self.db.execute(stmt)
        creator = result.scalar_one_or_none()

        if not creator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="创建者不存在"
            )

        # 生成唯一房间ID
        room_id = str(uuid.uuid4())

        # 准备 settings，包含 AI 模板 ID 列表
        settings = room_data.settings.dict() if room_data.settings else {}
        if room_data.ai_template_ids:
            settings['ai_template_ids'] = room_data.ai_template_ids

        # 创建房间
        db_room = Room(
            id=room_id,
            name=room_data.name,
            creator_id=creator_id,
            max_players=room_data.max_players,
            ai_count=room_data.ai_count,
            password=room_data.password,  # 保存房间密码
            status=RoomStatus.WAITING,
            settings=settings,
            current_players=[creator_id]  # 创建者自动加入房间
        )

        self.db.add(db_room)
        await self.db.commit()
        await self.db.refresh(db_room)

        # Log room creation
        await audit_logger.log_event(
            event_type=AuditEventType.ROOM_CREATE,
            user_id=creator_id,
            details={
                "room_id": room_id,
                "room_name": room_data.name,
                "max_players": room_data.max_players,
                "ai_count": room_data.ai_count
            },
            success=True
        )

        return self._room_to_response(db_room, creator.username)

    def _room_to_response(self, room: Room, creator_name: str = None) -> RoomResponse:
        """Convert Room model to RoomResponse"""
        # 计算总人数：真人玩家 + AI 玩家
        human_count = len(room.current_players) if room.current_players else 0
        total_players = human_count + room.ai_count

        return RoomResponse(
            id=room.id,
            name=room.name,
            creator_id=room.creator_id,
            creator_name=creator_name or "Unknown",
            max_players=room.max_players,
            current_players=total_players,  # 真人 + AI 的总数
            ai_count=room.ai_count,
            has_password=bool(room.password),  # 是否有密码
            status=room.status.value if isinstance(room.status, RoomStatus) else room.status,
            created_at=room.created_at,
            updated_at=room.updated_at
        )

    async def get_room(self, room_id: str) -> Optional[RoomResponse]:
        """获取房间信息"""
        stmt = select(Room).where(Room.id == room_id)
        result = await self.db.execute(stmt)
        room = result.scalar_one_or_none()

        if not room:
            return None

        # Get creator name
        stmt = select(User.username).where(User.id == room.creator_id)
        result = await self.db.execute(stmt)
        creator_name = result.scalar_one_or_none() or "Unknown"

        return self._room_to_response(room, creator_name)

    async def get_room_detail(self, room_id: str) -> Optional[RoomDetailResponse]:
        """获取房间详细信息"""
        stmt = select(Room).where(Room.id == room_id)
        result = await self.db.execute(stmt)
        room = result.scalar_one_or_none()

        if not room:
            return None

        # 获取玩家详细信息
        players = []
        if room.current_players:
            stmt = select(User).where(User.id.in_(room.current_players))
            result = await self.db.execute(stmt)
            users = result.scalars().all()

            for user in users:
                players.append(PlayerInfo(
                    id=user.id,
                    username=user.username,
                    is_ai=False,
                    is_ready=True,
                    is_creator=(user.id == room.creator_id)
                ))

        # 添加 AI 玩家信息（从配置的模板 ID 获取）
        ai_template_ids = room.settings.get('ai_template_ids', []) if room.settings else []

        if ai_template_ids:
            # 获取配置的 AI 玩家
            stmt = select(AIPlayer).where(AIPlayer.id.in_(ai_template_ids))
            result = await self.db.execute(stmt)
            ai_players_db = result.scalars().all()

            for ai_player in ai_players_db:
                players.append(PlayerInfo(
                    id=ai_player.id,
                    username=ai_player.name,
                    is_ai=True,
                    is_ready=True,
                    is_creator=False
                ))
        else:
            # 兼容旧逻辑：没有指定 AI 模板时，显示占位 AI
            for i in range(room.ai_count):
                players.append(PlayerInfo(
                    id=f"ai_{i+1}",
                    username=f"AI玩家{i+1}",
                    is_ai=True,
                    is_ready=True,
                    is_creator=False
                ))

        # Get creator info
        stmt = select(User).where(User.id == room.creator_id)
        result = await self.db.execute(stmt)
        creator = result.scalar_one_or_none()

        return RoomDetailResponse(
            id=room.id,
            name=room.name,
            creator_id=room.creator_id,
            creator_name=creator.username if creator else "Unknown",
            max_players=room.max_players,
            current_players=len(room.current_players) if room.current_players else 0,
            ai_count=room.ai_count,
            status=room.status.value if isinstance(room.status, RoomStatus) else room.status,
            created_at=room.created_at,
            updated_at=room.updated_at,
            players=players
        )

    async def join_room(self, room_id: str, user_id: str, password: Optional[str] = None) -> RoomResponse:
        """
        加入房间
        """
        # 验证用户存在
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )

        # 获取房间
        stmt = select(Room).where(Room.id == room_id)
        result = await self.db.execute(stmt)
        room = result.scalar_one_or_none()

        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="房间不存在"
            )

        # 验证房间状态
        if room.status != RoomStatus.WAITING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="房间不在等待状态，无法加入"
            )

        # 验证房间密码
        if room.password:
            if not password:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="此房间需要密码才能加入"
                )
            if password != room.password:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="房间密码错误"
                )

        # 检查用户是否已经在房间中
        if user_id in (room.current_players or []):
            # 用户已在房间中，视为重新加入（处理异常退出后重连的情况）
            logger.info(f"User {user_id} is rejoining room {room_id}")
            # Get creator name
            stmt = select(User.username).where(User.id == room.creator_id)
            result = await self.db.execute(stmt)
            creator_name = result.scalar_one_or_none() or "Unknown"
            return self._room_to_response(room, creator_name)

        # 检查房间是否已满（真人 + AI 不能超过 max_players）
        human_count = len(room.current_players or [])
        total_count = human_count + room.ai_count
        if total_count >= room.max_players:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="房间已满，无法加入"
            )

        # 加入房间
        current_players = list(room.current_players or [])
        current_players.append(user_id)
        room.current_players = current_players
        room.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(room)

        # Get creator name
        stmt = select(User.username).where(User.id == room.creator_id)
        result = await self.db.execute(stmt)
        creator_name = result.scalar_one_or_none() or "Unknown"

        return self._room_to_response(room, creator_name)

    async def leave_room(self, room_id: str, user_id: str) -> bool:
        """离开房间"""
        stmt = select(Room).where(Room.id == room_id)
        result = await self.db.execute(stmt)
        room = result.scalar_one_or_none()

        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="房间不存在"
            )

        # 检查用户是否在房间中
        if user_id not in (room.current_players or []):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="您不在此房间中"
            )

        # 从房间中移除用户
        current_players = list(room.current_players or [])
        current_players.remove(user_id)

        # 如果是房主离开
        if room.creator_id == user_id:
            if len(current_players) > 0:
                # 转移房主权限给第一个玩家
                room.creator_id = current_players[0]
            else:
                # 房间为空，解散房间
                # 先删除关联的游戏及其相关记录（强制删除）
                await self._cleanup_room_games(room_id, force=True)
                await self.db.delete(room)
                await self.db.commit()
                return True

        room.current_players = current_players
        room.updated_at = datetime.utcnow()

        await self.db.commit()
        return True

    async def _cleanup_room_games(self, room_id: str, force: bool = False) -> None:
        """
        清理房间关联的所有游戏及其相关记录

        Args:
            room_id: 房间ID
            force: 是否强制清理（包括进行中的游戏）
        """
        from app.models.game import Game, Speech, Vote
        from app.models.participant import Participant
        from app.schemas.game import GamePhase

        # 获取房间关联的所有游戏
        stmt = select(Game).where(Game.room_id == room_id)
        result = await self.db.execute(stmt)
        games = result.scalars().all()

        for game in games:
            # 检查游戏是否正在进行中
            if not force and game.current_phase not in [GamePhase.FINISHED, GamePhase.PREPARING, None]:
                logger.warning(f"Skipping cleanup of active game {game.id} (phase: {game.current_phase})")
                # 标记游戏为异常结束
                game.current_phase = GamePhase.FINISHED
                game.finished_at = datetime.utcnow()
                continue

            # 删除投票记录
            vote_stmt = delete(Vote).where(Vote.game_id == game.id)
            await self.db.execute(vote_stmt)

            # 删除发言记录
            speech_stmt = delete(Speech).where(Speech.game_id == game.id)
            await self.db.execute(speech_stmt)

            # 删除参与者记录
            participant_stmt = delete(Participant).where(Participant.game_id == game.id)
            await self.db.execute(participant_stmt)

            # 删除游戏记录
            await self.db.delete(game)

    async def update_room(self, room_id: str, room_data: RoomUpdate, user_id: str) -> RoomResponse:
        """更新房间设置（仅房主可操作）"""
        stmt = select(Room).where(Room.id == room_id)
        result = await self.db.execute(stmt)
        room = result.scalar_one_or_none()

        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="房间不存在"
            )

        # 验证权限
        if room.creator_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有房主可以修改房间设置"
            )

        # 验证房间状态
        if room.status != RoomStatus.WAITING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="游戏已开始，无法修改房间设置"
            )

        # 更新房间信息
        update_data = room_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            if field == 'settings' and value:
                room.settings = value.dict() if hasattr(value, 'dict') else value
            else:
                setattr(room, field, value)

        room.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(room)

        # Get creator name
        stmt = select(User.username).where(User.id == room.creator_id)
        result = await self.db.execute(stmt)
        creator_name = result.scalar_one_or_none() or "Unknown"

        return self._room_to_response(room, creator_name)

    async def list_rooms(self, filters: RoomFilters) -> RoomListResponse:
        """获取房间列表"""
        stmt = select(Room)

        # 应用过滤条件
        conditions = []

        if filters.status:
            conditions.append(Room.status == filters.status)

        if filters.min_players:
            conditions.append(Room.max_players >= filters.min_players)

        if filters.max_players:
            conditions.append(Room.max_players <= filters.max_players)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        # 排序
        stmt = stmt.order_by(Room.created_at.desc())

        # 计算总数
        count_stmt = select(func.count()).select_from(stmt.subquery())
        result = await self.db.execute(count_stmt)
        total = result.scalar() or 0

        # 分页
        offset = (filters.page - 1) * filters.page_size
        stmt = stmt.offset(offset).limit(filters.page_size)

        result = await self.db.execute(stmt)
        rooms = result.scalars().all()

        # 获取所有创建者信息
        creator_ids = [room.creator_id for room in rooms]
        if creator_ids:
            stmt = select(User.id, User.username).where(User.id.in_(creator_ids))
            result = await self.db.execute(stmt)
            creators = {row[0]: row[1] for row in result.fetchall()}
        else:
            creators = {}

        # 转换为响应模型
        room_responses = []
        for room in rooms:
            creator_name = creators.get(room.creator_id, "Unknown")
            room_responses.append(self._room_to_response(room, creator_name))

        has_next = offset + len(rooms) < total
        total_pages = (total + filters.page_size - 1) // filters.page_size

        return RoomListResponse(
            rooms=room_responses,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=total_pages,
            has_next=has_next
        )

    async def kick_player(self, room_id: str, target_user_id: str, operator_id: str) -> bool:
        """踢出玩家（仅房主可操作）"""
        stmt = select(Room).where(Room.id == room_id)
        result = await self.db.execute(stmt)
        room = result.scalar_one_or_none()

        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="房间不存在"
            )

        # 验证权限
        if room.creator_id != operator_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有房主可以踢出玩家"
            )

        # 不能踢出自己
        if target_user_id == operator_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能踢出自己"
            )

        # 检查目标用户是否在房间中
        if target_user_id not in (room.current_players or []):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="目标用户不在房间中"
            )

        # 踢出玩家
        current_players = list(room.current_players or [])
        current_players.remove(target_user_id)
        room.current_players = current_players
        room.updated_at = datetime.utcnow()

        await self.db.commit()
        return True

    async def transfer_ownership(self, room_id: str, new_owner_id: str, current_owner_id: str) -> bool:
        """转移房主权限"""
        stmt = select(Room).where(Room.id == room_id)
        result = await self.db.execute(stmt)
        room = result.scalar_one_or_none()

        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="房间不存在"
            )

        # 验证权限
        if room.creator_id != current_owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有房主可以转移房主权限"
            )

        # 检查新房主是否在房间中
        if new_owner_id not in (room.current_players or []):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="新房主必须在房间中"
            )

        # 转移权限
        room.creator_id = new_owner_id
        room.updated_at = datetime.utcnow()

        await self.db.commit()
        return True

    async def cleanup_empty_rooms(self, max_idle_minutes: int = 30) -> int:
        """清理空闲房间"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=max_idle_minutes)

        # 先查找需要清理的空闲房间
        stmt = select(Room).where(
            and_(
                Room.status == RoomStatus.WAITING,
                Room.updated_at < cutoff_time
            )
        )
        result = await self.db.execute(stmt)
        rooms_to_delete = result.scalars().all()

        deleted_count = 0
        for room in rooms_to_delete:
            try:
                # 先清理关联的游戏记录
                await self._cleanup_room_games(room.id, force=True)
                # 再删除房间
                await self.db.delete(room)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to cleanup room {room.id}: {e}")
                continue

        await self.db.commit()
        return deleted_count

    async def can_start_game(self, room_id: str) -> bool:
        """检查房间是否可以开始游戏"""
        stmt = select(Room).where(Room.id == room_id)
        result = await self.db.execute(stmt)
        room = result.scalar_one_or_none()

        if not room:
            return False

        total_players = len(room.current_players or []) + room.ai_count
        return total_players >= 3

    async def get_room_activity_status(self, room_id: str) -> Optional[Dict[str, Any]]:
        """获取房间活动状态"""
        stmt = select(Room).where(Room.id == room_id)
        result = await self.db.execute(stmt)
        room = result.scalar_one_or_none()

        if not room:
            return None

        now = datetime.utcnow()
        idle_minutes = (now - room.updated_at).total_seconds() / 60

        return {
            "room_id": room_id,
            "last_activity": room.updated_at,
            "idle_minutes": idle_minutes,
            "is_idle": idle_minutes > 30,
            "status": room.status.value if isinstance(room.status, RoomStatus) else room.status,
            "player_count": len(room.current_players or [])
        }

    async def start_game(self, room_id: str, user_id: str) -> bool:
        """开始游戏（仅房主可操作）"""
        stmt = select(Room).where(Room.id == room_id)
        result = await self.db.execute(stmt)
        room = result.scalar_one_or_none()

        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="房间不存在"
            )

        # 验证权限
        if room.creator_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有房主可以开始游戏"
            )

        # 检查是否可以开始游戏
        total_players = len(room.current_players or []) + room.ai_count
        if total_players < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"至少需要3个玩家才能开始游戏，当前有{total_players}个玩家"
            )

        # 更新房间状态
        room.status = RoomStatus.STARTING
        room.updated_at = datetime.utcnow()

        await self.db.commit()
        return True


def get_room_service(db: AsyncSession) -> RoomService:
    """获取房间服务实例"""
    return RoomService(db)
