"""
Game Flow Orchestrator
游戏流程编排器 - 集成用户系统、游戏逻辑、AI系统和结算系统
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.room import Room, RoomStatus
from app.models.ai_player import AIPlayer
from app.schemas.game import GameCreate, GameState, GamePhase, PlayerRole
from app.services.game import GameEngine, GameStateManager
from app.services.room import RoomService
from app.services.settlement import get_settlement_service
from app.services.ai_player import get_ai_player_service
from app.services.leaderboard import leaderboard_service
from app.services.leaderboard_realtime import leaderboard_realtime_service
from app.websocket.connection_manager import connection_manager
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


class GameFlowOrchestrator:
    """
    游戏流程编排器
    
    负责协调以下系统的交互:
    - 用户认证系统
    - 房间管理系统
    - 游戏核心逻辑
    - AI对手系统
    - 积分结算系统
    - 排行榜系统
    - WebSocket实时通信
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.game_engine = GameEngine(db)
        self.game_state_manager = GameStateManager(db)
        self.room_service = RoomService(db)
        self.settlement_service = get_settlement_service(db)
        self.ai_player_service = get_ai_player_service(db)
        self.redis = None
    
    async def _get_redis(self):
        """获取Redis客户端"""
        if self.redis is None:
            self.redis = await get_redis()
        return self.redis
    
    async def create_and_start_game(
        self,
        room_id: str,
        creator_id: str,
        game_settings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        创建并启动游戏的完整流程
        
        流程:
        1. 验证房间和用户权限
        2. 获取房间内玩家
        3. 创建AI玩家（如需要）
        4. 创建游戏实例
        5. 分配角色和词汇
        6. 广播游戏开始
        7. 启动游戏循环
        """
        try:
            # 1. 验证房间
            room = await self._validate_room(room_id, creator_id)
            
            # 2. 获取玩家
            players, ai_players = await self._get_game_players(room)
            
            # 3. 创建游戏
            game_create = GameCreate(
                room_id=room_id,
                difficulty=game_settings.get('difficulty') if game_settings else None,
                category=game_settings.get('category') if game_settings else None
            )
            
            game_state = await self.game_engine.create_game(
                game_create, players, ai_players
            )
            
            # 4. 更新房间状态
            await self._update_room_status(room_id, RoomStatus.PLAYING)
            
            # 5. 广播游戏创建
            await self._broadcast_game_created(game_state)
            
            # 6. 记录游戏开始
            await self._log_game_start(game_state)
            
            logger.info(f"Game created and ready: {game_state.id}")
            
            return {
                "success": True,
                "game_id": game_state.id,
                "player_count": len(game_state.players),
                "phase": game_state.current_phase.value
            }
            
        except Exception as e:
            logger.error(f"Failed to create and start game: {e}")
            raise
    
    async def start_game_loop(self, game_id: str) -> Dict[str, Any]:
        """
        启动游戏主循环
        
        流程:
        1. 设置所有玩家准备就绪
        2. 开始游戏
        3. 处理AI玩家回合
        """
        try:
            # 获取游戏状态
            game_state = await self.game_engine._get_game_state(game_id)
            if not game_state:
                raise ValueError("游戏不存在")
            
            # 设置所有玩家准备就绪
            for player in game_state.players:
                player.is_ready = True
            await self.game_engine._update_game_in_db(game_state)
            
            # 开始游戏
            game_state = await self.game_engine.start_game(game_id)
            
            # 广播游戏开始
            await self._broadcast_game_started(game_state)
            
            # 如果第一个发言者是AI，处理AI发言
            await self._process_ai_turn_if_needed(game_state)
            
            return {
                "success": True,
                "game_id": game_id,
                "phase": game_state.current_phase.value,
                "current_speaker": game_state.current_speaker
            }
            
        except Exception as e:
            logger.error(f"Failed to start game loop: {e}")
            raise
    
    async def process_game_turn(
        self,
        game_id: str,
        player_id: str,
        action_type: str,
        action_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        处理游戏回合
        
        支持的动作类型:
        - speech: 发言
        - skip_speech: 跳过发言
        - vote: 投票
        """
        try:
            game_state = await self.game_engine._get_game_state(game_id)
            if not game_state:
                raise ValueError("游戏不存在")
            
            result = {}
            
            if action_type == "speech":
                from app.schemas.game import SpeechCreate
                speech_create = SpeechCreate(content=action_data.get("content", ""))
                game_state = await self.game_engine.handle_speech(
                    game_id, player_id, speech_create
                )
                result["action"] = "speech_submitted"
                
            elif action_type == "skip_speech":
                game_state = await self.game_engine.skip_speech(game_id, player_id)
                result["action"] = "speech_skipped"
                
            elif action_type == "vote":
                from app.schemas.game import VoteCreate
                vote_create = VoteCreate(target_id=action_data.get("target_id"))
                game_state = await self.game_engine.handle_vote(
                    game_id, player_id, vote_create
                )
                result["action"] = "vote_submitted"
            
            else:
                raise ValueError(f"不支持的动作类型: {action_type}")
            
            # 广播动作结果
            await self._broadcast_game_action(game_state, action_type, player_id, action_data)
            
            # 检查游戏状态变化
            if game_state.current_phase == GamePhase.FINISHED:
                # 游戏结束，处理结算
                await self._handle_game_end(game_state)
                result["game_ended"] = True
            else:
                # 处理AI回合
                await self._process_ai_turn_if_needed(game_state)
                result["game_ended"] = False
            
            result["success"] = True
            result["phase"] = game_state.current_phase.value
            result["round_number"] = game_state.round_number
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to process game turn: {e}")
            raise
    
    async def _validate_room(self, room_id: str, creator_id: str) -> Room:
        """验证房间和用户权限"""
        room = await self.room_service.get_room(room_id)
        if not room:
            raise ValueError("房间不存在")
        
        if room.creator_id != creator_id:
            raise ValueError("只有房主可以开始游戏")
        
        if room.status != RoomStatus.WAITING:
            raise ValueError("房间状态不允许开始游戏")
        
        return room
    
    async def _get_game_players(self, room: Room) -> tuple:
        """获取游戏玩家（真人和AI）"""
        from sqlalchemy import select
        
        # 获取真人玩家
        stmt = select(User).filter(User.id.in_(room.current_players))
        result = await self.db.execute(stmt)
        players = list(result.scalars().all())
        
        # 创建AI玩家
        ai_players = []
        if room.ai_count > 0:
            ai_players = await self.ai_player_service.create_ai_players_for_room(
                room_id=room.id,
                count=room.ai_count
            )
        
        # 验证玩家数量
        total_players = len(players) + len(ai_players)
        if total_players < 3:
            raise ValueError(f"至少需要3名玩家，当前有{total_players}名")
        if total_players > 10:
            raise ValueError(f"最多支持10名玩家，当前有{total_players}名")
        
        return players, ai_players
    
    async def _update_room_status(self, room_id: str, status: RoomStatus):
        """更新房间状态"""
        from sqlalchemy import select
        stmt = select(Room).filter(Room.id == room_id)
        result = await self.db.execute(stmt)
        room = result.scalar_one_or_none()
        
        if room:
            room.status = status
            room.updated_at = datetime.utcnow()
            await self.db.commit()
    
    async def _broadcast_game_created(self, game_state: GameState):
        """广播游戏创建消息"""
        await connection_manager.broadcast_to_room(game_state.room_id, {
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
                ],
                "phase": game_state.current_phase.value
            }
        })
    
    async def _broadcast_game_started(self, game_state: GameState):
        """广播游戏开始消息"""
        await connection_manager.broadcast_to_room(game_state.room_id, {
            "type": "game_started",
            "data": {
                "game_id": game_state.id,
                "phase": game_state.current_phase.value,
                "current_speaker": game_state.current_speaker,
                "round_number": game_state.round_number
            }
        })
    
    async def _broadcast_game_action(
        self,
        game_state: GameState,
        action_type: str,
        player_id: str,
        action_data: Dict[str, Any]
    ):
        """广播游戏动作"""
        await connection_manager.broadcast_to_room(game_state.room_id, {
            "type": f"game_{action_type}",
            "data": {
                "game_id": game_state.id,
                "player_id": player_id,
                "action_data": action_data,
                "phase": game_state.current_phase.value,
                "current_speaker": game_state.current_speaker,
                "round_number": game_state.round_number
            }
        })
    
    async def _process_ai_turn_if_needed(self, game_state: GameState):
        """如果需要，处理AI玩家回合"""
        if game_state.current_phase == GamePhase.SPEAKING:
            if game_state.current_speaker:
                current_player = next(
                    (p for p in game_state.players if p.id == game_state.current_speaker),
                    None
                )
                if current_player and current_player.is_ai:
                    # 异步处理AI发言
                    asyncio.create_task(
                        self._process_ai_speech(game_state.id, current_player.id)
                    )
        
        elif game_state.current_phase == GamePhase.VOTING:
            # 处理所有AI玩家的投票
            asyncio.create_task(
                self._process_ai_votes(game_state)
            )
    
    async def _process_ai_speech(self, game_id: str, ai_player_id: str):
        """处理AI玩家发言"""
        try:
            # 添加短暂延迟模拟思考时间
            await asyncio.sleep(2)
            
            speech = await self.game_engine.handle_ai_speech(game_id, ai_player_id)
            
            if speech:
                # 获取更新后的游戏状态
                game_state = await self.game_engine._get_game_state(game_id)
                if game_state:
                    # 广播AI发言
                    await connection_manager.broadcast_to_room(game_state.room_id, {
                        "type": "ai_speech",
                        "data": {
                            "game_id": game_id,
                            "player_id": ai_player_id,
                            "content": speech,
                            "phase": game_state.current_phase.value,
                            "next_speaker": game_state.current_speaker
                        }
                    })
                    
                    # 继续处理下一个AI回合
                    await self._process_ai_turn_if_needed(game_state)
                    
        except Exception as e:
            logger.error(f"Failed to process AI speech: {e}")
    
    async def _process_ai_votes(self, game_state: GameState):
        """处理所有AI玩家的投票"""
        try:
            # 添加短暂延迟模拟思考时间
            await asyncio.sleep(1)
            
            ai_players = [p for p in game_state.alive_players if p.is_ai]
            available_targets = [p.id for p in game_state.alive_players]
            
            for ai_player in ai_players:
                try:
                    vote_target = await self.game_engine.handle_ai_vote(
                        game_state.id, ai_player.id, available_targets
                    )
                    
                    if vote_target:
                        # 广播AI投票
                        await connection_manager.broadcast_to_room(game_state.room_id, {
                            "type": "ai_vote",
                            "data": {
                                "game_id": game_state.id,
                                "voter_id": ai_player.id,
                                "voter_name": ai_player.username,
                                "target_id": vote_target,
                                "round_number": game_state.round_number,
                                "is_ai": True
                            }
                        })
                        
                except Exception as e:
                    logger.error(f"Failed to process AI vote for {ai_player.id}: {e}")
            
            # 检查游戏状态
            updated_state = await self.game_engine._get_game_state(game_state.id)
            if updated_state and updated_state.current_phase == GamePhase.FINISHED:
                await self._handle_game_end(updated_state)
                
        except Exception as e:
            logger.error(f"Failed to process AI votes: {e}")
    
    async def _handle_game_end(self, game_state: GameState):
        """处理游戏结束"""
        try:
            # 1. 广播游戏结束
            result = await self.game_engine.get_game_result(game_state.id)
            
            await connection_manager.broadcast_to_room(game_state.room_id, {
                "type": "game_ended",
                "data": {
                    "game_id": game_state.id,
                    "winner_role": game_state.winner_role.value if game_state.winner_role else None,
                    "winner_players": game_state.winner_players or [],
                    "result": result
                }
            })
            
            # 2. 处理积分结算
            try:
                settlement_results = await self.settlement_service.apply_settlement(game_state.id)
                
                # 广播结算结果
                await connection_manager.broadcast_to_room(game_state.room_id, {
                    "type": "settlement_complete",
                    "data": {
                        "game_id": game_state.id,
                        "results": settlement_results
                    }
                })
                
            except Exception as e:
                logger.error(f"Settlement failed for game {game_state.id}: {e}")
            
            # 3. 更新排行榜
            try:
                await leaderboard_service.invalidate_leaderboard_cache()
                
                # 通知排行榜更新
                affected_users = [p.id for p in game_state.players if not p.is_ai]
                await leaderboard_realtime_service.notify_leaderboard_update(
                    affected_users, self.db
                )
                
            except Exception as e:
                logger.error(f"Leaderboard update failed: {e}")
            
            # 4. 更新房间状态
            await self._update_room_status(game_state.room_id, RoomStatus.FINISHED)
            
            # 5. 记录游戏结束
            await self._log_game_end(game_state)
            
            logger.info(f"Game {game_state.id} ended successfully")
            
        except Exception as e:
            logger.error(f"Failed to handle game end: {e}")
    
    async def _log_game_start(self, game_state: GameState):
        """记录游戏开始"""
        redis = await self._get_redis()
        await redis.set(
            f"game_start_log:{game_state.id}",
            f"{datetime.utcnow().isoformat()}",
            ex=86400
        )
    
    async def _log_game_end(self, game_state: GameState):
        """记录游戏结束"""
        redis = await self._get_redis()
        await redis.set(
            f"game_end_log:{game_state.id}",
            f"{datetime.utcnow().isoformat()}",
            ex=86400
        )


def get_game_orchestrator(db: AsyncSession) -> GameFlowOrchestrator:
    """获取游戏流程编排器实例"""
    return GameFlowOrchestrator(db)
