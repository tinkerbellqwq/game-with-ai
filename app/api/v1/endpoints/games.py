"""
Game management API endpoints
游戏管理API端点 - 完整游戏流程集成
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.models.user import User
from app.schemas.game import (
    GameCreate, GameState, GameResponse, SpeechCreate, VoteCreate,
    VoteResult, PlayerRole, GamePhase
)
from app.schemas.common import MessageResponse
from app.services.game import GameEngine, GameStateManager
from app.services.room import RoomService
from app.services.settlement import get_settlement_service
from app.services.ai_player import get_ai_player_service
from app.websocket.connection_manager import connection_manager

logger = logging.getLogger(__name__)
router = APIRouter()


def get_game_engine(db: AsyncSession = Depends(get_db)) -> GameEngine:
    """获取游戏引擎依赖"""
    return GameEngine(db)


def get_game_state_manager(db: AsyncSession = Depends(get_db)) -> GameStateManager:
    """获取游戏状态管理器依赖"""
    return GameStateManager(db)


def get_room_service(db: AsyncSession = Depends(get_db)) -> RoomService:
    """获取房间服务依赖"""
    return RoomService(db)


@router.post("/", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_game(
    game_data: GameCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    game_engine: GameEngine = Depends(get_game_engine),
    room_service: RoomService = Depends(get_room_service),
    db: AsyncSession = Depends(get_db)
):
    """
    创建新游戏
    
    - **room_id**: 房间ID
    - **word_pair_id**: 词汇对ID（可选）
    - **difficulty**: 难度等级（可选）
    - **category**: 词汇类别（可选）
    """
    try:
        # 验证房间存在且用户是房主
        room = await room_service.get_room(game_data.room_id)
        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="房间不存在"
            )
        
        if room.creator_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有房主可以开始游戏"
            )

        # 获取房间内的玩家
        room_detail = await room_service.get_room_detail(game_data.room_id)
        if not room_detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="房间详情不存在"
            )

        # 获取真人玩家
        human_player_ids = [p.id for p in room_detail.players if not p.is_ai]

        # 从数据库获取用户对象
        from sqlalchemy import select
        from app.models.ai_player import AIPlayer
        stmt = select(User).filter(User.id.in_(human_player_ids))
        result = await db.execute(stmt)
        players = result.scalars().all()

        if len(players) < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="至少需要1名真人玩家"
            )

        # 获取AI玩家 - 优先使用房间配置的 AI 模板
        ai_players = []

        # 检查房间是否配置了 AI 模板 ID
        room_db = await room_service.get_room(game_data.room_id)
        ai_template_ids = []
        if room_db:
            # 需要从数据库重新获取完整的房间信息以获取 settings
            from app.models.room import Room
            stmt = select(Room).where(Room.id == game_data.room_id)
            result = await db.execute(stmt)
            room_model = result.scalar_one_or_none()
            if room_model and room_model.settings:
                ai_template_ids = room_model.settings.get('ai_template_ids', [])

        if ai_template_ids:
            # 使用房间配置的 AI 模板
            logger.info(f"Using configured AI templates: {ai_template_ids}")
            stmt = select(AIPlayer).where(AIPlayer.id.in_(ai_template_ids))
            result = await db.execute(stmt)
            ai_players = list(result.scalars().all())
            logger.info(f"Loaded {len(ai_players)} AI players from templates")
        elif room.ai_count > 0:
            # 没有配置模板时，从数据库获取活跃的 AI 模板
            logger.info(f"No AI templates configured, fetching {room.ai_count} active AI players from database")
            stmt = select(AIPlayer).where(AIPlayer.is_active == True).limit(room.ai_count)
            result = await db.execute(stmt)
            ai_players = list(result.scalars().all())

            # 如果数据库中没有足够的 AI 模板，才创建新的
            if len(ai_players) < room.ai_count:
                logger.warning(f"Not enough AI templates in database ({len(ai_players)}/{room.ai_count}), creating temporary ones")
                ai_service = get_ai_player_service(db)
                additional_count = room.ai_count - len(ai_players)
                additional_ai = await ai_service.create_ai_players_for_room(
                    room_id=game_data.room_id,
                    count=additional_count
                )
                ai_players.extend(additional_ai)

        # 检查总玩家数
        total_players = len(players) + len(ai_players)
        if total_players < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"至少需要3名玩家才能开始游戏，当前有{total_players}名玩家"
            )
        
        # 创建游戏
        game_state = await game_engine.create_game(game_data, list(players), ai_players)
        
        # 广播游戏创建消息
        await connection_manager.broadcast_to_room(game_data.room_id, {
            "type": "game_created",
            "data": {
                "game_id": game_state.id,
                "players": [
                    {
                        "id": p.id,
                        "username": p.username,
                        "is_ai": p.is_ai
                    }
                    for p in game_state.players
                ]
            }
        })
        
        logger.info(f"Game created: {game_state.id} in room {game_data.room_id}")
        
        return {
            "success": True,
            "message": "游戏创建成功",
            "game_id": game_state.id,
            "player_count": len(game_state.players),
            "phase": game_state.current_phase.value
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create game: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建游戏失败: {str(e)}"
        )


@router.post("/{game_id}/start", response_model=Dict[str, Any])
async def start_game(
    game_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    game_engine: GameEngine = Depends(get_game_engine)
):
    """
    开始游戏

    - **game_id**: 游戏ID
    """
    try:
        logger.info(f"[START_GAME] Starting game {game_id} by user {current_user.id}")
        game_state = await game_engine.start_game(game_id)
        logger.info(f"[START_GAME] Game state: phase={game_state.current_phase.value}, speaker={game_state.current_speaker}")

        # 广播游戏开始消息
        await connection_manager.broadcast_to_room(game_state.room_id, {
            "type": "game_started",
            "data": {
                "game_id": game_id,
                "current_phase": game_state.current_phase.value,
                "current_speaker": game_state.current_speaker,
                "round_number": game_state.round_number
            }
        })

        # 如果第一个发言者是AI，使用 asyncio.create_task 处理（确保任务被触发）
        if game_state.current_speaker:
            current_player = next(
                (p for p in game_state.players if p.id == game_state.current_speaker),
                None
            )
            logger.info(f"[START_GAME] First speaker: {current_player.username if current_player else 'None'}, is_ai: {current_player.is_ai if current_player else 'N/A'}")
            if current_player and current_player.is_ai:
                logger.info(f"[START_GAME] Scheduling AI player {current_player.username} with asyncio.create_task (3s delay)")
                # 使用 asyncio.create_task 确保任务被触发，添加延迟等待弹窗消失
                asyncio.create_task(process_ai_turn(game_id, initial_delay=3.0))

        logger.info(f"Game started: {game_id}")
        
        return {
            "success": True,
            "message": "游戏已开始",
            "game_id": game_id,
            "current_phase": game_state.current_phase.value,
            "current_speaker": game_state.current_speaker
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to start game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"开始游戏失败: {str(e)}"
        )


@router.get("/{game_id}", response_model=Dict[str, Any])
async def get_game(
    game_id: str,
    current_user: User = Depends(get_current_user),
    game_state_manager: GameStateManager = Depends(get_game_state_manager)
):
    """
    获取游戏状态
    
    - **game_id**: 游戏ID
    """
    try:
        game_response = await game_state_manager.get_game_response(game_id, current_user.id)
        
        # 游戏结束时显示所有玩家的角色和词汇
        is_finished = game_response.game.current_phase == GamePhase.FINISHED

        return {
            "success": True,
            "game": {
                "id": game_response.game.id,
                "room_id": game_response.game.room_id,
                "current_phase": game_response.game.current_phase.value,
                "current_speaker": game_response.game.current_speaker,
                "current_voter": game_response.game.current_voter,
                "current_voter_username": game_response.game.current_voter_username,
                "round_number": game_response.game.round_number,
                "winner_role": game_response.game.winner_role.value if game_response.game.winner_role else None,
                "winner_players": game_response.game.winner_players or [],
                "players": [
                    {
                        "id": p.id,
                        "username": p.username,
                        "is_alive": p.is_alive,
                        "is_ai": p.is_ai,
                        "is_ready": p.is_ready,
                        # 游戏结束后揭示角色和词汇
                        "role": p.role.value if is_finished and p.role else None,
                        "word": p.word if is_finished else None
                    }
                    for p in game_response.game.players
                ],
                "eliminated_players": game_response.game.eliminated_players
            },
            "current_user": {
                "role": game_response.current_user_role.value if game_response.current_user_role else None,
                "word": game_response.current_user_word,
                "can_speak": game_response.can_speak,
                "can_vote": game_response.can_vote
            },
            "time_remaining": game_response.time_remaining
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to get game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取游戏状态失败: {str(e)}"
        )


@router.post("/{game_id}/ready", response_model=Dict[str, Any])
async def set_player_ready(
    game_id: str,
    ready: bool = True,
    current_user: User = Depends(get_current_user),
    game_state_manager: GameStateManager = Depends(get_game_state_manager)
):
    """
    设置玩家准备状态
    
    - **game_id**: 游戏ID
    - **ready**: 是否准备就绪
    """
    try:
        game_state = await game_state_manager.set_player_ready(game_id, current_user.id, ready)
        
        # 广播玩家准备状态
        await connection_manager.broadcast_to_room(game_state.room_id, {
            "type": "player_ready",
            "data": {
                "game_id": game_id,
                "player_id": current_user.id,
                "ready": ready,
                "all_ready": all(p.is_ready for p in game_state.players)
            }
        })
        
        return {
            "success": True,
            "message": "准备状态已更新",
            "ready": ready,
            "all_ready": all(p.is_ready for p in game_state.players)
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to set player ready for game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"设置准备状态失败: {str(e)}"
        )


@router.post("/{game_id}/speech", response_model=Dict[str, Any])
async def submit_speech(
    game_id: str,
    speech_data: SpeechCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    game_engine: GameEngine = Depends(get_game_engine)
):
    """
    提交发言

    - **game_id**: 游戏ID
    - **content**: 发言内容
    """
    try:
        logger.info(f"[SPEECH] User {current_user.id} submitting speech for game {game_id}")
        game_state = await game_engine.handle_speech(game_id, current_user.id, speech_data)
        logger.info(f"[SPEECH] After speech: phase={game_state.current_phase.value}, next_speaker={game_state.current_speaker}")

        # 广播发言消息
        await connection_manager.broadcast_to_room(game_state.room_id, {
            "type": "speech_submitted",
            "data": {
                "game_id": game_id,
                "player_id": current_user.id,
                "content": speech_data.content,
                "round_number": game_state.round_number,
                "current_phase": game_state.current_phase.value,
                "next_speaker": game_state.current_speaker
            }
        })

        # 如果下一个发言者是AI，使用异步任务处理（不阻塞响应）
        if game_state.current_speaker and game_state.current_phase == GamePhase.SPEAKING:
            current_player = next(
                (p for p in game_state.players if p.id == game_state.current_speaker),
                None
            )
            logger.info(f"[SPEECH] Next speaker: {current_player.username if current_player else 'None'}, is_ai: {current_player.is_ai if current_player else 'N/A'}")
            if current_player and current_player.is_ai:
                logger.info(f"[SPEECH] Scheduling AI player {current_player.username} in background")
                # 使用异步任务，不阻塞响应
                asyncio.create_task(process_ai_turn(game_id))

        # 如果进入投票阶段，处理AI投票
        if game_state.current_phase == GamePhase.VOTING:
            logger.info(f"[SPEECH] Entering voting phase, triggering AI votes")
            asyncio.create_task(process_ai_votes(game_id))

        return {
            "success": True,
            "message": "发言已提交",
            "current_phase": game_state.current_phase.value,
            "next_speaker": game_state.current_speaker
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to submit speech for game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"提交发言失败: {str(e)}"
        )


@router.post("/{game_id}/skip-speech", response_model=Dict[str, Any])
async def skip_speech(
    game_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    game_engine: GameEngine = Depends(get_game_engine)
):
    """
    跳过发言
    
    - **game_id**: 游戏ID
    """
    try:
        game_state = await game_engine.skip_speech(game_id, current_user.id)
        
        # 广播跳过发言消息
        await connection_manager.broadcast_to_room(game_state.room_id, {
            "type": "speech_skipped",
            "data": {
                "game_id": game_id,
                "player_id": current_user.id,
                "round_number": game_state.round_number,
                "current_phase": game_state.current_phase.value,
                "next_speaker": game_state.current_speaker
            }
        })
        
        # 如果下一个发言者是AI，处理AI发言
        if game_state.current_speaker and game_state.current_phase == GamePhase.SPEAKING:
            current_player = next(
                (p for p in game_state.players if p.id == game_state.current_speaker),
                None
            )
            if current_player and current_player.is_ai:
                asyncio.create_task(process_ai_turn(game_id))

        # 如果进入投票阶段，处理AI投票
        if game_state.current_phase == GamePhase.VOTING:
            asyncio.create_task(process_ai_votes(game_id))

        return {
            "success": True,
            "message": "已跳过发言",
            "current_phase": game_state.current_phase.value,
            "next_speaker": game_state.current_speaker
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to skip speech for game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"跳过发言失败: {str(e)}"
        )


@router.post("/{game_id}/vote", response_model=Dict[str, Any])
async def submit_vote(
    game_id: str,
    vote_data: VoteCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    game_engine: GameEngine = Depends(get_game_engine),
    db: AsyncSession = Depends(get_db)
):
    """
    提交投票

    - **game_id**: 游戏ID
    - **target_id**: 被投票玩家ID
    """
    try:
        game_state = await game_engine.handle_vote(game_id, current_user.id, vote_data)

        # 广播投票消息，包含下一个投票者信息
        await connection_manager.broadcast_to_room(game_state.room_id, {
            "type": "vote_submitted",
            "data": {
                "game_id": game_id,
                "voter_id": current_user.id,
                "voter_name": current_user.username,
                "target_id": vote_data.target_id,
                "round_number": game_state.round_number,
                "is_ai": False,
                "current_phase": game_state.current_phase.value,
                "current_voter": game_state.current_voter,
                "current_voter_username": game_state.current_voter_username
            }
        })

        # 检查游戏是否结束
        if game_state.current_phase == GamePhase.FINISHED:
            # 广播游戏结束消息
            await broadcast_game_end(game_engine, game_state)

            # 触发积分结算
            asyncio.create_task(process_settlement(game_id))
        elif game_state.current_phase == GamePhase.SPEAKING:
            # 新一轮开始，广播回合变化
            await connection_manager.broadcast_to_room(game_state.room_id, {
                "type": "round_started",
                "data": {
                    "game_id": game_id,
                    "round_number": game_state.round_number,
                    "current_phase": game_state.current_phase.value,
                    "current_speaker": game_state.current_speaker
                }
            })
            # 如果第一个发言者是AI，处理AI发言
            if game_state.current_speaker:
                current_player = next(
                    (p for p in game_state.players if p.id == game_state.current_speaker),
                    None
                )
                if current_player and current_player.is_ai:
                    asyncio.create_task(process_ai_turn(game_id))
        elif game_state.current_phase == GamePhase.VOTING and game_state.current_voter:
            # 还在投票阶段，检查下一个投票者是否是 AI
            next_voter = next(
                (p for p in game_state.alive_players if p.id == game_state.current_voter),
                None
            )
            if next_voter and next_voter.is_ai:
                asyncio.create_task(process_ai_votes(game_id))

        return {
            "success": True,
            "message": "投票已提交",
            "current_phase": game_state.current_phase.value,
            "current_voter": game_state.current_voter,
            "round_number": game_state.round_number
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to submit vote for game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"提交投票失败: {str(e)}"
        )


@router.get("/{game_id}/result", response_model=Dict[str, Any])
async def get_game_result(
    game_id: str,
    current_user: User = Depends(get_current_user),
    game_engine: GameEngine = Depends(get_game_engine)
):
    """
    获取游戏结果
    
    - **game_id**: 游戏ID
    """
    try:
        result = await game_engine.get_game_result(game_id)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="游戏结果不存在或游戏尚未结束"
            )
        
        return {
            "success": True,
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get game result for {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取游戏结果失败: {str(e)}"
        )


@router.get("/{game_id}/summary", response_model=Dict[str, Any])
async def get_game_summary(
    game_id: str,
    current_user: User = Depends(get_current_user),
    game_state_manager: GameStateManager = Depends(get_game_state_manager)
):
    """
    获取游戏总结
    
    - **game_id**: 游戏ID
    """
    try:
        summary = await game_state_manager.get_game_summary(game_id)
        
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="游戏总结不存在或游戏尚未结束"
            )
        
        return {
            "success": True,
            "summary": summary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get game summary for {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取游戏总结失败: {str(e)}"
        )


@router.get("/{game_id}/mvp", response_model=Dict[str, Any])
async def get_game_mvp(
    game_id: str,
    current_user: User = Depends(get_current_user),
    game_engine: GameEngine = Depends(get_game_engine)
):
    """
    获取游戏MVP
    
    - **game_id**: 游戏ID
    """
    try:
        mvp = await game_engine.get_mvp_player(game_id)
        
        if not mvp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="MVP信息不存在或游戏尚未结束"
            )
        
        return {
            "success": True,
            "mvp": mvp
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get MVP for game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取MVP失败: {str(e)}"
        )


@router.get("/{game_id}/speeches", response_model=Dict[str, Any])
async def get_game_speeches(
    game_id: str,
    round_number: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    game_engine: GameEngine = Depends(get_game_engine)
):
    """
    获取游戏发言记录

    - **game_id**: 游戏ID
    - **round_number**: 轮次（可选）
    """
    try:
        speeches = await game_engine.get_speeches(game_id, round_number)

        return {
            "success": True,
            "speeches": [
                {
                    "id": s.id,
                    "player_id": s.participant.player_id if s.participant else None,
                    "player_name": s.participant.username if s.participant else None,
                    "is_ai": s.participant.is_ai if s.participant else False,
                    "content": s.content,
                    "round_number": s.round_number,
                    "speech_order": s.speech_order,
                    "created_at": s.created_at.isoformat() if s.created_at else None
                }
                for s in speeches
            ]
        }

    except Exception as e:
        logger.error(f"Failed to get speeches for game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取发言记录失败: {str(e)}"
        )


@router.get("/{game_id}/votes", response_model=Dict[str, Any])
async def get_game_votes(
    game_id: str,
    round_number: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    game_engine: GameEngine = Depends(get_game_engine)
):
    """
    获取游戏投票记录

    - **game_id**: 游戏ID
    - **round_number**: 轮次（可选）
    """
    try:
        votes = await game_engine.get_votes(game_id, round_number)

        return {
            "success": True,
            "votes": [
                {
                    "id": v.id,
                    "voter_id": v.voter.player_id if v.voter else None,
                    "voter_name": v.voter.username if v.voter else None,
                    "target_id": v.target.player_id if v.target else None,
                    "target_name": v.target.username if v.target else None,
                    "round_number": v.round_number,
                    "created_at": v.created_at.isoformat() if v.created_at else None
                }
                for v in votes
            ]
        }

    except Exception as e:
        logger.error(f"Failed to get votes for game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取投票记录失败: {str(e)}"
        )


@router.post("/{game_id}/trigger-ai", response_model=Dict[str, Any])
async def trigger_ai_turn(
    game_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    game_engine: GameEngine = Depends(get_game_engine)
):
    """
    手动触发 AI 玩家发言

    当游戏恢复或卡住时，可调用此接口触发 AI 发言
    - **game_id**: 游戏ID
    """
    try:
        logger.info(f"[TRIGGER_AI] Manual trigger for game {game_id} by user {current_user.id}")

        # 获取游戏状态
        game_state = await game_engine._get_game_state(game_id)
        if not game_state:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="游戏不存在"
            )

        # 检查当前是否需要 AI 发言
        if game_state.current_phase == GamePhase.SPEAKING and game_state.current_speaker:
            current_player = next(
                (p for p in game_state.players if p.id == game_state.current_speaker),
                None
            )

            if current_player and current_player.is_ai:
                # 直接执行 AI 发言（不使用后台任务，确保立即执行）
                logger.info(f"[TRIGGER_AI] Processing AI turn for {current_player.username}")
                try:
                    result = await game_engine.process_ai_turns(game_id)
                    logger.info(f"[TRIGGER_AI] process_ai_turns result: {result}")
                except Exception as proc_error:
                    logger.error(f"[TRIGGER_AI] process_ai_turns exception: {proc_error}", exc_info=True)
                    return {
                        "success": False,
                        "message": f"AI 发言处理异常: {str(proc_error)}",
                        "triggered": False
                    }

                if result:
                    # 重新获取更新后的游戏状态
                    updated_state = await game_engine._get_game_state(game_id)

                    # 广播 AI 发言消息
                    await connection_manager.broadcast_to_room(game_state.room_id, {
                        "type": "ai_speech_completed",
                        "data": {
                            "game_id": game_id,
                            "player_id": current_player.id,
                            "player_name": current_player.username,
                            "current_phase": updated_state.current_phase.value if updated_state else game_state.current_phase.value,
                            "next_speaker": updated_state.current_speaker if updated_state else None
                        }
                    })

                    return {
                        "success": True,
                        "message": f"AI 玩家 {current_player.username} 已发言",
                        "triggered": True
                    }
                else:
                    # 获取更多诊断信息
                    from app.services.llm import llm_service
                    llm_status = await llm_service.health_check()
                    logger.warning(f"[TRIGGER_AI] AI speech failed. LLM status: {llm_status}")
                    return {
                        "success": False,
                        "message": f"AI 发言处理失败 (LLM可用: {llm_status.get('is_available', False)})",
                        "triggered": False,
                        "debug": {
                            "llm_available": llm_status.get('is_available', False),
                            "last_error": llm_status.get('last_error')
                        }
                    }
            else:
                return {
                    "success": False,
                    "message": "当前发言者不是 AI 玩家",
                    "triggered": False
                }

        elif game_state.current_phase == GamePhase.VOTING:
            # 处理 AI 投票
            asyncio.create_task(process_ai_votes(game_id))
            return {
                "success": True,
                "message": "已触发 AI 投票",
                "triggered": True
            }

        else:
            return {
                "success": False,
                "message": f"当前阶段 ({game_state.current_phase.value}) 不需要 AI 操作",
                "triggered": False
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TRIGGER_AI] Failed to trigger AI turn for game {game_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"触发 AI 发言失败: {str(e)}"
        )


@router.post("/{game_id}/force-end", response_model=Dict[str, Any])
async def force_end_game(
    game_id: str,
    reason: str = "游戏被强制结束",
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    game_engine: GameEngine = Depends(get_game_engine),
    db: AsyncSession = Depends(get_db)
):
    """
    强制结束游戏（管理员功能）
    
    - **game_id**: 游戏ID
    - **reason**: 结束原因
    """
    try:
        game_state = await game_engine.force_end_game(game_id, reason)
        
        # 广播游戏强制结束消息
        await connection_manager.broadcast_to_room(game_state.room_id, {
            "type": "game_force_ended",
            "data": {
                "game_id": game_id,
                "reason": reason,
                "ended_by": current_user.id
            }
        })
        
        logger.info(f"Game {game_id} force ended by {current_user.id}: {reason}")
        
        return {
            "success": True,
            "message": "游戏已强制结束",
            "reason": reason
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to force end game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"强制结束游戏失败: {str(e)}"
        )


# 后台任务函数
async def process_ai_turn(game_id: str, initial_delay: float = 0):
    """处理AI玩家回合 - 使用独立的数据库会话"""
    logger.info(f"[AI_TURN] Starting process_ai_turn for game {game_id}")
    try:
        # 等待弹窗消失后再开始 AI 发言
        if initial_delay > 0:
            logger.info(f"[AI_TURN] Waiting {initial_delay}s before AI speech...")
            await asyncio.sleep(initial_delay)

        from app.core.database import db_manager

        logger.info("[AI_TURN] Getting database session...")
        async with db_manager.get_session() as session:
            logger.info("[AI_TURN] Creating GameEngine...")
            game_engine = GameEngine(session)
            logger.info("[AI_TURN] Calling process_ai_turns...")
            result = await game_engine.process_ai_turns(game_id)
            logger.info(f"[AI_TURN] process_ai_turns completed with result: {result}")

    except Exception as e:
        logger.error(f"[AI_TURN] Failed to process AI turn for game {game_id}: {e}", exc_info=True)


async def process_ai_votes(game_id: str):
    """处理AI玩家投票 - 轮流投票机制，每次只处理当前投票者"""
    logger.info(f"[AI_VOTES] Starting AI vote processing for game {game_id}")
    try:
        from app.core.database import db_manager

        async with db_manager.get_session() as session:
            game_engine = GameEngine(session)
            game_state = await game_engine._get_game_state(game_id)

            if not game_state:
                logger.warning(f"[AI_VOTES] Game state not found for {game_id}")
                return

            if game_state.current_phase != GamePhase.VOTING:
                logger.info(f"[AI_VOTES] Game {game_id} not in voting phase, current: {game_state.current_phase}")
                return

            # 检查当前投票者是否是 AI
            if not game_state.current_voter:
                logger.info(f"[AI_VOTES] No current voter for game {game_id}")
                return

            current_voter = next(
                (p for p in game_state.alive_players if p.id == game_state.current_voter),
                None
            )

            if not current_voter:
                logger.warning(f"[AI_VOTES] Current voter not found in alive players")
                return

            if not current_voter.is_ai:
                logger.info(f"[AI_VOTES] Current voter {current_voter.username} is not AI, waiting for human vote")
                return

            # 处理当前 AI 玩家的投票
            logger.info(f"[AI_VOTES] Processing vote for AI player {current_voter.username}")
            available_targets = [p.id for p in game_state.alive_players if p.id != current_voter.id]
            vote_target = await game_engine.handle_ai_vote(game_id, current_voter.id, available_targets)

            if vote_target:
                logger.info(f"[AI_VOTES] AI player {current_voter.username} voted for {vote_target}")
                # 广播 AI 投票
                await connection_manager.broadcast_to_room(game_state.room_id, {
                    "type": "vote_submitted",
                    "data": {
                        "game_id": game_id,
                        "voter_id": current_voter.id,
                        "voter_name": current_voter.username,
                        "target_id": vote_target,
                        "round_number": game_state.round_number,
                        "is_ai": True
                    }
                })

                # 重新获取游戏状态，检查下一步动作
                updated_state = await game_engine._get_game_state(game_id)
                if updated_state:
                    if updated_state.current_phase == GamePhase.VOTING and updated_state.current_voter:
                        # 还在投票阶段，检查下一个投票者是否也是 AI
                        next_voter = next(
                            (p for p in updated_state.alive_players if p.id == updated_state.current_voter),
                            None
                        )
                        if next_voter and next_voter.is_ai:
                            # 继续处理下一个 AI 投票
                            logger.info(f"[AI_VOTES] Next voter {next_voter.username} is also AI, continuing...")
                            asyncio.create_task(process_ai_votes(game_id))
                    elif updated_state.current_phase == GamePhase.SPEAKING and updated_state.current_speaker:
                        # 新一轮开始了，检查第一个发言者是否是 AI
                        first_speaker = next(
                            (p for p in updated_state.players if p.id == updated_state.current_speaker),
                            None
                        )
                        if first_speaker and first_speaker.is_ai:
                            logger.info(f"[AI_VOTES] New round started, first speaker {first_speaker.username} is AI, triggering AI turn...")
                            asyncio.create_task(process_ai_turn(game_id, initial_delay=2.0))

            logger.info(f"[AI_VOTES] Completed AI vote for game {game_id}")

    except Exception as e:
        logger.error(f"[AI_VOTES] Failed to process AI vote for game {game_id}: {e}", exc_info=True)


async def process_settlement(game_id: str):
    """处理游戏结算 - 使用独立的数据库会话"""
    try:
        from app.core.database import db_manager

        async with db_manager.get_session() as session:
            settlement_service = get_settlement_service(session)
            await settlement_service.apply_settlement(game_id)
            logger.info(f"Settlement completed for game {game_id}")
    except Exception as e:
        logger.error(f"Failed to process settlement for game {game_id}: {e}")


async def broadcast_game_end(game_engine: GameEngine, game_state: GameState):
    """广播游戏结束消息"""
    try:
        result = await game_engine.get_game_result(game_state.id)
        
        await connection_manager.broadcast_to_room(game_state.room_id, {
            "type": "game_ended",
            "data": {
                "game_id": game_state.id,
                "winner_role": game_state.winner_role.value if game_state.winner_role else None,
                "winner_players": game_state.winner_players or [],
                "result": result
            }
        })
    except Exception as e:
        logger.error(f"Failed to broadcast game end for {game_state.id}: {e}")
