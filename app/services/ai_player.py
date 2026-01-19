"""
AI Player service for creating and managing AI opponents
AI玩家服务用于创建和管理AI对手
验证需求: 需求 4.1
"""

import uuid
import random
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.ai_player import AIPlayer, AIDifficulty, AIPersonality, AIPlayerConfig
from app.schemas.game import PlayerRole, GamePlayer
from app.core.redis_client import get_redis
from app.core.config import settings
from app.services.llm import llm_service

logger = logging.getLogger(__name__)


class AIPlayerInstance:
    """
    AI玩家游戏实例
    用于跟踪AI玩家在特定游戏中的状态
    """

    def __init__(
        self,
        ai_player: AIPlayer,
        game_id: str,
        role: PlayerRole,
        word: str
    ):
        self.ai_player = ai_player
        self.game_id = game_id
        self.role = role
        self.word = word
        self.speeches: List[str] = []
        self.votes: List[str] = []
        self.is_alive = True
        self.strategy_config = ai_player.get_strategy_config()
        self.created_at = datetime.utcnow()

    @property
    def id(self) -> str:
        return self.ai_player.id

    @property
    def name(self) -> str:
        return self.ai_player.name

    @property
    def difficulty(self) -> AIDifficulty:
        return self.ai_player.difficulty

    @property
    def personality(self) -> AIPersonality:
        return self.ai_player.personality

    def add_speech(self, content: str) -> None:
        """记录发言"""
        self.speeches.append(content)

    def add_vote(self, target_id: str) -> None:
        """记录投票"""
        self.votes.append(target_id)

    def mark_eliminated(self) -> None:
        """标记为已淘汰"""
        self.is_alive = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "game_id": self.game_id,
            "role": self.role.value,
            "word": self.word,
            "difficulty": self.difficulty.value,
            "personality": self.personality.value,
            "speeches_count": len(self.speeches),
            "votes_count": len(self.votes),
            "is_alive": self.is_alive,
            "created_at": self.created_at.isoformat()
        }

    async def generate_speech(self, game_context: Dict[str, Any]) -> Optional[str]:
        """
        生成 AI 发言

        Args:
            game_context: 游戏上下文信息

        Returns:
            Optional[str]: 生成的发言内容，失败则返回 None
        """
        try:
            logger.info(f"[AI_GEN] generate_speech called for {self.name}, role={self.role.value}")
            logger.info(f"[AI_GEN] AI config: model={self.ai_player.model_name}, api_url={self.ai_player.api_base_url or 'not set'}, key={'SET' if self.ai_player.api_key else 'NOT SET'}")

            # 获取自定义提示词（如果有）
            config = self.ai_player.config_dict or {}
            custom_system_prompt = config.get("system_prompt")
            custom_speech_prompt = config.get("speech_prompt")

            # 使用 LLM 服务生成发言，传入 AI 玩家的完整配置
            speech = await llm_service.generate_ai_speech(
                role=self.role.value,
                word=self.word,
                context=game_context,
                personality=self.personality.value,
                difficulty=self.difficulty.value,
                model=self.ai_player.model_name,
                api_base_url=self.ai_player.api_base_url,
                api_key=self.ai_player.api_key,
                custom_system_prompt=custom_system_prompt,
                custom_speech_prompt=custom_speech_prompt
            )
            logger.info(f"[AI_GEN] LLM response: {speech[:50] if speech else 'None'}...")

            # 如果 LLM 不可用，使用降级策略
            if speech is None:
                logger.warning(f"[AI_GEN] LLM returned None, using fallback for {self.name}")
                fallback = await llm_service.graceful_degradation()
                speech = fallback.get("speech", "我觉得这个词很有意思。")
                logger.info(f"[AI_GEN] Fallback speech: {speech}")

            # 记录发言
            if speech:
                self.add_speech(speech)
                logger.info(f"[AI_GEN] Speech recorded for {self.name}: {speech[:30]}...")

            return speech

        except Exception as e:
            logger.error(f"[AI_GEN] Failed to generate AI speech for {self.name}: {e}", exc_info=True)
            # 返回一个简单的备用发言
            fallback_speech = "我需要再想想。"
            self.add_speech(fallback_speech)
            return fallback_speech

    async def make_vote_decision(
        self,
        game_context: Dict[str, Any],
        available_targets: List[str]
    ) -> Optional[str]:
        """
        做出投票决策

        Args:
            game_context: 游戏上下文信息
            available_targets: 可投票的目标 ID 列表

        Returns:
            Optional[str]: 投票目标 ID，失败则返回 None
        """
        try:
            if not available_targets:
                return None

            # 过滤掉自己
            valid_targets = [t for t in available_targets if t != self.id]
            if not valid_targets:
                return None

            # 获取自定义提示词（如果有）
            config = self.ai_player.config_dict or {}
            custom_vote_prompt = config.get("vote_prompt")

            # 使用 LLM 服务生成投票决策，传入 AI 玩家的完整配置
            vote_target = await llm_service.generate_ai_vote(
                role=self.role.value,
                game_context=game_context,
                available_targets=valid_targets,
                personality=self.personality.value,
                difficulty=self.difficulty.value,
                model=self.ai_player.model_name,
                api_base_url=self.ai_player.api_base_url,
                api_key=self.ai_player.api_key,
                custom_vote_prompt=custom_vote_prompt
            )

            # 如果 LLM 返回无效结果，随机选择
            if vote_target is None or vote_target not in valid_targets:
                vote_target = random.choice(valid_targets)

            # 记录投票
            if vote_target:
                self.add_vote(vote_target)

            return vote_target

        except Exception as e:
            logger.error(f"Failed to make vote decision for {self.name}: {e}")
            # 返回随机选择
            if available_targets:
                valid_targets = [t for t in available_targets if t != self.id]
                if valid_targets:
                    return random.choice(valid_targets)
            return None


class AIPlayerService:
    """
    AI Player service
    管理AI玩家的创建、实例化和游戏状态
    验证需求: 需求 4.1
    """

    def __init__(self, db: Session):
        self.db = db
        self.redis = None
        # 内存缓存：game_id -> {ai_player_id -> AIPlayerInstance}
        self._instances: Dict[str, Dict[str, AIPlayerInstance]] = {}

    async def _get_redis(self):
        """获取Redis客户端"""
        if self.redis is None:
            self.redis = await get_redis()
        return self.redis

    async def create_ai_players_for_room(
        self,
        room_id: str,
        count: int,
        difficulty: Optional[AIDifficulty] = None,
        personalities: Optional[List[AIPersonality]] = None
    ) -> List[AIPlayer]:
        """
        为房间创建AI玩家

        Args:
            room_id: 房间ID
            count: AI玩家数量
            difficulty: 难度等级（可选，默认随机）
            personalities: 个性列表（可选，默认随机）

        Returns:
            List[AIPlayer]: 创建的AI玩家列表
        """
        try:
            ai_players = []

            # 获取可用的AI名称
            available_names = self._get_available_names(count, difficulty)

            # 获取可用的 AI 模型列表
            available_models = settings.ai_models_list

            for i in range(count):
                # 确定难度
                player_difficulty = difficulty or random.choice(list(AIDifficulty))

                # 确定个性
                if personalities and i < len(personalities):
                    player_personality = personalities[i]
                else:
                    player_personality = random.choice(list(AIPersonality))

                # 选择名称
                name = available_names[i] if i < len(available_names) else f"AI玩家{i+1}"

                # 为每个 AI 分配不同的模型（循环使用可用模型）
                model_name = available_models[i % len(available_models)] if available_models else None

                # 创建AI玩家，应用全局 API 配置
                ai_player = AIPlayer(
                    id=str(uuid.uuid4()),
                    name=name,
                    difficulty=player_difficulty,
                    personality=player_personality,
                    model_name=model_name,
                    api_base_url=settings.OPENAI_BASE_URL,  # 应用全局 API URL
                    api_key=settings.OPENAI_API_KEY,        # 应用全局 API Key
                    config=None,
                    is_active=True
                )

                # 设置默认配置
                ai_player.config_dict = AIPlayerConfig.create_default_config(
                    player_difficulty, player_personality
                )

                # 添加到数据库
                self.db.add(ai_player)
                ai_players.append(ai_player)

                logger.info(
                    f"Created AI player: {name} "
                    f"(difficulty={player_difficulty.value}, personality={player_personality.value}, "
                    f"model={model_name}, api_url={'SET' if settings.OPENAI_BASE_URL else 'default'}, "
                    f"api_key={'SET' if settings.OPENAI_API_KEY else 'NOT SET'})"
                )

            # 提交事务
            await self.db.commit()

            # 缓存到Redis
            await self._cache_ai_players(room_id, ai_players)

            return ai_players

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create AI players for room {room_id}: {e}")
            raise

    async def create_ai_player_instance(
        self,
        ai_player: AIPlayer,
        game_id: str,
        role: PlayerRole,
        word: str
    ) -> AIPlayerInstance:
        """
        创建AI玩家游戏实例

        Args:
            ai_player: AI玩家模型
            game_id: 游戏ID
            role: 玩家角色
            word: 分配的词汇

        Returns:
            AIPlayerInstance: AI玩家游戏实例
        """
        try:
            # 创建实例
            instance = AIPlayerInstance(
                ai_player=ai_player,
                game_id=game_id,
                role=role,
                word=word
            )

            # 存储到内存缓存
            if game_id not in self._instances:
                self._instances[game_id] = {}
            self._instances[game_id][ai_player.id] = instance

            # 同时缓存到Redis（用于分布式场景）
            await self._cache_instance(instance)

            logger.info(
                f"Created AI player instance: {ai_player.name} "
                f"(game={game_id}, role={role.value})"
            )

            return instance

        except Exception as e:
            logger.error(f"Failed to create AI player instance: {e}")
            raise

    async def get_ai_player_instance(
        self,
        game_id: str,
        ai_player_id: str
    ) -> Optional[AIPlayerInstance]:
        """
        获取AI玩家游戏实例

        Args:
            game_id: 游戏ID
            ai_player_id: AI玩家ID

        Returns:
            Optional[AIPlayerInstance]: AI玩家实例，不存在则返回None
        """
        try:
            # 首先从内存缓存获取
            if game_id in self._instances:
                if ai_player_id in self._instances[game_id]:
                    return self._instances[game_id][ai_player_id]

            # 从Redis缓存获取
            instance = await self._get_cached_instance(game_id, ai_player_id)
            if instance:
                # 存入内存缓存
                if game_id not in self._instances:
                    self._instances[game_id] = {}
                self._instances[game_id][ai_player_id] = instance
                return instance

            logger.warning(
                f"AI player instance not found: game={game_id}, player={ai_player_id}"
            )
            return None

        except Exception as e:
            logger.error(f"Failed to get AI player instance: {e}")
            return None

    async def get_ai_player(self, ai_player_id: str) -> Optional[AIPlayer]:
        """
        获取AI玩家模型

        Args:
            ai_player_id: AI玩家ID

        Returns:
            Optional[AIPlayer]: AI玩家模型
        """
        try:
            stmt = select(AIPlayer).filter(AIPlayer.id == ai_player_id)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get AI player {ai_player_id}: {e}")
            return None

    async def update_ai_player_stats(
        self,
        ai_player_id: str,
        game_won: bool = False
    ) -> None:
        """
        更新AI玩家统计数据

        Args:
            ai_player_id: AI玩家ID
            game_won: 是否获胜
        """
        try:
            ai_player = await self.get_ai_player(ai_player_id)
            if ai_player:
                ai_player.games_played += 1
                if game_won:
                    ai_player.games_won += 1
                ai_player.updated_at = datetime.utcnow()
                await self.db.commit()

                logger.info(
                    f"Updated AI player stats: {ai_player.name} "
                    f"(games={ai_player.games_played}, wins={ai_player.games_won})"
                )
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update AI player stats: {e}")

    async def record_ai_speech(
        self,
        game_id: str,
        ai_player_id: str,
        content: str
    ) -> None:
        """
        记录AI玩家发言

        Args:
            game_id: 游戏ID
            ai_player_id: AI玩家ID
            content: 发言内容
        """
        try:
            instance = await self.get_ai_player_instance(game_id, ai_player_id)
            if instance:
                instance.add_speech(content)

                # 更新数据库统计
                ai_player = await self.get_ai_player(ai_player_id)
                if ai_player:
                    ai_player.total_speeches += 1
                    await self.db.commit()

                logger.debug(f"Recorded AI speech: {ai_player_id} in game {game_id}")
        except Exception as e:
            logger.error(f"Failed to record AI speech: {e}")

    async def record_ai_vote(
        self,
        game_id: str,
        ai_player_id: str,
        target_id: str
    ) -> None:
        """
        记录AI玩家投票

        Args:
            game_id: 游戏ID
            ai_player_id: AI玩家ID
            target_id: 被投票目标ID
        """
        try:
            instance = await self.get_ai_player_instance(game_id, ai_player_id)
            if instance:
                instance.add_vote(target_id)

                # 更新数据库统计
                ai_player = await self.get_ai_player(ai_player_id)
                if ai_player:
                    ai_player.total_votes += 1
                    await self.db.commit()

                logger.debug(
                    f"Recorded AI vote: {ai_player_id} -> {target_id} in game {game_id}"
                )
        except Exception as e:
            logger.error(f"Failed to record AI vote: {e}")

    async def cleanup_game_instances(self, game_id: str) -> None:
        """
        清理游戏结束后的AI实例

        Args:
            game_id: 游戏ID
        """
        try:
            # 清理内存缓存
            if game_id in self._instances:
                del self._instances[game_id]

            # 清理Redis缓存
            redis = await self._get_redis()
            pattern = f"ai_instance:{game_id}:*"
            keys = await redis.keys(pattern)
            if keys:
                await redis.delete(*keys)

            logger.info(f"Cleaned up AI instances for game {game_id}")

        except Exception as e:
            logger.error(f"Failed to cleanup AI instances: {e}")

    def _get_available_names(
        self,
        count: int,
        difficulty: Optional[AIDifficulty] = None
    ) -> List[str]:
        """获取可用的AI名称列表"""
        all_names = AIPlayerConfig.get_default_names()

        if difficulty:
            # 使用指定难度的名称
            names = all_names.get(difficulty, [])
        else:
            # 混合所有难度的名称
            names = []
            for difficulty_names in all_names.values():
                names.extend(difficulty_names)

        # 随机打乱并返回需要的数量
        random.shuffle(names)
        return names[:count]

    async def _cache_ai_players(
        self,
        room_id: str,
        ai_players: List[AIPlayer]
    ) -> None:
        """缓存AI玩家到Redis"""
        try:
            redis = await self._get_redis()
            cache_key = f"room_ai_players:{room_id}"

            player_data = [
                {
                    "id": p.id,
                    "name": p.name,
                    "difficulty": p.difficulty.value,
                    "personality": p.personality.value
                }
                for p in ai_players
            ]

            import json
            await redis.set(cache_key, json.dumps(player_data), ex=3600)

        except Exception as e:
            logger.error(f"Failed to cache AI players: {e}")

    async def _cache_instance(self, instance: AIPlayerInstance) -> None:
        """缓存AI实例到Redis"""
        try:
            redis = await self._get_redis()
            cache_key = f"ai_instance:{instance.game_id}:{instance.id}"

            import json
            await redis.set(cache_key, json.dumps(instance.to_dict()), ex=7200)

        except Exception as e:
            logger.error(f"Failed to cache AI instance: {e}")

    async def _get_cached_instance(
        self,
        game_id: str,
        ai_player_id: str
    ) -> Optional[AIPlayerInstance]:
        """从Redis获取缓存的AI实例"""
        try:
            redis = await self._get_redis()
            cache_key = f"ai_instance:{game_id}:{ai_player_id}"

            cached_data = await redis.get(cache_key)
            if not cached_data:
                return None

            import json
            data = json.loads(cached_data)

            # 获取AI玩家模型
            ai_player = await self.get_ai_player(ai_player_id)
            if not ai_player:
                return None

            # 重建实例
            instance = AIPlayerInstance(
                ai_player=ai_player,
                game_id=game_id,
                role=PlayerRole(data["role"]),
                word=data["word"]
            )
            instance.is_alive = data.get("is_alive", True)

            return instance

        except Exception as e:
            logger.error(f"Failed to get cached AI instance: {e}")
            return None

    async def get_game_ai_players(self, game_id: str) -> List[AIPlayerInstance]:
        """
        获取游戏中所有AI玩家实例

        Args:
            game_id: 游戏ID

        Returns:
            List[AIPlayerInstance]: AI玩家实例列表
        """
        if game_id in self._instances:
            return list(self._instances[game_id].values())
        return []

    async def mark_ai_eliminated(
        self,
        game_id: str,
        ai_player_id: str
    ) -> None:
        """
        标记AI玩家被淘汰

        Args:
            game_id: 游戏ID
            ai_player_id: AI玩家ID
        """
        try:
            instance = await self.get_ai_player_instance(game_id, ai_player_id)
            if instance:
                instance.mark_eliminated()
                await self._cache_instance(instance)
                logger.info(f"AI player {ai_player_id} eliminated in game {game_id}")
        except Exception as e:
            logger.error(f"Failed to mark AI eliminated: {e}")


def get_ai_player_service(db: Session) -> AIPlayerService:
    """获取AI玩家服务实例"""
    return AIPlayerService(db)
