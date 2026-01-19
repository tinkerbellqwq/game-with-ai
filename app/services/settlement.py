"""
Settlement service
积分结算系统服务
"""

import uuid
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func
from sqlalchemy.exc import SQLAlchemyError

from app.models.user import User
from app.models.game import Game, Speech, Vote
from app.models.participant import Participant
from app.schemas.game import GameState, PlayerRole, GamePlayer
from app.core.database import get_db
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


class SettlementService:
    """积分结算服务"""
    
    def __init__(self, db: Session):
        self.db = db
        self.redis = None  # 延迟初始化
    
    async def _get_redis(self):
        """获取Redis客户端"""
        if self.redis is None:
            self.redis = await get_redis()
        return self.redis
    
    async def calculate_game_settlement(self, game_id: str) -> Dict[str, Dict]:
        """计算游戏结算结果"""
        # 获取游戏信息
        game = await self._get_game(game_id)
        if not game or not game.finished_at:
            raise ValueError("游戏未结束或不存在")
        
        # 获取游戏状态
        players = [GamePlayer(**player_data) for player_data in game.players]
        
        # 计算每个玩家的积分变化
        settlement_results = {}
        
        for player in players:
            if player.is_ai:
                continue  # AI玩家不参与积分结算
            
            # 计算基础积分
            base_score = await self._calculate_base_score(player, game)
            
            # 计算表现奖励
            performance_bonus = await self._calculate_performance_bonus(game_id, player.id)
            
            # 计算连胜奖励
            streak_bonus = await self._calculate_streak_bonus(player.id)
            
            # 总积分变化
            total_score_change = base_score + performance_bonus + streak_bonus
            
            # 确保积分不会变成负数（用户总积分有最低限制）
            user = await self._get_user(player.id)
            if user and user.score + total_score_change < 0:
                total_score_change = -user.score  # 最多扣到0分
            
            settlement_results[player.id] = {
                'player_id': player.id,
                'username': player.username,
                'role': player.role.value,
                'is_winner': player.id in (game.winner_players or []),
                'is_alive': player.is_alive,
                'base_score': base_score,
                'performance_bonus': performance_bonus,
                'streak_bonus': streak_bonus,
                'total_score_change': total_score_change,
                'final_score': (user.score + total_score_change) if user else total_score_change
            }
        
        return settlement_results
    
    async def _calculate_base_score(self, player: GamePlayer, game: Game) -> int:
        """计算基础积分"""
        is_winner = player.id in (game.winner_players or [])
        
        if is_winner:
            # 胜利奖励
            return 10
        else:
            # 失败惩罚
            return -5
    
    async def _calculate_performance_bonus(self, game_id: str, player_id: str) -> int:
        """计算表现奖励"""
        bonus = 0
        
        # 获取玩家发言记录
        speeches = await self._get_player_speeches(game_id, player_id)
        
        # 发言质量奖励（基于发言数量和长度）
        if speeches:
            speech_count = len(speeches)
            avg_length = sum(len(speech.content) for speech in speeches) / speech_count
            
            # 发言数量奖励（最多3分）
            if speech_count >= 3:
                bonus += 3
            elif speech_count >= 2:
                bonus += 2
            elif speech_count >= 1:
                bonus += 1
            
            # 发言质量奖励（基于平均长度，最多2分）
            if avg_length >= 50:
                bonus += 2
            elif avg_length >= 30:
                bonus += 1
        
        # 生存轮次奖励
        game = await self._get_game(game_id)
        if game:
            survival_rounds = await self._calculate_survival_rounds(game_id, player_id)
            # 每生存一轮获得0.5分，最多3分
            survival_bonus = min(int(survival_rounds * 0.5), 3)
            bonus += survival_bonus
        
        return min(bonus, 8)  # 表现奖励最多8分
    
    async def _calculate_streak_bonus(self, player_id: str) -> int:
        """计算连胜奖励"""
        # 获取玩家最近的游戏记录
        recent_games = await self._get_recent_games(player_id, limit=5)
        
        if not recent_games:
            return 0
        
        # 计算连胜次数
        consecutive_wins = 0
        for game in recent_games:
            if game.winner_players and player_id in game.winner_players:
                consecutive_wins += 1
            else:
                break
        
        # 连胜奖励：2连胜+1分，3连胜+2分，4连胜+3分，5连胜+5分
        if consecutive_wins >= 5:
            return 5
        elif consecutive_wins >= 4:
            return 3
        elif consecutive_wins >= 3:
            return 2
        elif consecutive_wins >= 2:
            return 1
        
        return 0
    
    async def _calculate_survival_rounds(self, game_id: str, player_id: str) -> int:
        """计算玩家生存轮次"""
        game = await self._get_game(game_id)
        if not game:
            return 0
        
        # 检查玩家是否被淘汰
        if player_id in (game.eliminated_players or []):
            # 通过投票记录推算被淘汰的轮次
            votes = await self._get_elimination_votes(game_id, player_id)
            if votes:
                return votes[0].round_number
            return 1  # 默认第一轮被淘汰
        else:
            # 玩家存活到最后
            return game.round_number
    
    async def apply_settlement(self, game_id: str) -> Dict[str, Dict]:
        """应用积分结算（带事务处理）"""
        try:
            # 开始事务
            settlement_results = await self.calculate_game_settlement(game_id)
            
            # 批量更新用户积分
            await self._batch_update_user_scores(settlement_results)
            
            # 实时更新缓存
            await self._update_score_cache(settlement_results)
            
            # 更新排行榜缓存
            await self._update_leaderboard_cache(settlement_results)
            
            # 发送实时通知
            await self._send_settlement_notifications(game_id, settlement_results)
            
            # 记录结算日志
            await self._log_settlement(game_id, settlement_results)
            
            logger.info(f"Settlement applied successfully for game {game_id}")
            return settlement_results
            
        except Exception as e:
            # 回滚事务
            await self.db.rollback()
            logger.error(f"Settlement failed for game {game_id}: {e}")
            raise
    
    async def _batch_update_user_scores(self, settlement_results: Dict[str, Dict]):
        """批量更新用户积分（事务安全）"""
        try:
            for player_id, result in settlement_results.items():
                await self._update_user_score_transactional(
                    player_id, 
                    result['total_score_change'],
                    result['is_winner']
                )
            
            # 提交所有更新
            await self.db.commit()
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Failed to batch update user scores: {e}")
            raise
    
    async def _update_user_score_transactional(self, user_id: str, score_change: int, is_winner: bool):
        """事务安全的用户积分更新"""
        # 使用行锁防止并发更新问题
        stmt = select(User).filter(User.id == user_id).with_for_update()
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(f"User {user_id} not found for score update")
            return

        # 记录更新前的积分
        old_score = user.score

        # 更新积分和统计
        user.score += score_change
        user.games_played += 1

        # 更新累计获得积分（只计算正向积分）
        if score_change > 0:
            user.total_score_earned += score_change

        if is_winner:
            user.games_won += 1
            # 更新连胜记录
            user.consecutive_wins += 1
            if user.consecutive_wins > user.max_consecutive_wins:
                user.max_consecutive_wins = user.consecutive_wins
        else:
            # 输了则重置连胜
            user.consecutive_wins = 0

        # 确保积分不为负数
        if user.score < 0:
            user.score = 0

        # 更新最后游戏时间
        user.last_game_at = datetime.utcnow()

        # 更新时间戳
        user.updated_at = datetime.utcnow()

        logger.info(f"User {user_id} score updated: {old_score} -> {user.score} (change: {score_change})")
    
    async def _update_score_cache(self, settlement_results: Dict[str, Dict]):
        """实时更新积分缓存"""
        redis = await self._get_redis()
        
        try:
            # 使用管道批量更新缓存
            pipe = redis.pipeline()
            
            for player_id, result in settlement_results.items():
                # 更新用户积分缓存
                cache_key = f"user_score:{player_id}"
                pipe.set(cache_key, result['final_score'], ex=3600)  # 1小时过期
                
                # 更新用户统计缓存
                stats_key = f"user_stats:{player_id}"
                user = await self._get_user(player_id)
                if user:
                    stats_data = {
                        'score': user.score,
                        'games_played': user.games_played,
                        'games_won': user.games_won,
                        'win_rate': user.win_rate,
                        'updated_at': datetime.utcnow().isoformat()
                    }
                    pipe.hset(stats_key, mapping=stats_data)
                    pipe.expire(stats_key, 3600)
            
            # 执行所有缓存更新
            await pipe.execute()
            
        except Exception as e:
            logger.error(f"Failed to update score cache: {e}")
            # 缓存更新失败不应该影响主流程
    
    async def _send_settlement_notifications(self, game_id: str, settlement_results: Dict[str, Dict]):
        """发送结算通知"""
        try:
            from app.services.leaderboard_realtime import leaderboard_realtime_service
            
            # 发送游戏结算完成通知
            await leaderboard_realtime_service.notify_game_settlement_complete(
                game_id, settlement_results, self.db
            )
            
            logger.info(f"Settlement notifications sent for game {game_id}")
            
        except Exception as e:
            logger.error(f"Failed to send settlement notifications for game {game_id}: {e}")
            # 通知发送失败不应该影响主流程
    
    async def _update_leaderboard_cache(self, settlement_results: Dict[str, Dict]):
        """更新排行榜缓存"""
        try:
            # 导入排行榜服务（避免循环导入）
            from app.services.leaderboard import leaderboard_service
            from app.services.leaderboard_realtime import leaderboard_realtime_service
            
            # 清除排行榜缓存
            await leaderboard_service.invalidate_leaderboard_cache()
            
            # 清除受影响用户的排名缓存
            for player_id in settlement_results.keys():
                await leaderboard_service.invalidate_user_rank_cache(player_id)
            
            # 发送实时更新通知
            affected_users = list(settlement_results.keys())
            if hasattr(self, 'db') and self.db:
                await leaderboard_realtime_service.notify_leaderboard_update(affected_users, self.db)
            
            logger.info(f"Leaderboard cache updated for {len(settlement_results)} players")
            
        except Exception as e:
            logger.error(f"Failed to update leaderboard cache: {e}")
            # 排行榜缓存更新失败不应该影响主流程
    
    async def _log_settlement(self, game_id: str, settlement_results: Dict[str, Dict]):
        """记录结算日志"""
        redis = await self._get_redis()
        
        try:
            # 创建结算记录
            settlement_log = {
                'game_id': game_id,
                'timestamp': datetime.utcnow().isoformat(),
                'player_count': len(settlement_results),
                'total_score_distributed': sum(r['total_score_change'] for r in settlement_results.values()),
                'results': settlement_results
            }
            
            # 存储到Redis（用于审计和调试）
            log_key = f"settlement_log:{game_id}"
            await redis.set(log_key, str(settlement_log), ex=86400)  # 24小时过期
            
            # 添加到结算历史列表
            history_key = "settlement_history"
            await redis.lpush(history_key, f"{game_id}:{datetime.utcnow().isoformat()}")
            await redis.ltrim(history_key, 0, 999)  # 保留最近1000条记录
            
        except Exception as e:
            logger.error(f"Failed to log settlement for game {game_id}: {e}")
    
    async def get_real_time_score(self, user_id: str) -> Optional[int]:
        """获取实时积分（优先从缓存）"""
        redis = await self._get_redis()
        
        try:
            # 先从缓存获取
            cache_key = f"user_score:{user_id}"
            cached_score = await redis.get(cache_key)
            
            if cached_score is not None:
                return int(cached_score)
            
            # 缓存未命中，从数据库获取并更新缓存
            user = await self._get_user(user_id)
            if user:
                await redis.set(cache_key, user.score, ex=3600)
                return user.score
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get real-time score for user {user_id}: {e}")
            # 降级到数据库查询
            user = await self._get_user(user_id)
            return user.score if user else None
    
    async def get_real_time_user_stats(self, user_id: str) -> Optional[Dict]:
        """获取实时用户统计（优先从缓存）"""
        redis = await self._get_redis()
        
        try:
            # 先从缓存获取
            stats_key = f"user_stats:{user_id}"
            cached_stats = await redis.hgetall(stats_key)
            
            if cached_stats:
                return {
                    'score': int(cached_stats.get('score', 0)),
                    'games_played': int(cached_stats.get('games_played', 0)),
                    'games_won': int(cached_stats.get('games_won', 0)),
                    'win_rate': float(cached_stats.get('win_rate', 0.0)),
                    'updated_at': cached_stats.get('updated_at')
                }
            
            # 缓存未命中，从数据库获取并更新缓存
            user = await self._get_user(user_id)
            if user:
                stats_data = {
                    'score': user.score,
                    'games_played': user.games_played,
                    'games_won': user.games_won,
                    'win_rate': user.win_rate,
                    'updated_at': datetime.utcnow().isoformat()
                }
                
                # 更新缓存
                await redis.hset(stats_key, mapping=stats_data)
                await redis.expire(stats_key, 3600)
                
                return stats_data
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get real-time stats for user {user_id}: {e}")
            # 降级到数据库查询
            user = await self._get_user(user_id)
            if user:
                return {
                    'score': user.score,
                    'games_played': user.games_played,
                    'games_won': user.games_won,
                    'win_rate': user.win_rate,
                    'updated_at': user.updated_at.isoformat() if user.updated_at else None
                }
            return None
    
    async def invalidate_user_cache(self, user_id: str):
        """清除用户缓存"""
        redis = await self._get_redis()
        
        try:
            cache_keys = [
                f"user_score:{user_id}",
                f"user_stats:{user_id}"
            ]
            
            await redis.delete(*cache_keys)
            logger.info(f"Cache invalidated for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to invalidate cache for user {user_id}: {e}")
    
    async def get_settlement_history(self, limit: int = 10) -> List[Dict]:
        """获取结算历史"""
        redis = await self._get_redis()
        
        try:
            history_key = "settlement_history"
            history_items = await redis.lrange(history_key, 0, limit - 1)
            
            settlement_history = []
            for item in history_items:
                if isinstance(item, bytes):
                    item = item.decode()
                
                game_id, timestamp = item.split(':', 1)
                
                # 获取详细的结算记录
                log_key = f"settlement_log:{game_id}"
                log_data = await redis.get(log_key)
                
                if log_data:
                    settlement_history.append({
                        'game_id': game_id,
                        'timestamp': timestamp,
                        'details': eval(log_data) if isinstance(log_data, str) else log_data
                    })
            
            return settlement_history
            
        except Exception as e:
            logger.error(f"Failed to get settlement history: {e}")
            return []
    
    async def recalculate_user_stats(self, user_id: str) -> Dict:
        """重新计算用户统计（修复数据不一致）"""
        try:
            # 获取用户所有游戏记录
            user_games = await self._get_user_all_games(user_id)
            
            # 重新计算统计数据
            total_games = len(user_games)
            total_wins = sum(1 for game in user_games if user_id in (game.winner_players or []))
            win_rate = (total_wins / total_games * 100) if total_games > 0 else 0.0
            
            # 更新数据库
            user = await self._get_user(user_id)
            if user:
                user.games_played = total_games
                user.games_won = total_wins
                user.updated_at = datetime.utcnow()
                
                await self.db.commit()
                
                # 清除缓存，强制重新加载
                await self.invalidate_user_cache(user_id)
                
                logger.info(f"User {user_id} stats recalculated: {total_games} games, {total_wins} wins")
                
                return {
                    'user_id': user_id,
                    'games_played': total_games,
                    'games_won': total_wins,
                    'win_rate': win_rate,
                    'score': user.score
                }
            
            return {}
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to recalculate stats for user {user_id}: {e}")
            raise
    
    async def _get_user_all_games(self, user_id: str) -> List[Game]:
        """获取用户所有游戏记录"""
        # 简化实现：通过JSON字段查询
        stmt = select(Game).filter(
            and_(
                Game.finished_at.isnot(None),
                Game.players.contains(f'"id": "{user_id}"')
            )
        ).order_by(Game.finished_at.desc())
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_player_performance_analysis(self, game_id: str, player_id: str) -> Dict:
        """获取玩家表现分析"""
        game = await self._get_game(game_id)
        if not game:
            raise ValueError("游戏不存在")
        
        # 获取玩家信息
        player_data = next(
            (p for p in game.players if p['id'] == player_id), 
            None
        )
        if not player_data:
            raise ValueError("玩家不在游戏中")
        
        player = GamePlayer(**player_data)
        
        # 获取发言记录
        speeches = await self._get_player_speeches(game_id, player_id)
        
        # 获取投票记录
        votes_cast = await self._get_player_votes(game_id, player_id)
        votes_received = await self._get_votes_against_player(game_id, player_id)
        
        # 计算各项指标
        analysis = {
            'player_id': player_id,
            'username': player.username,
            'role': player.role.value,
            'word': player.word,
            'is_winner': player_id in (game.winner_players or []),
            'is_alive': player.is_alive,
            'survival_rounds': await self._calculate_survival_rounds(game_id, player_id),
            'total_rounds': game.round_number,
            'speeches': {
                'count': len(speeches),
                'average_length': (
                    sum(len(s.content) for s in speeches) / len(speeches)
                    if speeches else 0
                ),
                'details': [
                    {
                        'round': s.round_number,
                        'order': s.speech_order,
                        'content': s.content,
                        'length': len(s.content)
                    }
                    for s in speeches
                ]
            },
            'voting': {
                'votes_cast': len(votes_cast),
                'votes_received': len(votes_received),
                'vote_targets': [v.target_id for v in votes_cast],
                'voters': [v.voter_id for v in votes_received]
            },
            'performance_score': await self._calculate_performance_bonus(game_id, player_id)
        }
        
        return analysis
    
    async def get_mvp_analysis(self, game_id: str) -> Optional[Dict]:
        """获取MVP分析"""
        game = await self._get_game(game_id)
        if not game or not game.finished_at:
            return None
        
        # 分析所有真人玩家的表现
        player_analyses = []
        for player_data in game.players:
            if not player_data.get('is_ai', False):
                analysis = await self.get_player_performance_analysis(game_id, player_data['id'])
                player_analyses.append(analysis)
        
        if not player_analyses:
            return None
        
        # 计算MVP评分
        for analysis in player_analyses:
            mvp_score = 0
            
            # 胜利加分
            if analysis['is_winner']:
                mvp_score += 20
            
            # 生存加分
            survival_rate = analysis['survival_rounds'] / analysis['total_rounds']
            mvp_score += survival_rate * 10
            
            # 发言质量加分
            speech_score = min(analysis['speeches']['count'] * 2, 10)
            if analysis['speeches']['average_length'] > 30:
                speech_score += 5
            mvp_score += speech_score
            
            # 投票准确性加分（简化计算）
            if analysis['voting']['votes_cast'] > 0:
                mvp_score += 5
            
            analysis['mvp_score'] = mvp_score
        
        # 找出MVP
        mvp = max(player_analyses, key=lambda x: x['mvp_score'])
        mvp['is_mvp'] = True
        
        return mvp
    
    # 辅助方法
    async def _get_game(self, game_id: str) -> Optional[Game]:
        """获取游戏记录"""
        stmt = select(Game).filter(Game.id == game_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_user(self, user_id: str) -> Optional[User]:
        """获取用户记录"""
        stmt = select(User).filter(User.id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_player_speeches(self, game_id: str, player_id: str) -> List[Speech]:
        """获取玩家发言记录（通过 participants 表关联）"""
        # 先找到该玩家在此游戏中的 participant 记录
        participant_stmt = select(Participant).filter(
            and_(Participant.game_id == game_id, Participant.player_id == player_id)
        )
        participant_result = await self.db.execute(participant_stmt)
        participant = participant_result.scalar_one_or_none()

        if not participant:
            return []

        # 通过 participant_id 查询发言记录
        stmt = select(Speech).filter(
            and_(Speech.game_id == game_id, Speech.participant_id == participant.id)
        ).order_by(Speech.round_number, Speech.speech_order)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def _get_player_votes(self, game_id: str, player_id: str) -> List[Vote]:
        """获取玩家投票记录（通过 participants 表关联）"""
        # 先找到该玩家在此游戏中的 participant 记录
        participant_stmt = select(Participant).filter(
            and_(Participant.game_id == game_id, Participant.player_id == player_id)
        )
        participant_result = await self.db.execute(participant_stmt)
        participant = participant_result.scalar_one_or_none()

        if not participant:
            return []

        stmt = select(Vote).filter(
            and_(Vote.game_id == game_id, Vote.voter_id == participant.id)
        ).order_by(Vote.round_number)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def _get_votes_against_player(self, game_id: str, player_id: str) -> List[Vote]:
        """获取针对玩家的投票记录（通过 participants 表关联）"""
        # 先找到该玩家在此游戏中的 participant 记录
        participant_stmt = select(Participant).filter(
            and_(Participant.game_id == game_id, Participant.player_id == player_id)
        )
        participant_result = await self.db.execute(participant_stmt)
        participant = participant_result.scalar_one_or_none()

        if not participant:
            return []

        stmt = select(Vote).filter(
            and_(Vote.game_id == game_id, Vote.target_id == participant.id)
        ).order_by(Vote.round_number)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def _get_elimination_votes(self, game_id: str, player_id: str) -> List[Vote]:
        """获取导致玩家被淘汰的投票记录"""
        # 简化实现：获取针对该玩家的所有投票
        return await self._get_votes_against_player(game_id, player_id)
    
    async def _get_recent_games(self, player_id: str, limit: int = 5) -> List[Game]:
        """获取玩家最近的游戏记录"""
        # 这里需要一个更复杂的查询来找到包含特定玩家的游戏
        # 简化实现：通过JSON字段查询（实际生产环境可能需要优化）
        stmt = select(Game).filter(
            and_(
                Game.finished_at.isnot(None),
                Game.players.contains(f'"id": "{player_id}"')  # 简化的JSON查询
            )
        ).order_by(Game.finished_at.desc()).limit(limit)
        
        result = await self.db.execute(stmt)
        return result.scalars().all()


def get_settlement_service(db: Session) -> SettlementService:
    """获取积分结算服务实例"""
    return SettlementService(db)