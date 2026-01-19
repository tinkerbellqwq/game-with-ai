"""
Leaderboard service
排行榜服务 - 处理排行榜查询、排序和缓存
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, asc, text
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.user import User
from app.models.ai_player import AIPlayer
from app.models.game import Game
from app.schemas.leaderboard import (
    LeaderboardEntry, LeaderboardResponse, UserRankInfo,
    PersonalStats, LeaderboardQuery
)

logger = logging.getLogger(__name__)


class LeaderboardService:
    """排行榜服务类"""
    
    # Cache keys
    LEADERBOARD_CACHE_KEY = "leaderboard:global"
    USER_RANK_CACHE_KEY = "user_rank:{user_id}"
    LEADERBOARD_CACHE_TTL = 300  # 5 minutes
    USER_RANK_CACHE_TTL = 600   # 10 minutes
    
    def __init__(self):
        self.redis = None
    
    async def _get_redis(self):
        """获取Redis连接"""
        if not self.redis:
            self.redis = await get_redis()
        return self.redis
    
    async def get_leaderboard(
        self,
        query: LeaderboardQuery,
        db: AsyncSession
    ) -> LeaderboardResponse:
        """
        获取排行榜数据（包含真人和AI玩家）

        Args:
            query: 查询参数
            db: 数据库会话

        Returns:
            LeaderboardResponse: 排行榜响应数据
        """
        try:
            # 尝试从缓存获取
            cache_key = f"{self.LEADERBOARD_CACHE_KEY}:{query.page}:{query.page_size}:{query.sort_by}:{query.order}"
            redis = await self._get_redis()

            if redis:
                cached_data = await redis.get(cache_key)
                if cached_data:
                    logger.info(f"Leaderboard cache hit for key: {cache_key}")
                    data = json.loads(cached_data)
                    return LeaderboardResponse(**data)

            # 获取真人用户数据
            users_query = select(User).where(User.is_active == True)
            users_result = await db.execute(users_query)
            users = users_result.scalars().all()

            # 获取AI玩家数据
            ai_query = select(AIPlayer).where(AIPlayer.is_active == True)
            ai_result = await db.execute(ai_query)
            ai_players = ai_result.scalars().all()

            # 合并所有玩家到统一列表
            all_entries = []

            for user in users:
                win_rate = (user.games_won / user.games_played * 100) if user.games_played > 0 else 0.0
                all_entries.append({
                    "user_id": user.id,
                    "username": user.username,
                    "score": user.score,
                    "games_played": user.games_played,
                    "games_won": user.games_won,
                    "win_rate": round(win_rate, 2),
                    "last_game_at": user.last_game_at if hasattr(user, 'last_game_at') else None,
                    "is_ai": False
                })

            for ai in ai_players:
                # AI 没有 score 字段，根据胜率计算虚拟分数
                win_rate = (ai.games_won / ai.games_played * 100) if ai.games_played > 0 else 0.0
                # 为 AI 计算虚拟分数：基础分 + 胜场奖励
                ai_score = ai.games_won * 10 - (ai.games_played - ai.games_won) * 5
                if ai_score < 0:
                    ai_score = 0
                all_entries.append({
                    "user_id": ai.id,
                    "username": f"{ai.name} 🤖",
                    "score": ai_score,
                    "games_played": ai.games_played,
                    "games_won": ai.games_won,
                    "win_rate": round(win_rate, 2),
                    "last_game_at": ai.updated_at,
                    "is_ai": True
                })

            # 根据查询参数排序
            sort_key = query.sort_by if query.sort_by in ["score", "games_played", "games_won", "win_rate"] else "score"
            reverse = query.order.lower() == "desc"
            all_entries.sort(key=lambda x: (x.get(sort_key, 0) or 0), reverse=reverse)

            # 分页
            total_count = len(all_entries)
            offset = (query.page - 1) * query.page_size
            total_pages = (total_count + query.page_size - 1) // query.page_size if total_count > 0 else 1
            page_entries = all_entries[offset:offset + query.page_size]

            # 构建排行榜条目
            entries = []
            for i, entry_data in enumerate(page_entries):
                rank = offset + i + 1
                entry = LeaderboardEntry(
                    rank=rank,
                    user_id=entry_data["user_id"],
                    username=entry_data["username"],
                    score=entry_data["score"],
                    games_played=entry_data["games_played"],
                    games_won=entry_data["games_won"],
                    win_rate=entry_data["win_rate"],
                    last_game_at=entry_data["last_game_at"],
                    is_ai=entry_data["is_ai"]
                )
                entries.append(entry)

            # 构建响应
            response = LeaderboardResponse(
                entries=entries,
                total_count=total_count,
                page=query.page,
                page_size=query.page_size,
                total_pages=total_pages,
                has_next=query.page < total_pages,
                has_prev=query.page > 1
            )

            # 缓存结果
            if redis:
                await redis.setex(
                    cache_key,
                    self.LEADERBOARD_CACHE_TTL,
                    json.dumps(response.dict(), default=str)
                )
                logger.info(f"Cached leaderboard data for key: {cache_key}")

            return response

        except Exception as e:
            logger.error(f"Error getting leaderboard: {str(e)}")
            raise
    
    async def get_user_rank(self, user_id: str, db: AsyncSession) -> Optional[UserRankInfo]:
        """
        获取用户排名信息
        
        Args:
            user_id: 用户ID
            db: 数据库会话
            
        Returns:
            UserRankInfo: 用户排名信息
        """
        try:
            # 尝试从缓存获取
            cache_key = self.USER_RANK_CACHE_KEY.format(user_id=user_id)
            redis = await self._get_redis()
            
            if redis:
                cached_data = await redis.get(cache_key)
                if cached_data:
                    logger.info(f"User rank cache hit for user: {user_id}")
                    data = json.loads(cached_data)
                    return UserRankInfo(**data)
            
            # 获取用户信息
            user_query = select(User).where(User.id == user_id, User.is_active == True)
            result = await db.execute(user_query)
            user = result.scalar_one_or_none()
            
            if not user:
                return None
            
            # 计算用户排名
            rank_query = select(func.count(User.id)).where(
                User.is_active == True,
                User.score > user.score
            )
            rank_result = await db.execute(rank_query)
            current_rank = rank_result.scalar() + 1
            
            # 计算胜率
            win_rate = (user.games_won / user.games_played * 100) if user.games_played > 0 else 0.0
            
            # 构建用户排名信息
            user_rank_info = UserRankInfo(
                user_id=user.id,
                username=user.username,
                current_rank=current_rank,
                score=user.score,
                games_played=user.games_played,
                games_won=user.games_won,
                win_rate=round(win_rate, 2),
                rank_change=None  # TODO: 实现排名变化追踪
            )
            
            # 缓存结果
            if redis:
                await redis.setex(
                    cache_key,
                    self.USER_RANK_CACHE_TTL,
                    json.dumps(user_rank_info.dict())
                )
                logger.info(f"Cached user rank for user: {user_id}")
            
            return user_rank_info
            
        except Exception as e:
            logger.error(f"Error getting user rank for {user_id}: {str(e)}")
            raise
    
    async def get_personal_stats(self, user_id: str, db: AsyncSession) -> Optional[PersonalStats]:
        """
        获取个人详细统计信息
        
        Args:
            user_id: 用户ID
            db: 数据库会话
            
        Returns:
            PersonalStats: 个人统计信息
        """
        try:
            # 获取用户基本信息
            user_query = select(User).where(User.id == user_id, User.is_active == True)
            result = await db.execute(user_query)
            user = result.scalar_one_or_none()
            
            if not user:
                return None
            
            # 获取当前排名
            rank_query = select(func.count(User.id)).where(
                User.is_active == True,
                User.score > user.score
            )
            rank_result = await db.execute(rank_query)
            current_rank = rank_result.scalar() + 1
            
            # 获取游戏统计
            games_query = (
                select(Game)
                .where(Game.players.contains(user.id))
                .order_by(desc(Game.started_at))
            )
            games_result = await db.execute(games_query)
            user_games = games_result.scalars().all()

            # 计算统计数据
            games_lost = user.games_played - user.games_won
            win_rate = (user.games_won / user.games_played * 100) if user.games_played > 0 else 0.0

            # 计算平均每局积分 (简化计算)
            average_score_per_game = user.score / user.games_played if user.games_played > 0 else 0.0

            # 获取最后游戏时间
            last_game_at = user_games[0].started_at if user_games else None
            
            # TODO: 实现更复杂的统计计算
            # - 历史最佳排名
            # - 累计获得积分
            # - 连胜统计
            
            personal_stats = PersonalStats(
                user_id=user.id,
                username=user.username,
                current_rank=current_rank,
                score=user.score,
                games_played=user.games_played,
                games_won=user.games_won,
                games_lost=games_lost,
                win_rate=round(win_rate, 2),
                best_rank=None,  # TODO: 实现历史排名追踪
                total_score_earned=user.score,  # 简化实现
                average_score_per_game=round(average_score_per_game, 2),
                consecutive_wins=0,  # TODO: 实现连胜统计
                max_consecutive_wins=0,  # TODO: 实现最大连胜记录
                created_at=user.created_at,
                last_game_at=last_game_at
            )
            
            return personal_stats
            
        except Exception as e:
            logger.error(f"Error getting personal stats for {user_id}: {str(e)}")
            raise
    
    async def invalidate_leaderboard_cache(self):
        """
        清除排行榜缓存
        """
        try:
            redis = await self._get_redis()
            if redis:
                # 清除所有排行榜相关缓存
                pattern = f"{self.LEADERBOARD_CACHE_KEY}:*"
                keys = await redis.keys(pattern)
                if keys:
                    await redis.delete(*keys)
                    logger.info(f"Invalidated {len(keys)} leaderboard cache entries")
        except Exception as e:
            logger.error(f"Error invalidating leaderboard cache: {str(e)}")
    
    async def invalidate_user_rank_cache(self, user_id: str):
        """
        清除用户排名缓存
        
        Args:
            user_id: 用户ID
        """
        try:
            redis = await self._get_redis()
            if redis:
                cache_key = self.USER_RANK_CACHE_KEY.format(user_id=user_id)
                await redis.delete(cache_key)
                logger.info(f"Invalidated user rank cache for user: {user_id}")
        except Exception as e:
            logger.error(f"Error invalidating user rank cache for {user_id}: {str(e)}")
    
    async def update_user_rank_after_game(self, user_id: str, db: AsyncSession):
        """
        游戏结束后更新用户排名缓存
        
        Args:
            user_id: 用户ID
            db: 数据库会话
        """
        try:
            # 清除用户排名缓存
            await self.invalidate_user_rank_cache(user_id)
            
            # 清除排行榜缓存
            await self.invalidate_leaderboard_cache()
            
            # 预热用户排名缓存
            await self.get_user_rank(user_id, db)
            
            logger.info(f"Updated rank cache for user: {user_id}")
            
        except Exception as e:
            logger.error(f"Error updating user rank cache for {user_id}: {str(e)}")


# 全局服务实例
leaderboard_service = LeaderboardService()