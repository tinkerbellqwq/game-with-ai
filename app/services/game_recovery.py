"""
Game state recovery service
游戏状态恢复服务 - 实现游戏状态的持久化和恢复机制
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import redis_manager
from app.core.database import db_manager
from app.models.game import Game, Speech, Vote
from app.schemas.game import GameState, GamePhase

logger = logging.getLogger(__name__)


class GameRecoveryService:
    """游戏状态恢复服务"""

    def __init__(self):
        self.recovery_key_prefix = "game:recovery:"
        self.recovery_ttl = 86400  # 24小时

    async def save_game_state(self, game_state: GameState) -> bool:
        """
        保存游戏状态到Redis和数据库

        Args:
            game_state: 游戏状态对象

        Returns:
            bool: 保存是否成功
        """
        try:
            # 序列化游戏状态
            state_data = game_state.model_dump(mode='json')
            state_json = json.dumps(state_data, default=str)

            # 保存到Redis
            redis_client = await redis_manager.get_client()
            recovery_key = f"{self.recovery_key_prefix}{game_state.id}"
            await redis_client.setex(
                recovery_key,
                self.recovery_ttl,
                state_json
            )

            # 同时更新数据库中的游戏记录
            async with db_manager.get_session() as db:
                stmt = select(Game).where(Game.id == game_state.id)
                result = await db.execute(stmt)
                game = result.scalar_one_or_none()

                if game:
                    game.current_phase = game_state.current_phase
                    game.round_number = game_state.round_number
                    game.current_speaker = game_state.current_speaker
                    game.players = [p.model_dump() for p in game_state.players]
                    game.eliminated_players = game_state.eliminated_players or []
                    game.updated_at = datetime.utcnow()
                    await db.commit()

            logger.info(f"Game state saved for recovery: {game_state.id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save game state for recovery: {e}")
            return False

    async def recover_game_state(self, game_id: str) -> Optional[GameState]:
        """
        从Redis或数据库恢复游戏状态

        Args:
            game_id: 游戏ID

        Returns:
            GameState: 恢复的游戏状态，如果失败则返回None
        """
        try:
            # 首先尝试从Redis恢复
            redis_client = await redis_manager.get_client()
            recovery_key = f"{self.recovery_key_prefix}{game_id}"
            state_json = await redis_client.get(recovery_key)

            if state_json:
                state_data = json.loads(state_json)
                game_state = GameState(**state_data)
                logger.info(f"Game state recovered from Redis: {game_id}")
                return game_state

            # 如果Redis中没有，尝试从数据库恢复
            async with db_manager.get_session() as db:
                stmt = select(Game).where(Game.id == game_id)
                result = await db.execute(stmt)
                game = result.scalar_one_or_none()

                if game and game.current_phase != GamePhase.FINISHED:
                    # 从数据库记录重建游戏状态
                    game_state = await self._rebuild_game_state_from_db(game, db)

                    # 恢复后重新缓存到Redis
                    if game_state:
                        await self.save_game_state(game_state)
                        logger.info(f"Game state recovered from database: {game_id}")
                        return game_state

            logger.warning(f"No recoverable game state found for: {game_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to recover game state: {e}")
            return None

    async def _rebuild_game_state_from_db(self, game: Game, db: AsyncSession) -> Optional[GameState]:
        """
        从数据库记录重建游戏状态

        Args:
            game: 游戏数据库记录
            db: 数据库会话

        Returns:
            GameState: 重建的游戏状态
        """
        try:
            from app.schemas.game import GamePlayer

            # 重建玩家列表
            players = [GamePlayer(**p) for p in game.players] if game.players else []

            # 获取发言记录
            stmt = select(Speech).where(Speech.game_id == game.id)
            result = await db.execute(stmt)
            speeches = result.scalars().all()

            speech_list = [
                {
                    "player_id": s.participant_id,
                    "content": s.content,
                    "round_number": s.round_number,
                    "created_at": s.created_at.isoformat()
                }
                for s in speeches
            ]

            # 获取投票记录
            stmt = select(Vote).where(
                and_(
                    Vote.game_id == game.id,
                    Vote.round_number == game.round_number
                )
            )
            result = await db.execute(stmt)
            votes = result.scalars().all()
            vote_dict = {v.voter_id: v.target_id for v in votes}

            # 构建游戏状态
            game_state = GameState(
                id=game.id,
                room_id=game.room_id,
                word_pair_id=game.word_pair_id,
                current_phase=game.current_phase,
                round_number=game.round_number,
                current_speaker=game.current_speaker,
                players=players,
                speeches=speech_list,
                votes=vote_dict,
                eliminated_players=game.eliminated_players or [],
                started_at=game.started_at,
                finished_at=game.finished_at
            )

            return game_state

        except Exception as e:
            logger.error(f"Failed to rebuild game state from database: {e}")
            return None

    async def recover_active_games(self) -> List[GameState]:
        """
        恢复所有活跃的游戏状态（系统重启时使用）

        Returns:
            List[GameState]: 恢复的游戏状态列表
        """
        recovered_games = []

        try:
            async with db_manager.get_session() as db:
                # 查找所有未完成的游戏
                stmt = select(Game).where(
                    and_(
                        Game.current_phase != GamePhase.FINISHED,
                        Game.started_at.isnot(None),
                        # 只恢复最近24小时内的游戏
                        Game.started_at > datetime.utcnow() - timedelta(hours=24)
                    )
                )
                result = await db.execute(stmt)
                active_games = result.scalars().all()

                logger.info(f"Found {len(active_games)} active games to recover")

                for game in active_games:
                    try:
                        game_state = await self._rebuild_game_state_from_db(game, db)
                        if game_state:
                            # 保存到Redis
                            await self.save_game_state(game_state)
                            recovered_games.append(game_state)
                            logger.info(f"Recovered game: {game.id}")
                    except Exception as e:
                        logger.error(f"Failed to recover game {game.id}: {e}")

                logger.info(f"Successfully recovered {len(recovered_games)} games")

        except Exception as e:
            logger.error(f"Failed to recover active games: {e}")

        return recovered_games

    async def cleanup_old_recovery_data(self, days: int = 7) -> int:
        """
        清理旧的恢复数据

        Args:
            days: 保留天数

        Returns:
            int: 清理的记录数
        """
        cleaned_count = 0

        try:
            # 清理Redis中的旧数据
            redis_client = await redis_manager.get_client()
            pattern = f"{self.recovery_key_prefix}*"

            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100
                )

                for key in keys:
                    # Redis的TTL会自动清理，这里只是记录
                    ttl = await redis_client.ttl(key)
                    if ttl < 0:  # 已过期但未清理
                        await redis_client.delete(key)
                        cleaned_count += 1

                if cursor == 0:
                    break

            logger.info(f"Cleaned {cleaned_count} old recovery records from Redis")

        except Exception as e:
            logger.error(f"Failed to cleanup old recovery data: {e}")

        return cleaned_count

    async def get_recovery_status(self) -> Dict[str, Any]:
        """
        获取恢复系统状态

        Returns:
            Dict: 恢复系统状态信息
        """
        try:
            redis_client = await redis_manager.get_client()
            pattern = f"{self.recovery_key_prefix}*"

            # 统计Redis中的恢复记录
            cursor = 0
            redis_count = 0
            while True:
                cursor, keys = await redis_client.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100
                )
                redis_count += len(keys)

                if cursor == 0:
                    break

            # 统计数据库中的活跃游戏
            async with db_manager.get_session() as db:
                from sqlalchemy import func
                stmt = select(func.count()).select_from(Game).where(
                    Game.current_phase != GamePhase.FINISHED
                )
                result = await db.execute(stmt)
                active_count = result.scalar() or 0

            return {
                "status": "operational",
                "redis_cached_games": redis_count,
                "database_active_games": active_count,
                "recovery_ttl_seconds": self.recovery_ttl,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to get recovery status: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# Global recovery service instance
game_recovery_service = GameRecoveryService()


# Convenience functions
async def save_game_state(game_state: GameState) -> bool:
    """保存游戏状态"""
    return await game_recovery_service.save_game_state(game_state)


async def recover_game_state(game_id: str) -> Optional[GameState]:
    """恢复游戏状态"""
    return await game_recovery_service.recover_game_state(game_id)


async def recover_all_active_games() -> List[GameState]:
    """恢复所有活跃游戏"""
    return await game_recovery_service.recover_active_games()


async def get_recovery_status() -> Dict[str, Any]:
    """获取恢复系统状态"""
    return await game_recovery_service.get_recovery_status()
