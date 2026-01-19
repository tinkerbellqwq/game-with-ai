"""
Leaderboard real-time update service
排行榜实时更新服务
"""

import json
import logging
from typing import List, Dict, Optional, Set
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.services.leaderboard import leaderboard_service
from app.websocket.connection_manager import connection_manager
from app.schemas.leaderboard import UserRankInfo, LeaderboardEntry

logger = logging.getLogger(__name__)


class LeaderboardRealtimeService:
    """排行榜实时更新服务"""
    
    # Redis keys for real-time updates
    RANK_CHANGE_CHANNEL = "leaderboard:rank_changes"
    SCORE_UPDATE_CHANNEL = "leaderboard:score_updates"
    LEADERBOARD_UPDATE_CHANNEL = "leaderboard:updates"
    
    def __init__(self):
        self.redis = None
        self.subscribers = set()  # 订阅排行榜更新的用户
    
    async def _get_redis(self):
        """获取Redis连接"""
        if not self.redis:
            self.redis = await get_redis()
        return self.redis
    
    async def subscribe_to_leaderboard_updates(self, user_id: str):
        """订阅排行榜更新"""
        self.subscribers.add(user_id)
        logger.info(f"User {user_id} subscribed to leaderboard updates")
    
    async def unsubscribe_from_leaderboard_updates(self, user_id: str):
        """取消订阅排行榜更新"""
        self.subscribers.discard(user_id)
        logger.info(f"User {user_id} unsubscribed from leaderboard updates")
    
    async def notify_score_update(
        self, 
        user_id: str, 
        old_score: int, 
        new_score: int,
        old_rank: Optional[int] = None,
        new_rank: Optional[int] = None,
        db: Optional[AsyncSession] = None
    ):
        """通知积分更新"""
        try:
            # 计算排名变化
            if old_rank is None or new_rank is None:
                if db:
                    user_rank_info = await leaderboard_service.get_user_rank(user_id, db)
                    new_rank = user_rank_info.current_rank if user_rank_info else None
            
            rank_change = None
            if old_rank is not None and new_rank is not None:
                rank_change = old_rank - new_rank  # 正数表示排名上升
            
            # 构建更新消息
            update_message = {
                "type": "score_update",
                "user_id": user_id,
                "old_score": old_score,
                "new_score": new_score,
                "score_change": new_score - old_score,
                "old_rank": old_rank,
                "new_rank": new_rank,
                "rank_change": rank_change,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # 发送给用户本人
            await self._send_to_user(user_id, {
                "event": "personal_score_update",
                "data": update_message
            })
            
            # 发布到Redis频道
            redis = await self._get_redis()
            if redis:
                await redis.publish(
                    self.SCORE_UPDATE_CHANNEL,
                    json.dumps(update_message)
                )
            
            logger.info(f"Score update notification sent for user {user_id}: {old_score} -> {new_score}")
            
        except Exception as e:
            logger.error(f"Failed to notify score update for user {user_id}: {e}")
    
    async def notify_rank_change(
        self, 
        user_id: str, 
        old_rank: int, 
        new_rank: int,
        db: AsyncSession
    ):
        """通知排名变化"""
        try:
            # 获取用户详细信息
            user_rank_info = await leaderboard_service.get_user_rank(user_id, db)
            if not user_rank_info:
                return
            
            rank_change = old_rank - new_rank  # 正数表示排名上升
            
            # 构建排名变化消息
            rank_message = {
                "type": "rank_change",
                "user_id": user_id,
                "username": user_rank_info.username,
                "old_rank": old_rank,
                "new_rank": new_rank,
                "rank_change": rank_change,
                "current_score": user_rank_info.score,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # 发送给用户本人
            await self._send_to_user(user_id, {
                "event": "rank_change",
                "data": rank_message
            })
            
            # 如果排名变化显著，通知所有订阅者
            if abs(rank_change) >= 5:  # 排名变化超过5位
                await self._broadcast_to_subscribers({
                    "event": "significant_rank_change",
                    "data": rank_message
                })
            
            # 发布到Redis频道
            redis = await self._get_redis()
            if redis:
                await redis.publish(
                    self.RANK_CHANGE_CHANNEL,
                    json.dumps(rank_message)
                )
            
            logger.info(f"Rank change notification sent for user {user_id}: {old_rank} -> {new_rank}")
            
        except Exception as e:
            logger.error(f"Failed to notify rank change for user {user_id}: {e}")
    
    async def notify_leaderboard_update(
        self, 
        affected_users: List[str],
        db: AsyncSession
    ):
        """通知排行榜更新"""
        try:
            # 获取前10名的最新排行榜
            from app.schemas.leaderboard import LeaderboardQuery
            
            top_query = LeaderboardQuery(page=1, page_size=10, sort_by="score", order="desc")
            top_leaderboard = await leaderboard_service.get_leaderboard(top_query, db)
            
            # 构建排行榜更新消息
            update_message = {
                "type": "leaderboard_update",
                "top_entries": [entry.dict() for entry in top_leaderboard.entries],
                "affected_users": affected_users,
                "timestamp": datetime.utcnow().isoformat(),
                "total_users": top_leaderboard.total_count
            }
            
            # 广播给所有订阅者
            await self._broadcast_to_subscribers({
                "event": "leaderboard_update",
                "data": update_message
            })
            
            # 发布到Redis频道
            redis = await self._get_redis()
            if redis:
                await redis.publish(
                    self.LEADERBOARD_UPDATE_CHANNEL,
                    json.dumps(update_message)
                )
            
            logger.info(f"Leaderboard update notification sent, affected users: {len(affected_users)}")
            
        except Exception as e:
            logger.error(f"Failed to notify leaderboard update: {e}")
    
    async def notify_game_settlement_complete(
        self, 
        game_id: str,
        settlement_results: Dict[str, Dict],
        db: AsyncSession
    ):
        """通知游戏结算完成"""
        try:
            # 提取受影响的用户
            affected_users = list(settlement_results.keys())
            
            # 为每个用户发送个人结算通知
            for user_id, result in settlement_results.items():
                personal_message = {
                    "event": "game_settlement",
                    "data": {
                        "game_id": game_id,
                        "user_id": user_id,
                        "score_change": result["total_score_change"],
                        "new_score": result["final_score"],
                        "is_winner": result["is_winner"],
                        "performance_bonus": result["performance_bonus"],
                        "streak_bonus": result["streak_bonus"],
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
                
                await self._send_to_user(user_id, personal_message)
            
            # 通知排行榜更新
            await self.notify_leaderboard_update(affected_users, db)
            
            logger.info(f"Game settlement notifications sent for game {game_id}")
            
        except Exception as e:
            logger.error(f"Failed to notify game settlement complete for game {game_id}: {e}")
    
    async def get_live_rank_updates(self, user_id: str, db: AsyncSession) -> Dict:
        """获取实时排名更新"""
        try:
            # 获取用户当前排名信息
            user_rank_info = await leaderboard_service.get_user_rank(user_id, db)
            if not user_rank_info:
                return {}
            
            # 获取用户周围的排名（前后各5名）
            current_rank = user_rank_info.current_rank
            start_rank = max(1, current_rank - 5)
            
            # 计算页码
            page = (start_rank - 1) // 10 + 1
            
            from app.schemas.leaderboard import LeaderboardQuery
            nearby_query = LeaderboardQuery(page=page, page_size=20, sort_by="score", order="desc")
            nearby_leaderboard = await leaderboard_service.get_leaderboard(nearby_query, db)
            
            # 筛选出用户周围的排名
            nearby_entries = []
            for entry in nearby_leaderboard.entries:
                if abs(entry.rank - current_rank) <= 5:
                    nearby_entries.append(entry.dict())
            
            return {
                "user_rank": user_rank_info.dict(),
                "nearby_rankings": nearby_entries,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get live rank updates for user {user_id}: {e}")
            return {}
    
    async def track_rank_changes(self, user_ids: List[str], db: AsyncSession):
        """跟踪用户排名变化"""
        try:
            redis = await self._get_redis()
            if not redis:
                return
            
            # 获取用户当前排名
            current_ranks = {}
            for user_id in user_ids:
                user_rank_info = await leaderboard_service.get_user_rank(user_id, db)
                if user_rank_info:
                    current_ranks[user_id] = user_rank_info.current_rank
            
            # 与之前的排名比较
            for user_id, current_rank in current_ranks.items():
                cache_key = f"previous_rank:{user_id}"
                previous_rank_str = await redis.get(cache_key)
                
                if previous_rank_str:
                    previous_rank = int(previous_rank_str)
                    if previous_rank != current_rank:
                        # 排名发生变化，发送通知
                        await self.notify_rank_change(user_id, previous_rank, current_rank, db)
                
                # 更新缓存中的排名
                await redis.set(cache_key, current_rank, ex=3600)  # 1小时过期
            
        except Exception as e:
            logger.error(f"Failed to track rank changes: {e}")
    
    async def _send_to_user(self, user_id: str, message: Dict):
        """发送消息给特定用户"""
        try:
            await connection_manager.send_to_user(user_id, message)
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")
    
    async def _broadcast_to_subscribers(self, message: Dict):
        """广播消息给所有订阅者"""
        try:
            for user_id in self.subscribers:
                await self._send_to_user(user_id, message)
        except Exception as e:
            logger.error(f"Failed to broadcast to subscribers: {e}")
    
    async def start_redis_listener(self):
        """启动Redis频道监听器"""
        try:
            redis = await self._get_redis()
            if not redis:
                return
            
            # 创建订阅者
            pubsub = redis.pubsub()
            await pubsub.subscribe(
                self.RANK_CHANGE_CHANNEL,
                self.SCORE_UPDATE_CHANNEL,
                self.LEADERBOARD_UPDATE_CHANNEL
            )
            
            logger.info("Started Redis listener for leaderboard updates")
            
            # 监听消息
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    await self._handle_redis_message(message)
                    
        except Exception as e:
            logger.error(f"Redis listener error: {e}")
    
    async def _handle_redis_message(self, message):
        """处理Redis消息"""
        try:
            channel = message['channel'].decode() if isinstance(message['channel'], bytes) else message['channel']
            data = json.loads(message['data'])
            
            if channel == self.RANK_CHANGE_CHANNEL:
                # 处理排名变化消息
                await self._broadcast_to_subscribers({
                    "event": "global_rank_change",
                    "data": data
                })
            elif channel == self.SCORE_UPDATE_CHANNEL:
                # 处理积分更新消息
                pass  # 积分更新通常只发给个人
            elif channel == self.LEADERBOARD_UPDATE_CHANNEL:
                # 处理排行榜更新消息
                await self._broadcast_to_subscribers({
                    "event": "global_leaderboard_update",
                    "data": data
                })
                
        except Exception as e:
            logger.error(f"Failed to handle Redis message: {e}")


# 全局服务实例
leaderboard_realtime_service = LeaderboardRealtimeService()