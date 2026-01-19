"""
Game service
游戏核心逻辑服务
"""

import uuid
import random
import logging
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from app.models.game import Game, Speech, Vote
from app.models.word_pair import WordPair
from app.models.user import User
from app.models.ai_player import AIPlayer
from app.models.participant import Participant
from app.schemas.game import (
    GameState, GamePlayer, GameCreate, VoteResult, 
    SpeechCreate, VoteCreate, GameResponse, PlayerRole, GamePhase
)
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.services.ai_player import get_ai_player_service, AIPlayerInstance
from app.services.game_recorder import get_game_recorder
from app.websocket.connection_manager import connection_manager

logger = logging.getLogger(__name__)


class GameEngine:
    """游戏引擎 - 管理游戏状态和逻辑"""
    
    def __init__(self, db: Session):
        self.db = db
        self.redis = None  # 延迟初始化
        self.ai_player_service = get_ai_player_service(db)
        self.game_recorder = get_game_recorder(db)
    
    async def _get_redis(self):
        """获取Redis客户端"""
        if self.redis is None:
            self.redis = await get_redis()
        return self.redis
    
    async def create_game(self, game_create: GameCreate, players: List[User], ai_players: List[AIPlayer] = None) -> GameState:
        """创建新游戏"""
        total_players = len(players) + (len(ai_players) if ai_players else 0)
        
        if total_players < 3:
            raise ValueError("游戏至少需要3名玩家")
        if total_players > 10:
            raise ValueError("游戏最多支持10名玩家")
        
        # 选择词汇对
        word_pair = await self._select_word_pair(game_create.word_pair_id, 
                                                game_create.difficulty, 
                                                game_create.category)
        if not word_pair:
            raise ValueError("未找到合适的词汇对")
        
        # 分配角色（包括AI玩家）
        game_players = await self._assign_roles(players, word_pair, ai_players)
        
        # 创建游戏记录
        game_id = str(uuid.uuid4())
        game = Game(
            id=game_id,
            room_id=game_create.room_id,
            word_pair_id=word_pair.id,
            current_phase=GamePhase.PREPARING,
            round_number=1,
            players=[player.model_dump() for player in game_players]
        )
        
        self.db.add(game)
        await self.db.commit()
        await self.db.refresh(game)

        # 创建参与者记录 (用于 speeches 和 votes 的外键)
        await self._create_participants(game_id, game_players)

        # 创建游戏状态
        game_state = GameState(
            id=game.id,
            room_id=game.room_id,
            word_pair_id=game.word_pair_id,
            current_phase=game.current_phase,
            round_number=game.round_number,
            players=game_players,
            started_at=game.started_at
        )
        
        # 为AI玩家创建游戏实例
        if ai_players:
            await self._create_ai_player_instances(game_id, game_players, ai_players)
        
        # 缓存游戏状态到Redis
        await self._cache_game_state(game_state)
        
        # 记录游戏创建
        await self.game_recorder.record_game_start(
            game_id=game_id,
            game_data={
                "room_id": game_create.room_id,
                "word_pair_id": word_pair.id,
                "players": [player.model_dump() for player in game_players],
                "settings": {
                    "difficulty": game_create.difficulty,
                    "category": game_create.category
                }
            }
        )
        
        return game_state
    
    async def start_game(self, game_id: str) -> GameState:
        """开始游戏"""
        game_state = await self._get_game_state(game_id)
        if not game_state:
            raise ValueError("游戏不存在")
        
        if game_state.current_phase != GamePhase.PREPARING:
            raise ValueError("游戏已经开始")
        
        # 检查所有玩家是否准备就绪
        if not all(player.is_ready for player in game_state.players):
            raise ValueError("还有玩家未准备就绪")
        
        # 进入发言阶段
        game_state.current_phase = GamePhase.SPEAKING
        game_state.current_speaker = game_state.players[0].id
        
        # 更新数据库
        await self._update_game_in_db(game_state)
        
        # 更新缓存
        await self._cache_game_state(game_state)
        
        return game_state
    
    async def handle_speech(self, game_id: str, player_id: str, speech_create: SpeechCreate) -> GameState:
        """处理玩家发言"""
        game_state = await self._get_game_state(game_id)
        if not game_state:
            raise ValueError("游戏不存在")
        
        if game_state.current_phase != GamePhase.SPEAKING:
            raise ValueError("当前不是发言阶段")
        
        if game_state.current_speaker != player_id:
            raise ValueError("当前不是您的发言轮次")
        
        # 检查玩家是否存活
        player = next((p for p in game_state.players if p.id == player_id), None)
        if not player or not player.is_alive:
            raise ValueError("玩家不存在或已被淘汰")

        # 获取或创建参与者记录
        participant_id = await self._ensure_participant_exists(game_id, player_id)
        if not participant_id:
            logger.error(f"Failed to get/create participant for player {player_id} in game {game_id}, game may have been deleted")
            raise ValueError("无法创建参与者记录，游戏可能已被删除")

        # 记录发言
        speech_order = await self._get_next_speech_order(game_id, game_state.round_number)
        speech = Speech(
            id=str(uuid.uuid4()),
            game_id=game_id,
            participant_id=participant_id,  # 使用 participant_id
            content=speech_create.content,
            round_number=game_state.round_number,
            speech_order=speech_order
        )
        
        self.db.add(speech)
        await self.db.commit()
        
        # 记录发言到游戏记录
        await self.game_recorder.record_speech(
            game_id=game_id,
            player_id=player_id,
            speech_data={
                "content": speech_create.content,
                "round_number": game_state.round_number,
                "speech_order": speech_order
            }
        )
        
        # 切换到下一个发言者
        await self._next_speaker(game_state)
        
        # 更新缓存
        await self._cache_game_state(game_state)
        
        return game_state
    
    async def handle_vote(self, game_id: str, voter_id: str, vote_create: VoteCreate) -> GameState:
        """处理玩家投票（轮流投票机制）"""
        game_state = await self._get_game_state(game_id)
        if not game_state:
            raise ValueError("游戏不存在")

        if game_state.current_phase != GamePhase.VOTING:
            raise ValueError("当前不是投票阶段")

        # 检查是否是当前投票者的回合
        if game_state.current_voter and game_state.current_voter != voter_id:
            raise ValueError(f"现在是 {game_state.current_voter_username} 的投票回合")

        # 检查投票者是否存活
        voter = next((p for p in game_state.players if p.id == voter_id), None)
        if not voter or not voter.is_alive:
            raise ValueError("投票者不存在或已被淘汰")

        # 检查被投票者是否存活
        target = next((p for p in game_state.players if p.id == vote_create.target_id), None)
        if not target or not target.is_alive:
            raise ValueError("被投票者不存在或已被淘汰")

        if voter_id == vote_create.target_id:
            raise ValueError("不能投票给自己")

        # 获取或创建投票者的参与者记录
        voter_participant_id = await self._ensure_participant_exists(game_id, voter_id)
        if not voter_participant_id:
            raise ValueError("无法创建投票者参与者记录")

        # 获取或创建被投票者的参与者记录
        target_participant_id = await self._ensure_participant_exists(game_id, vote_create.target_id)
        if not target_participant_id:
            raise ValueError("无法创建被投票者参与者记录")

        # 检查是否已经投过票（使用 participant_id）
        from sqlalchemy import select
        stmt = select(Vote).filter(
            and_(
                Vote.game_id == game_id,
                Vote.voter_id == voter_participant_id,
                Vote.round_number == game_state.round_number
            )
        )
        result = await self.db.execute(stmt)
        existing_vote = result.scalar_one_or_none()

        if existing_vote:
            # 更新投票
            existing_vote.target_id = target_participant_id
        else:
            # 创建新投票
            vote = Vote(
                id=str(uuid.uuid4()),
                game_id=game_id,
                voter_id=voter_participant_id,
                target_id=target_participant_id,
                round_number=game_state.round_number
            )
            self.db.add(vote)

        await self.db.commit()

        # 记录投票到游戏记录
        await self.game_recorder.record_vote(
            game_id=game_id,
            voter_id=voter_id,
            vote_data={
                "target_id": vote_create.target_id,
                "round_number": game_state.round_number
            }
        )

        # 切换到下一个投票者
        await self._next_voter(game_state)

        # 检查是否所有存活玩家都已投票
        if await self._all_players_voted(game_id, game_state):
            # 统计投票结果
            vote_result = await self._count_votes(game_id, game_state)

            # 处理淘汰
            if vote_result.is_eliminated:
                await self._eliminate_player(game_state, vote_result.target_id, vote_result)

            # 检查游戏是否结束
            if game_state.is_game_over:
                await self._end_game(game_state)
            else:
                # 进入下一轮
                await self._next_round(game_state)

        # 更新缓存
        await self._cache_game_state(game_state)

        return game_state
    
    async def _select_word_pair(self, word_pair_id: Optional[str], 
                               difficulty: Optional[int], 
                               category: Optional[str]) -> Optional[WordPair]:
        """选择词汇对"""
        from sqlalchemy import select
        
        if word_pair_id:
            stmt = select(WordPair).filter(WordPair.id == word_pair_id)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        
        stmt = select(WordPair)
        
        if difficulty:
            stmt = stmt.filter(WordPair.difficulty == difficulty)
        
        if category:
            stmt = stmt.filter(WordPair.category == category)
        
        result = await self.db.execute(stmt)
        word_pairs = result.scalars().all()
        
        if not word_pairs:
            # 如果没有找到，返回任意一个
            stmt = select(WordPair)
            result = await self.db.execute(stmt)
            word_pairs = result.scalars().all()
        
        return random.choice(word_pairs) if word_pairs else None
    
    async def _assign_roles(self, players: List[User], word_pair: WordPair, ai_players: List[AIPlayer] = None) -> List[GamePlayer]:
        """分配角色和词汇（包括AI玩家）"""
        all_players = players.copy()
        total_count = len(players) + (len(ai_players) if ai_players else 0)
        
        # 计算卧底数量 (通常是玩家总数的1/3，至少1个)
        undercover_count = max(1, total_count // 3)
        
        # 创建所有玩家的游戏对象
        game_players = []
        
        # 添加真人玩家
        for user in players:
            game_player = GamePlayer(
                id=user.id,
                username=user.username,
                role=PlayerRole.CIVILIAN,  # 临时设置，后面会重新分配
                word="",  # 临时设置，后面会重新分配
                is_ai=False,
                is_alive=True,
                is_ready=True  # 房主创建游戏时，所有真人玩家默认准备就绪
            )
            game_players.append(game_player)
        
        # 添加AI玩家
        if ai_players:
            for ai_player in ai_players:
                game_player = GamePlayer(
                    id=ai_player.id,
                    username=ai_player.name,
                    role=PlayerRole.CIVILIAN,  # 临时设置，后面会重新分配
                    word="",  # 临时设置，后面会重新分配
                    is_ai=True,
                    is_alive=True,
                    is_ready=True  # AI玩家默认准备就绪
                )
                game_players.append(game_player)
        
        # 随机分配角色
        random.shuffle(game_players)
        
        for i, game_player in enumerate(game_players):
            is_undercover = i < undercover_count
            role = PlayerRole.UNDERCOVER if is_undercover else PlayerRole.CIVILIAN
            word = word_pair.get_word_for_role(role.value)
            
            game_player.role = role
            game_player.word = word
        
        return game_players

    async def _create_participants(self, game_id: str, game_players: List[GamePlayer]):
        """为游戏创建参与者记录（用于发言和投票的外键）"""
        for game_player in game_players:
            participant = Participant(
                id=str(uuid.uuid4()),
                game_id=game_id,
                player_id=game_player.id,
                username=game_player.username,
                is_ai=game_player.is_ai,
                role=game_player.role,
                word=game_player.word,
                is_alive=game_player.is_alive,
                is_ready=game_player.is_ready
            )
            self.db.add(participant)

        await self.db.commit()
        logger.info(f"Created {len(game_players)} participants for game {game_id}")

    async def _get_participant_id(self, game_id: str, player_id: str) -> Optional[str]:
        """根据玩家ID获取参与者ID"""
        from sqlalchemy import select
        stmt = select(Participant).filter(
            and_(
                Participant.game_id == game_id,
                Participant.player_id == player_id
            )
        )
        result = await self.db.execute(stmt)
        participant = result.scalar_one_or_none()
        return participant.id if participant else None

    async def _ensure_participant_exists(self, game_id: str, player_id: str) -> Optional[str]:
        """确保参与者记录存在，如果不存在则从游戏状态创建"""
        try:
            participant_id = await self._get_participant_id(game_id, player_id)
            if participant_id:
                return participant_id

            # 参与者不存在，尝试从游戏状态创建
            logger.warning(f"Participant not found for player {player_id} in game {game_id}, creating...")

            # 首先检查游戏是否仍然存在于数据库中
            from sqlalchemy import select
            stmt = select(Game).where(Game.id == game_id)
            result = await self.db.execute(stmt)
            db_game = result.scalar_one_or_none()
            if not db_game:
                logger.error(f"Game {game_id} no longer exists in database, cannot create participant")
                return None

            game_state = await self._get_game_state(game_id)
            if not game_state:
                return None

            game_player = next((p for p in game_state.players if p.id == player_id), None)
            if not game_player:
                return None

            participant = Participant(
                id=str(uuid.uuid4()),
                game_id=game_id,
                player_id=player_id,
                username=game_player.username,
                is_ai=game_player.is_ai,
                role=game_player.role,
                word=game_player.word,
                is_alive=game_player.is_alive,
                is_ready=game_player.is_ready
            )
            self.db.add(participant)
            await self.db.commit()
            logger.info(f"Created participant {participant.id} for player {player_id}")
            return participant.id
        except Exception as e:
            logger.error(f"Failed to ensure participant exists for player {player_id} in game {game_id}: {e}")
            # 回滚事务以避免脏数据
            await self.db.rollback()
            return None

    async def _create_ai_player_instances(self, game_id: str, game_players: List[GamePlayer], ai_players: List[AIPlayer]):
        """为AI玩家创建游戏实例"""
        for ai_player in ai_players:
            # 找到对应的游戏玩家信息
            game_player = next((gp for gp in game_players if gp.id == ai_player.id), None)
            if game_player:
                await self.ai_player_service.create_ai_player_instance(
                    ai_player=ai_player,
                    game_id=game_id,
                    role=game_player.role,
                    word=game_player.word
                )
    
    async def handle_ai_speech(self, game_id: str, ai_player_id: str) -> Optional[str]:
        """处理AI玩家发言"""
        try:
            logger.info(f"[AI_SPEECH] Starting handle_ai_speech for {ai_player_id} in game {game_id}")

            # 获取AI玩家实例
            ai_instance = await self.ai_player_service.get_ai_player_instance(game_id, ai_player_id)
            logger.info(f"[AI_SPEECH] AI instance from cache: {ai_instance.name if ai_instance else 'None'}")

            # 如果实例不存在，尝试从游戏状态重建
            if not ai_instance:
                logger.warning(f"[AI_SPEECH] AI player instance not found, attempting to rebuild: {ai_player_id}")
                ai_instance = await self._rebuild_ai_instance(game_id, ai_player_id)
                if not ai_instance:
                    logger.error(f"[AI_SPEECH] Failed to rebuild AI player instance: {ai_player_id}")
                    return None
                logger.info(f"[AI_SPEECH] AI instance rebuilt successfully: {ai_instance.name}")

            # 获取游戏状态
            game_state = await self._get_game_state(game_id)
            if not game_state:
                logger.error(f"[AI_SPEECH] Game state not found: {game_id}")
                return None

            # 构建游戏上下文
            logger.info(f"[AI_SPEECH] Building game context...")
            game_context = await self._build_ai_game_context(game_state)
            logger.info(f"[AI_SPEECH] Game context built, round={game_context.get('round_number', 'N/A')}")

            # 生成AI发言
            logger.info(f"[AI_SPEECH] Generating speech for {ai_instance.name}...")
            speech_content = await ai_instance.generate_speech(game_context)
            logger.info(f"[AI_SPEECH] Speech generated: {speech_content[:50] if speech_content else 'None'}...")

            # 如果发言为空或太短，使用 Kimi 重试
            if not speech_content or len(speech_content.strip()) < 5:
                logger.warning(f"[AI_SPEECH] Primary model failed or returned empty, retrying with Kimi...")
                speech_content = await self._generate_speech_with_kimi(game_context, ai_instance)

            if speech_content:
                # 创建发言记录，如果验证失败则用 Kimi 重试
                try:
                    speech_create = SpeechCreate(content=speech_content)
                except Exception as validation_error:
                    logger.warning(f"[AI_SPEECH] Speech validation failed for {ai_instance.name}: {validation_error}")
                    logger.warning(f"[AI_SPEECH] Original speech that failed validation: {speech_content[:100]}...")
                    # 用 Kimi 重试一次
                    speech_content = await self._generate_speech_with_kimi(game_context, ai_instance)
                    if speech_content:
                        try:
                            speech_create = SpeechCreate(content=speech_content)
                        except:
                            # 如果还是失败，使用简单发言
                            speech_content = "这个词让我想到了很多有趣的事情。"
                            speech_create = SpeechCreate(content=speech_content)
                    else:
                        speech_content = "这个词让我想到了很多有趣的事情。"
                        speech_create = SpeechCreate(content=speech_content)

                await self.handle_speech(game_id, ai_player_id, speech_create)

                logger.info(f"[AI_SPEECH] AI player {ai_instance.ai_player.name} made speech: {speech_content[:50]}...")
                return speech_content

            logger.warning(f"[AI_SPEECH] No speech content generated for {ai_player_id}, using simple fallback")
            # 最后的兜底
            fallback_content = "这个词让我想到了很多有趣的事情。"
            speech_create = SpeechCreate(content=fallback_content)
            await self.handle_speech(game_id, ai_player_id, speech_create)
            return fallback_content

        except Exception as e:
            logger.error(f"[AI_SPEECH] Failed to handle AI speech for {ai_player_id}: {e}", exc_info=True)
            # 即使出错也要发言，使用默认发言避免游戏卡住
            try:
                fallback_content = "这个词让我想到了很多有趣的事情。"
                speech_create = SpeechCreate(content=fallback_content)
                await self.handle_speech(game_id, ai_player_id, speech_create)
                logger.info(f"[AI_SPEECH] Used fallback speech for {ai_player_id} due to error")
                return fallback_content
            except Exception as fallback_error:
                logger.error(f"[AI_SPEECH] Even fallback failed for {ai_player_id}: {fallback_error}")
                return None

    async def _generate_speech_with_kimi(self, game_context: Dict, ai_instance) -> Optional[str]:
        """使用 Kimi 模型生成发言（作为后备）"""
        try:
            from app.services.llm import llm_service
            from app.core.config import settings

            # 使用 Kimi 模型
            speech = await llm_service.generate_ai_speech(
                role=ai_instance.role.value if ai_instance.role else "civilian",
                word=ai_instance.word or "",
                context=game_context,
                personality=ai_instance.ai_player.personality.value if ai_instance.ai_player else "normal",
                difficulty=ai_instance.ai_player.difficulty.value if ai_instance.ai_player else "normal",
                model="moonshotai/kimi-k2-instruct",  # Kimi 模型
                api_base_url=settings.OPENROUTER_API_BASE,
                api_key=settings.OPENROUTER_API_KEY
            )
            if speech and len(speech.strip()) >= 5:
                logger.info(f"[AI_SPEECH] Kimi fallback generated speech: {speech[:50]}...")
                return speech
            return None
        except Exception as e:
            logger.error(f"[AI_SPEECH] Kimi fallback failed: {e}")
            return None
    
    async def handle_ai_vote(self, game_id: str, ai_player_id: str, available_targets: List[str]) -> Optional[str]:
        """处理AI玩家投票"""
        try:
            # 获取AI玩家实例
            ai_instance = await self.ai_player_service.get_ai_player_instance(game_id, ai_player_id)

            # 如果实例不存在，尝试从游戏状态重建
            if not ai_instance:
                logger.warning(f"AI player instance not found for vote, attempting to rebuild: {ai_player_id}")
                ai_instance = await self._rebuild_ai_instance(game_id, ai_player_id)
                if not ai_instance:
                    logger.error(f"Failed to rebuild AI player instance for vote: {ai_player_id}")
                    # 实例重建失败，随机投票
                    import random
                    vote_target = random.choice(available_targets)
                    vote_create = VoteCreate(target_id=vote_target)
                    await self.handle_vote(game_id, ai_player_id, vote_create)
                    logger.info(f"[AI_VOTE] Used random vote for {ai_player_id}: {vote_target}")
                    return vote_target

            # 获取游戏状态
            game_state = await self._get_game_state(game_id)
            if not game_state:
                import random
                vote_target = random.choice(available_targets)
                vote_create = VoteCreate(target_id=vote_target)
                await self.handle_vote(game_id, ai_player_id, vote_create)
                return vote_target

            # 构建游戏上下文
            game_context = await self._build_ai_game_context(game_state)

            # 生成AI投票决策
            vote_target = await ai_instance.make_vote_decision(game_context, available_targets)

            # 如果主模型失败，使用 Kimi 重试
            if not vote_target or vote_target not in available_targets:
                logger.warning(f"[AI_VOTE] Primary model failed, retrying with Kimi...")
                vote_target = await self._generate_vote_with_kimi(game_context, available_targets, ai_instance)

            # 如果还是失败，随机选择
            if not vote_target or vote_target not in available_targets:
                import random
                vote_target = random.choice(available_targets)
                logger.warning(f"[AI_VOTE] All models failed, using random vote: {vote_target}")

            # 重新检查游戏状态，确保仍在投票阶段（防止长时间网络请求导致状态过期）
            current_state = await self._get_game_state(game_id)
            if not current_state or current_state.current_phase != GamePhase.VOTING:
                logger.warning(f"[AI_VOTE] Game {game_id} is no longer in VOTING phase, skipping vote for {ai_player_id}")
                return None

            # 创建投票记录
            vote_create = VoteCreate(target_id=vote_target)
            await self.handle_vote(game_id, ai_player_id, vote_create)

            logger.info(f"AI player {ai_instance.ai_player.name if ai_instance else ai_player_id} voted for: {vote_target}")
            return vote_target

        except Exception as e:
            logger.error(f"Failed to handle AI vote for {ai_player_id}: {e}", exc_info=True)
            # 即使出错也要投票，使用随机投票避免游戏卡住
            try:
                # 先检查游戏是否仍在投票阶段
                current_state = await self._get_game_state(game_id)
                if not current_state or current_state.current_phase != GamePhase.VOTING:
                    logger.warning(f"[AI_VOTE] Game {game_id} is no longer in VOTING phase, skipping fallback vote")
                    return None

                import random
                vote_target = random.choice(available_targets)
                vote_create = VoteCreate(target_id=vote_target)
                await self.handle_vote(game_id, ai_player_id, vote_create)
                logger.info(f"[AI_VOTE] Used random fallback vote for {ai_player_id}: {vote_target}")
                return vote_target
            except Exception as fallback_error:
                logger.error(f"[AI_VOTE] Even fallback vote failed for {ai_player_id}: {fallback_error}")
                return None

    async def _generate_vote_with_kimi(self, game_context: Dict, available_targets: List[str], ai_instance) -> Optional[str]:
        """使用 Kimi 模型生成投票决策（作为后备）"""
        try:
            from app.services.llm import llm_service
            from app.core.config import settings

            # 使用 Kimi 模型
            vote_target = await llm_service.generate_ai_vote(
                role=ai_instance.role.value if ai_instance and ai_instance.role else "civilian",
                game_context=game_context,
                available_targets=available_targets,
                personality=ai_instance.ai_player.personality.value if ai_instance and ai_instance.ai_player else "normal",
                difficulty=ai_instance.ai_player.difficulty.value if ai_instance and ai_instance.ai_player else "normal",
                model="moonshotai/kimi-k2-instruct",  # Kimi 模型
                api_base_url=settings.OPENROUTER_API_BASE,
                api_key=settings.OPENROUTER_API_KEY
            )
            if vote_target and vote_target in available_targets:
                logger.info(f"[AI_VOTE] Kimi fallback generated vote: {vote_target}")
                return vote_target
            return None
        except Exception as e:
            logger.error(f"[AI_VOTE] Kimi fallback failed: {e}")
            return None

    async def _rebuild_ai_instance(self, game_id: str, ai_player_id: str) -> Optional[AIPlayerInstance]:
        """从游戏状态重建 AI 玩家实例（用于恢复场景）"""
        try:
            from app.models.ai_player import AIPlayer, AIDifficulty, AIPersonality

            logger.info(f"[REBUILD_AI] Starting rebuild for {ai_player_id} in game {game_id}")

            # 获取游戏状态
            game_state = await self._get_game_state(game_id)
            if not game_state:
                logger.error(f"[REBUILD_AI] Cannot rebuild AI instance: game state not found for {game_id}")
                return None

            logger.info(f"[REBUILD_AI] Game state found, {len(game_state.players)} players")

            # 从游戏状态中找到 AI 玩家信息
            game_player = next(
                (p for p in game_state.players if p.id == ai_player_id and p.is_ai),
                None
            )
            if not game_player:
                logger.error(f"[REBUILD_AI] Cannot rebuild AI instance: player not found or not AI: {ai_player_id}")
                logger.info(f"[REBUILD_AI] Available players: {[(p.id, p.username, p.is_ai) for p in game_state.players]}")
                return None

            logger.info(f"[REBUILD_AI] Found AI player: {game_player.username}, role={game_player.role}, word={game_player.word[:10]}...")

            # 尝试从数据库获取 AI 玩家记录
            ai_player = await self.ai_player_service.get_ai_player(ai_player_id)
            logger.info(f"[REBUILD_AI] AI player from DB: {ai_player.name if ai_player else 'None'}")

            # 如果数据库中没有，创建一个临时的 AI 玩家对象
            if not ai_player:
                logger.warning(f"[REBUILD_AI] AI player not found in database, creating temporary: {ai_player_id}")
                ai_player = AIPlayer(
                    id=ai_player_id,
                    name=game_player.username,
                    difficulty=AIDifficulty.MEDIUM,
                    personality=AIPersonality.BALANCED,
                    is_active=True
                )

            # 创建 AI 实例
            instance = AIPlayerInstance(
                ai_player=ai_player,
                game_id=game_id,
                role=game_player.role,
                word=game_player.word
            )
            instance.is_alive = game_player.is_alive

            # 缓存到内存和 Redis
            if game_id not in self.ai_player_service._instances:
                self.ai_player_service._instances[game_id] = {}
            self.ai_player_service._instances[game_id][ai_player_id] = instance

            logger.info(f"[REBUILD_AI] Successfully rebuilt AI player instance: {ai_player_id} for game {game_id}")
            return instance

        except Exception as e:
            logger.error(f"[REBUILD_AI] Failed to rebuild AI instance: {e}", exc_info=True)
            return None

    async def _build_ai_game_context(self, game_state: GameState) -> Dict[str, Any]:
        """构建AI玩家的游戏上下文"""
        # 获取发言记录
        speeches = await self.get_speeches(game_state.id)
        speech_data = []
        for speech in speeches:
            speech_data.append({
                "player_id": speech.participant_id,
                "player_name": speech.participant.username if hasattr(speech, 'participant') and speech.participant else "Unknown",
                "content": speech.content,
                "round_number": speech.round_number,
                "speech_order": speech.speech_order
            })
        
        # 获取投票记录
        votes = await self.get_votes(game_state.id)
        vote_data = []
        for vote in votes:
            vote_data.append({
                "voter_id": vote.voter_id,
                "target_id": vote.target_id,
                "round_number": vote.round_number
            })
        
        # 构建上下文
        context = {
            "game_id": game_state.id,
            "round_number": game_state.round_number,
            "current_phase": game_state.current_phase.value,
            "alive_players": [
                {
                    "id": p.id,
                    "username": p.username,
                    "is_ai": p.is_ai
                }
                for p in game_state.alive_players
            ],
            "speeches": speech_data,
            "votes": vote_data,
            "is_final_round": len(game_state.alive_players) <= 4  # 简单判断是否接近结束
        }
        
        return context
    
    async def process_ai_turns(self, game_id: str) -> bool:
        """处理AI玩家的回合（包括连续多个AI玩家）"""
        try:
            logger.info(f"[AI_TURNS] Getting game state for {game_id}")
            game_state = await self._get_game_state(game_id)
            if not game_state:
                logger.warning(f"[AI_TURNS] Game state not found for {game_id}")
                return False

            logger.info(f"[AI_TURNS] Game phase: {game_state.current_phase}, speaker: {game_state.current_speaker}")

            # 检查当前是否轮到AI玩家
            if game_state.current_phase == GamePhase.SPEAKING and game_state.current_speaker:
                processed_any = False
                max_iterations = 20  # 防止无限循环

                # 循环处理连续的 AI 玩家
                for _ in range(max_iterations):
                    # 重新获取最新的游戏状态
                    game_state = await self._get_game_state(game_id)
                    if not game_state:
                        break

                    if game_state.current_phase != GamePhase.SPEAKING:
                        logger.info(f"[AI_TURNS] Phase changed to {game_state.current_phase}, stopping speech loop")
                        # 如果进入投票阶段，跳出循环后处理投票
                        break

                    if not game_state.current_speaker:
                        break

                    current_player = next(
                        (p for p in game_state.players if p.id == game_state.current_speaker),
                        None
                    )

                    logger.info(f"[AI_TURNS] Current player: {current_player.username if current_player else 'None'}, is_ai: {current_player.is_ai if current_player else 'N/A'}")

                    if not current_player or not current_player.is_ai:
                        logger.info(f"[AI_TURNS] Current player is not AI, stopping AI turns")
                        break

                    # 处理AI发言
                    logger.info(f"[AI_TURNS] Handling AI speech for {current_player.username}")
                    speech = await self.handle_ai_speech(game_id, current_player.id)
                    logger.info(f"[AI_TURNS] AI speech result: {speech[:50] if speech else 'None'}...")

                    if speech:
                        processed_any = True
                        # 广播 AI 发言
                        from app.websocket.connection_manager import connection_manager
                        logger.info(f"[AI_TURNS] Broadcasting ai_speech to room {game_state.room_id}")
                        sent_count = await connection_manager.broadcast_to_room(game_state.room_id, {
                            "type": "ai_speech",
                            "data": {
                                "game_id": game_id,
                                "player_id": current_player.id,
                                "player_name": current_player.username,
                                "content": speech,
                                "round_number": game_state.round_number
                            }
                        })
                        logger.info(f"[AI_TURNS] Broadcast ai_speech sent to {sent_count} users")
                        # 短暂延迟，让客户端有时间处理
                        import asyncio
                        await asyncio.sleep(1)
                    else:
                        logger.warning(f"[AI_TURNS] AI speech failed for {current_player.username}")
                        break

                # 发言循环结束后，检查是否需要处理投票
                game_state = await self._get_game_state(game_id)
                if game_state and game_state.current_phase == GamePhase.VOTING:
                    logger.info(f"[AI_TURNS] Speech phase ended, now processing AI votes")
                    return await self._process_ai_voting(game_id, game_state)

                return processed_any

            elif game_state.current_phase == GamePhase.VOTING:
                # 处理所有AI玩家的投票
                ai_players = [p for p in game_state.alive_players if p.is_ai]
                # AI 可以投票给任何存活玩家（包括其他 AI，但不包括自己）
                available_targets = [p.id for p in game_state.alive_players]

                success_count = 0
                for ai_player in ai_players:
                    # 检查是否已经投票
                    has_voted = await self._has_ai_voted(game_id, ai_player.id, game_state.round_number)
                    if not has_voted:
                        vote_target = await self.handle_ai_vote(game_id, ai_player.id, available_targets)
                        if vote_target:
                            success_count += 1
                            # 广播 AI 投票
                            from app.websocket.connection_manager import connection_manager
                            await connection_manager.broadcast_to_room(game_state.room_id, {
                                "type": "ai_vote",
                                "data": {
                                    "game_id": game_id,
                                    "voter_id": ai_player.id,
                                    "voter_name": ai_player.username,
                                    "target_id": vote_target,
                                    "round_number": game_state.round_number,
                                    "is_ai": True
                                }
                            })

                return success_count > 0

            return False

        except Exception as e:
            logger.error(f"Failed to process AI turns for game {game_id}: {e}")
            return False

    async def _process_ai_voting(self, game_id: str, game_state: GameState) -> bool:
        """处理所有 AI 玩家的投票"""
        try:
            ai_players = [p for p in game_state.alive_players if p.is_ai]
            # AI 可以投票给任何存活玩家（包括其他 AI，但不包括自己）
            available_targets = [p.id for p in game_state.alive_players]

            logger.info(f"[AI_VOTING] Processing votes for {len(ai_players)} AI players")

            success_count = 0
            for ai_player in ai_players:
                # 每个 AI 只能投给除自己以外的玩家
                targets_for_this_ai = [t for t in available_targets if t != ai_player.id]
                if not targets_for_this_ai:
                    continue

                # 检查是否已经投票
                has_voted = await self._has_ai_voted(game_id, ai_player.id, game_state.round_number)
                if has_voted:
                    logger.info(f"[AI_VOTING] AI player {ai_player.username} has already voted")
                    continue

                logger.info(f"[AI_VOTING] Processing vote for AI player {ai_player.username}")
                vote_target = await self.handle_ai_vote(game_id, ai_player.id, targets_for_this_ai)
                if vote_target:
                    success_count += 1
                    # 广播 AI 投票
                    from app.websocket.connection_manager import connection_manager
                    await connection_manager.broadcast_to_room(game_state.room_id, {
                        "type": "ai_vote",
                        "data": {
                            "game_id": game_id,
                            "voter_id": ai_player.id,
                            "voter_name": ai_player.username,
                            "target_id": vote_target,
                            "round_number": game_state.round_number,
                            "is_ai": True
                        }
                    })
                    logger.info(f"[AI_VOTING] AI player {ai_player.username} voted for {vote_target}")
                    # 短暂延迟
                    import asyncio
                    await asyncio.sleep(0.5)
                else:
                    logger.warning(f"[AI_VOTING] AI player {ai_player.username} failed to vote")

            logger.info(f"[AI_VOTING] Completed with {success_count}/{len(ai_players)} successful votes")

            # 投票完成后，检查是否进入新一轮，如果第一个发言者是 AI，需要继续处理
            updated_state = await self._get_game_state(game_id)
            if updated_state and updated_state.current_phase == GamePhase.SPEAKING:
                first_speaker = next(
                    (p for p in updated_state.players if p.id == updated_state.current_speaker),
                    None
                )
                if first_speaker and first_speaker.is_ai:
                    logger.info(f"[AI_VOTING] New round started, first speaker {first_speaker.username} is AI")
                    # 短暂延迟后继续处理 AI 发言
                    import asyncio
                    await asyncio.sleep(2.0)
                    # 递归调用 process_ai_turns 来处理新一轮的 AI 发言
                    return await self.process_ai_turns(game_id)

            return success_count > 0

        except Exception as e:
            logger.error(f"[AI_VOTING] Failed to process AI voting: {e}", exc_info=True)
            return False

    async def _has_ai_voted(self, game_id: str, ai_player_id: str, round_number: int) -> bool:
        """检查AI玩家是否已投票"""
        # 先获取 AI 玩家的 participant_id
        participant_id = await self._get_participant_id(game_id, ai_player_id)
        if not participant_id:
            return False

        from sqlalchemy import select
        stmt = select(Vote).filter(
            and_(
                Vote.game_id == game_id,
                Vote.voter_id == participant_id,
                Vote.round_number == round_number
            )
        )
        result = await self.db.execute(stmt)
        vote = result.scalar_one_or_none()
        return vote is not None
    
    async def _get_game_state(self, game_id: str) -> Optional[GameState]:
        """获取游戏状态"""
        # 先从Redis缓存获取
        redis = await self._get_redis()
        cached_state = await redis.get(f"game_state:{game_id}")
        if cached_state:
            return GameState.model_validate_json(cached_state)
        
        # 从数据库获取
        from sqlalchemy import select
        stmt = select(Game).filter(Game.id == game_id)
        result = await self.db.execute(stmt)
        game = result.scalar_one_or_none()
        
        if not game:
            return None
        
        # 构建游戏状态
        players = [GamePlayer(**player_data) for player_data in game.players]
        
        game_state = GameState(
            id=game.id,
            room_id=game.room_id,
            word_pair_id=game.word_pair_id,
            current_phase=game.current_phase,
            current_speaker=game.current_speaker,
            round_number=game.round_number,
            players=players,
            eliminated_players=game.eliminated_players or [],
            winner_role=game.winner_role,
            winner_players=game.winner_players,
            started_at=game.started_at,
            finished_at=game.finished_at
        )
        
        # 缓存到Redis
        await self._cache_game_state(game_state)
        
        return game_state
    
    async def _cache_game_state(self, game_state: GameState):
        """缓存游戏状态到Redis"""
        redis = await self._get_redis()
        await redis.setex(
            f"game_state:{game_state.id}",
            3600,  # 1小时过期
            game_state.model_dump_json()
        )
    
    async def _update_game_in_db(self, game_state: GameState):
        """更新数据库中的游戏状态"""
        from sqlalchemy import select
        stmt = select(Game).filter(Game.id == game_state.id)
        result = await self.db.execute(stmt)
        game = result.scalar_one_or_none()
        
        if game:
            game.current_phase = game_state.current_phase
            game.current_speaker = game_state.current_speaker
            game.round_number = game_state.round_number
            game.players = [player.model_dump() for player in game_state.players]
            game.eliminated_players = game_state.eliminated_players
            game.winner_role = game_state.winner_role
            game.winner_players = game_state.winner_players
            game.finished_at = game_state.finished_at
            
            await self.db.commit()
            
            # 同时更新缓存
            await self._cache_game_state(game_state)
    
    async def _get_next_speech_order(self, game_id: str, round_number: int) -> int:
        """获取下一个发言顺序号"""
        from sqlalchemy import select
        stmt = select(func.max(Speech.speech_order)).filter(
            and_(Speech.game_id == game_id, Speech.round_number == round_number)
        )
        result = await self.db.execute(stmt)
        max_order = result.scalar()
        
        return (max_order or 0) + 1
    
    async def _next_speaker(self, game_state: GameState):
        """切换到下一个发言者"""
        alive_players = game_state.alive_players
        if not alive_players:
            return
        
        current_index = next(
            (i for i, p in enumerate(alive_players) if p.id == game_state.current_speaker),
            -1
        )
        
        next_index = (current_index + 1) % len(alive_players)
        
        # 如果回到第一个玩家，说明本轮发言结束，进入投票阶段
        if next_index == 0 and current_index >= 0:
            game_state.current_phase = GamePhase.VOTING
            game_state.current_speaker = None
            # 设置第一个投票者
            game_state.current_voter = alive_players[0].id
            game_state.current_voter_username = alive_players[0].username

            # 广播阶段变化
            await connection_manager.broadcast_to_room(game_state.room_id, {
                "type": "phase_changed",
                "data": {
                    "game_id": game_state.id,
                    "new_phase": "VOTING",
                    "old_phase": "SPEAKING",
                    "round_number": game_state.round_number,
                    "message": "发言阶段结束，进入投票阶段"
                }
            })
        else:
            game_state.current_speaker = alive_players[next_index].id
        
        await self._update_game_in_db(game_state)

    async def _next_voter(self, game_state: GameState) -> None:
        """切换到下一个投票者"""
        alive_players = game_state.alive_players

        if not alive_players:
            return

        # 找到当前投票者的索引
        current_index = next(
            (i for i, p in enumerate(alive_players) if p.id == game_state.current_voter),
            -1
        )

        next_index = (current_index + 1) % len(alive_players)

        # 如果回到第一个玩家，说明所有人都已投票，current_voter 设为 None
        if next_index == 0 and current_index >= 0:
            game_state.current_voter = None
            game_state.current_voter_username = None
        else:
            game_state.current_voter = alive_players[next_index].id
            game_state.current_voter_username = alive_players[next_index].username

        await self._update_game_in_db(game_state)

    async def _all_players_voted(self, game_id: str, game_state: GameState) -> bool:
        """检查是否所有存活玩家都已投票"""
        alive_player_ids = [p.id for p in game_state.alive_players]

        # 获取所有存活玩家的 participant_ids
        from sqlalchemy import select
        stmt = select(Participant.id).filter(
            and_(
                Participant.game_id == game_id,
                Participant.player_id.in_(alive_player_ids)
            )
        )
        result = await self.db.execute(stmt)
        participant_ids = [row[0] for row in result.fetchall()]

        from sqlalchemy import func
        stmt = select(func.count(Vote.id)).filter(
            and_(
                Vote.game_id == game_id,
                Vote.round_number == game_state.round_number,
                Vote.voter_id.in_(participant_ids)
            )
        )
        result = await self.db.execute(stmt)
        vote_count = result.scalar()

        return vote_count == len(alive_player_ids)
    
    async def _count_votes(self, game_id: str, game_state: GameState) -> VoteResult:
        """统计投票结果"""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        stmt = select(Vote).options(
            selectinload(Vote.target)
        ).filter(
            and_(
                Vote.game_id == game_id,
                Vote.round_number == game_state.round_number
            )
        )
        result = await self.db.execute(stmt)
        votes = result.scalars().all()

        # 统计每个玩家的得票数（使用 player_id）
        vote_counts = {}
        for vote in votes:
            if vote.target:
                player_id = vote.target.player_id
                vote_counts[player_id] = vote_counts.get(player_id, 0) + 1

        if not vote_counts:
            # 没有投票，随机淘汰一个玩家
            alive_players = game_state.alive_players
            target_player = random.choice(alive_players)
            return VoteResult(
                target_id=target_player.id,
                target_username=target_player.username,
                vote_count=0,
                is_eliminated=True,
                revealed_role=target_player.role
            )

        # 找到得票最多的玩家
        max_votes = max(vote_counts.values())
        candidates = [player_id for player_id, count in vote_counts.items() if count == max_votes]

        # 如果有平票，随机选择一个
        target_id = random.choice(candidates)
        target_player = next(p for p in game_state.players if p.id == target_id)
        
        return VoteResult(
            target_id=target_id,
            target_username=target_player.username,
            vote_count=max_votes,
            is_eliminated=True,
            revealed_role=target_player.role
        )
    
    async def _eliminate_player(self, game_state: GameState, player_id: str, vote_result: Optional[VoteResult] = None):
        """淘汰玩家"""
        eliminated_player = None
        for player in game_state.players:
            if player.id == player_id:
                player.is_alive = False
                eliminated_player = player
                break

        game_state.eliminated_players.append(player_id)
        await self._update_game_in_db(game_state)

        # 广播玩家被淘汰
        if eliminated_player:
            await connection_manager.broadcast_to_room(game_state.room_id, {
                "type": "player_eliminated",
                "data": {
                    "game_id": game_state.id,
                    "player_id": player_id,
                    "player_name": eliminated_player.username,
                    "is_ai": eliminated_player.is_ai,
                    "role": eliminated_player.role.value if eliminated_player.role else None,
                    "round_number": game_state.round_number,
                    "vote_count": vote_result.vote_count if vote_result else None
                }
            })
        
        # 记录淘汰到游戏记录
        if vote_result:
            await self.game_recorder.record_elimination(
                game_id=game_state.id,
                eliminated_player_id=player_id,
                elimination_data={
                    "round_number": game_state.round_number,
                    "vote_count": vote_result.vote_count,
                    "revealed_role": vote_result.revealed_role.value if vote_result.revealed_role else None
                }
            )
    
    async def _end_game(self, game_state: GameState):
        """结束游戏"""
        game_state.current_phase = GamePhase.FINISHED
        game_state.finished_at = datetime.utcnow()

        # 判断获胜方
        if game_state.undercover_count == 0:
            # 平民获胜
            game_state.winner_role = PlayerRole.CIVILIAN
            game_state.winner_players = [
                p.id for p in game_state.players
                if p.role == PlayerRole.CIVILIAN
            ]
        else:
            # 卧底获胜
            game_state.winner_role = PlayerRole.UNDERCOVER
            game_state.winner_players = [
                p.id for p in game_state.players
                if p.role == PlayerRole.UNDERCOVER
            ]

        await self._update_game_in_db(game_state)

        # 广播游戏结束
        await connection_manager.broadcast_to_room(game_state.room_id, {
            "type": "game_ended",
            "data": {
                "game_id": game_state.id,
                "winner_role": game_state.winner_role.value if game_state.winner_role else None,
                "winner_players": game_state.winner_players or [],
                "total_rounds": game_state.round_number,
                "players": [
                    {
                        "id": p.id,
                        "username": p.username,
                        "role": p.role.value if p.role else None,
                        "is_alive": p.is_alive,
                        "is_ai": p.is_ai
                    }
                    for p in game_state.players
                ]
            }
        })
        
        # 记录游戏结束
        duration_minutes = (
            (game_state.finished_at - game_state.started_at).total_seconds() / 60
            if game_state.finished_at else 0
        )
        await self.game_recorder.record_game_finish(
            game_id=game_state.id,
            finish_data={
                "winner_role": game_state.winner_role.value if game_state.winner_role else None,
                "winner_players": game_state.winner_players or [],
                "total_rounds": game_state.round_number,
                "duration_minutes": duration_minutes,
                "final_players": [
                    {
                        "id": p.id,
                        "username": p.username,
                        "role": p.role.value,
                        "is_alive": p.is_alive
                    }
                    for p in game_state.players
                ]
            }
        )
        
        # 自动触发积分结算
        try:
            from app.services.settlement import get_settlement_service
            settlement_service = get_settlement_service(self.db)
            await settlement_service.apply_settlement(game_state.id)
            logger.info(f"Settlement applied automatically for game {game_state.id}")
        except Exception as e:
            logger.error(f"Failed to apply settlement for game {game_state.id}: {e}")
            # 结算失败不应该影响游戏结束流程

        # 更新 AI 玩家统计
        try:
            ai_player_service = get_ai_player_service(self.db)
            for player in game_state.players:
                if player.is_ai:
                    # AI 玩家的 id 就是 AI 玩家模板的 id
                    is_winner = player.id in (game_state.winner_players or [])
                    await ai_player_service.update_ai_player_stats(
                        player.id,  # 使用 player.id，它就是 ai_player_id
                        game_won=is_winner
                    )
            logger.info(f"AI player stats updated for game {game_state.id}")
        except Exception as e:
            logger.error(f"Failed to update AI player stats for game {game_state.id}: {e}")
            # AI 统计更新失败不应该影响游戏结束流程
    
    async def check_game_end_conditions(self, game_id: str) -> Optional[Dict]:
        """检查游戏结束条件并返回结果"""
        game_state = await self._get_game_state(game_id)
        if not game_state:
            return None
        
        if not game_state.is_game_over:
            return None
        
        # 游戏结束，计算详细结果
        result = {
            'game_over': True,
            'winner_role': None,
            'winner_players': [],
            'reason': '',
            'final_stats': {
                'total_rounds': game_state.round_number,
                'total_players': len(game_state.players),
                'eliminated_players': len(game_state.eliminated_players),
                'surviving_players': len(game_state.alive_players)
            }
        }
        
        if game_state.undercover_count == 0:
            # 平民获胜 - 所有卧底被淘汰
            result['winner_role'] = PlayerRole.CIVILIAN
            result['winner_players'] = [
                p.id for p in game_state.players 
                if p.role == PlayerRole.CIVILIAN
            ]
            result['reason'] = '所有卧底已被淘汰，平民获胜'
        elif game_state.undercover_count >= game_state.civilian_count:
            # 卧底获胜 - 卧底数量大于等于平民数量
            result['winner_role'] = PlayerRole.UNDERCOVER
            result['winner_players'] = [
                p.id for p in game_state.players 
                if p.role == PlayerRole.UNDERCOVER
            ]
            result['reason'] = '卧底数量达到或超过平民数量，卧底获胜'
        
        return result
    
    async def force_end_game(self, game_id: str, reason: str = "游戏被强制结束") -> GameState:
        """强制结束游戏（管理员功能）"""
        game_state = await self._get_game_state(game_id)
        if not game_state:
            raise ValueError("游戏不存在")
        
        if game_state.current_phase == GamePhase.FINISHED:
            raise ValueError("游戏已经结束")
        
        # 强制结束游戏，不判断胜负
        game_state.current_phase = GamePhase.FINISHED
        game_state.finished_at = datetime.utcnow()
        
        # 记录强制结束的原因
        redis = await self._get_redis()
        await redis.set(f"game_end_reason:{game_id}", reason, ex=3600)
        
        await self._update_game_in_db(game_state)
        await self._cache_game_state(game_state)
        
        return game_state
    
    async def get_game_result(self, game_id: str) -> Optional[Dict]:
        """获取游戏结果详情"""
        game_state = await self._get_game_state(game_id)
        if not game_state or game_state.current_phase != GamePhase.FINISHED:
            return None
        
        # 检查是否是强制结束
        redis = await self._get_redis()
        forced_reason = await redis.get(f"game_end_reason:{game_id}")
        
        result = {
            'game_id': game_id,
            'started_at': game_state.started_at.isoformat(),
            'finished_at': game_state.finished_at.isoformat() if game_state.finished_at else None,
            'duration_minutes': (
                (game_state.finished_at - game_state.started_at).total_seconds() / 60
                if game_state.finished_at else None
            ),
            'total_rounds': game_state.round_number,
            'winner_role': game_state.winner_role.value if game_state.winner_role else None,
            'winner_players': game_state.winner_players or [],
            'forced_end': bool(forced_reason),
            'end_reason': (
                forced_reason.decode() if isinstance(forced_reason, bytes) 
                else forced_reason
            ) if forced_reason else None,
            'players': []
        }
        
        # 添加玩家详细信息
        for player in game_state.players:
            player_info = {
                'id': player.id,
                'username': player.username,
                'role': player.role.value,
                'word': player.word,
                'is_alive': player.is_alive,
                'is_winner': player.id in (game_state.winner_players or [])
            }
            result['players'].append(player_info)
        
        return result
    
    async def calculate_player_performance(self, game_id: str, player_id: str) -> Dict:
        """计算玩家在游戏中的表现"""
        game_state = await self._get_game_state(game_id)
        if not game_state:
            raise ValueError("游戏不存在")
        
        player = next((p for p in game_state.players if p.id == player_id), None)
        if not player:
            raise ValueError("玩家不在游戏中")
        
        # 获取玩家的发言记录
        speeches = await self.get_speeches(game_id)
        player_speeches = [s for s in speeches if s.participant and s.participant.player_id == player_id]

        # 获取玩家的投票记录
        votes = await self.get_votes(game_id)
        player_votes = [v for v in votes if v.voter and v.voter.player_id == player_id]
        votes_received = [v for v in votes if v.target and v.target.player_id == player_id]
        
        performance = {
            'player_id': player_id,
            'username': player.username,
            'role': player.role.value,
            'word': player.word,
            'is_alive': player.is_alive,
            'is_winner': player.id in (game_state.winner_players or []),
            'speeches_count': len(player_speeches),
            'votes_cast': len(player_votes),
            'votes_received': len(votes_received),
            'survival_rounds': game_state.round_number if player.is_alive else self._calculate_elimination_round(player_id, game_state),
            'performance_score': 0
        }
        
        # 计算表现分数
        base_score = 10 if performance['is_winner'] else 5
        speech_bonus = min(len(player_speeches) * 2, 10)  # 发言奖励，最多10分
        survival_bonus = performance['survival_rounds'] * 1  # 生存轮次奖励
        
        performance['performance_score'] = base_score + speech_bonus + survival_bonus
        
        return performance
    
    def _calculate_elimination_round(self, player_id: str, game_state: GameState) -> int:
        """计算玩家被淘汰的轮次"""
        # 简单实现，实际应该从游戏记录中获取
        if player_id in game_state.eliminated_players:
            # 假设按淘汰顺序分配轮次
            elimination_index = game_state.eliminated_players.index(player_id)
            return elimination_index + 1
        return game_state.round_number  # 如果还存活，返回当前轮次
    
    async def get_mvp_player(self, game_id: str) -> Optional[Dict]:
        """获取游戏MVP玩家"""
        game_state = await self._get_game_state(game_id)
        if not game_state or game_state.current_phase != GamePhase.FINISHED:
            return None
        
        # 计算所有玩家的表现
        performances = []
        for player in game_state.players:
            performance = await self.calculate_player_performance(game_id, player.id)
            performances.append(performance)
        
        # 找出表现最好的玩家
        if not performances:
            return None
        
        mvp = max(performances, key=lambda p: p['performance_score'])
        return mvp
    
    async def _next_round(self, game_state: GameState):
        """进入下一轮"""
        old_round = game_state.round_number
        game_state.round_number += 1
        game_state.current_phase = GamePhase.SPEAKING

        # 从第一个存活玩家开始发言
        alive_players = game_state.alive_players
        if alive_players:
            game_state.current_speaker = alive_players[0].id

        await self._update_game_in_db(game_state)

        # 广播新一轮开始
        await connection_manager.broadcast_to_room(game_state.room_id, {
            "type": "round_started",
            "data": {
                "game_id": game_state.id,
                "round_number": game_state.round_number,
                "old_round": old_round,
                "phase": "SPEAKING",
                "current_speaker": game_state.current_speaker,
                "alive_players": len(alive_players),
                "message": f"第 {game_state.round_number} 轮开始"
            }
        })
    
    async def skip_speech(self, game_id: str, player_id: str) -> GameState:
        """跳过发言"""
        game_state = await self._get_game_state(game_id)
        if not game_state:
            raise ValueError("游戏不存在")
        
        if game_state.current_phase != GamePhase.SPEAKING:
            raise ValueError("当前不是发言阶段")
        
        if game_state.current_speaker != player_id:
            raise ValueError("当前不是您的发言轮次")

        # 获取或创建参与者记录
        participant_id = await self._ensure_participant_exists(game_id, player_id)
        if not participant_id:
            raise ValueError("无法创建参与者记录")

        # 记录空发言
        speech = Speech(
            id=str(uuid.uuid4()),
            game_id=game_id,
            participant_id=participant_id,
            content="[跳过发言]",
            round_number=game_state.round_number,
            speech_order=await self._get_next_speech_order(game_id, game_state.round_number)
        )
        
        self.db.add(speech)
        await self.db.commit()
        
        # 切换到下一个发言者
        await self._next_speaker(game_state)
        
        # 更新缓存
        await self._cache_game_state(game_state)
        
        return game_state
    
    async def get_speeches(self, game_id: str, round_number: Optional[int] = None) -> List[Speech]:
        """获取发言记录"""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        stmt = select(Speech).options(selectinload(Speech.participant)).filter(Speech.game_id == game_id)

        if round_number:
            stmt = stmt.filter(Speech.round_number == round_number)

        stmt = stmt.order_by(Speech.round_number, Speech.speech_order)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_votes(self, game_id: str, round_number: Optional[int] = None) -> List[Vote]:
        """获取投票记录"""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        stmt = select(Vote).options(
            selectinload(Vote.voter),
            selectinload(Vote.target)
        ).filter(Vote.game_id == game_id)

        if round_number:
            stmt = stmt.filter(Vote.round_number == round_number)

        stmt = stmt.order_by(Vote.round_number, Vote.created_at)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_current_votes(self, game_id: str, round_number: int) -> Dict[str, int]:
        """获取当前轮次的投票统计"""
        votes = await self.get_votes(game_id, round_number)

        vote_counts = {}
        for vote in votes:
            if vote.target:
                target_player_id = vote.target.player_id
                vote_counts[target_player_id] = vote_counts.get(target_player_id, 0) + 1

        return vote_counts
    
    async def force_next_phase(self, game_id: str) -> GameState:
        """强制进入下一阶段（管理员功能）"""
        game_state = await self._get_game_state(game_id)
        if not game_state:
            raise ValueError("游戏不存在")
        
        if game_state.current_phase == GamePhase.SPEAKING:
            # 进入投票阶段
            game_state.current_phase = GamePhase.VOTING
            game_state.current_speaker = None
        elif game_state.current_phase == GamePhase.VOTING:
            # 统计投票并进入下一轮或结束游戏
            vote_result = await self._count_votes(game_id, game_state)
            
            if vote_result.is_eliminated:
                await self._eliminate_player(game_state, vote_result.target_id)
            
            if game_state.is_game_over:
                await self._end_game(game_state)
            else:
                await self._next_round(game_state)
        
        await self._cache_game_state(game_state)
        return game_state
    
    async def get_time_remaining(self, game_id: str) -> Optional[int]:
        """获取当前阶段剩余时间（秒）"""
        game_state = await self._get_game_state(game_id)
        if not game_state:
            return None
        
        # 简单实现，实际应该基于阶段开始时间计算
        if game_state.current_phase == GamePhase.SPEAKING:
            return 60  # 发言时间60秒
        elif game_state.current_phase == GamePhase.VOTING:
            return 30  # 投票时间30秒
        
        return None


class GameStateManager:
    """游戏状态管理器"""
    
    def __init__(self, db: Session):
        self.db = db
        self.redis = get_redis()
        self.game_engine = GameEngine(db)
    
    async def get_game_response(self, game_id: str, user_id: str) -> GameResponse:
        """获取游戏响应（包含用户特定信息）"""
        game_state = await self.game_engine._get_game_state(game_id)
        if not game_state:
            raise ValueError("游戏不存在")
        
        # 获取当前用户信息
        current_player = next((p for p in game_state.players if p.id == user_id), None)
        if not current_player:
            raise ValueError("用户不在游戏中")
        
        # 判断用户权限
        can_speak = (
            game_state.current_phase == GamePhase.SPEAKING and
            game_state.current_speaker == user_id and
            current_player.is_alive
        )
        
        can_vote = (
            game_state.current_phase == GamePhase.VOTING and
            current_player.is_alive and
            not await self._has_voted(game_id, user_id, game_state.round_number)
        )
        
        # 计算剩余时间
        time_remaining = await self.game_engine.get_time_remaining(game_id)
        
        return GameResponse(
            game=game_state,
            current_user_role=current_player.role if current_player else None,
            current_user_word=current_player.word if current_player else None,
            can_speak=can_speak,
            can_vote=can_vote,
            time_remaining=time_remaining
        )
    
    async def set_player_ready(self, game_id: str, user_id: str, ready: bool = True) -> GameState:
        """设置玩家准备状态"""
        game_state = await self.game_engine._get_game_state(game_id)
        if not game_state:
            raise ValueError("游戏不存在")
        
        if game_state.current_phase != GamePhase.PREPARING:
            raise ValueError("游戏已经开始，无法修改准备状态")
        
        # 更新玩家准备状态
        for player in game_state.players:
            if player.id == user_id:
                player.is_ready = ready
                break
        else:
            raise ValueError("用户不在游戏中")
        
        # 更新缓存和数据库
        await self.game_engine._cache_game_state(game_state)
        await self.game_engine._update_game_in_db(game_state)
        
        return game_state
    
    async def _has_voted(self, game_id: str, user_id: str, round_number: int) -> bool:
        """检查用户是否已投票"""
        from sqlalchemy import select
        stmt = select(Vote).filter(
            and_(
                Vote.game_id == game_id,
                Vote.voter_id == user_id,
                Vote.round_number == round_number
            )
        )
        result = await self.db.execute(stmt)
        vote = result.scalar_one_or_none()
        
        return vote is not None
    
    async def get_game_summary(self, game_id: str) -> Optional[Dict]:
        """获取游戏总结"""
        game_state = await self.game_engine._get_game_state(game_id)
        if not game_state or game_state.current_phase != GamePhase.FINISHED:
            return None
        
        # 获取所有发言和投票记录
        speeches = await self.game_engine.get_speeches(game_id)
        votes = await self.game_engine.get_votes(game_id)
        
        # 构建轮次总结
        rounds = {}
        for speech in speeches:
            round_num = speech.round_number
            if round_num not in rounds:
                rounds[round_num] = {
                    'speeches': [],
                    'votes': [],
                    'eliminated_player': None
                }
            rounds[round_num]['speeches'].append({
                'player_id': speech.participant_id,
                'player_username': speech.participant.username if speech.participant else "Unknown",
                'content': speech.content,
                'order': speech.speech_order
            })
        
        for vote in votes:
            round_num = vote.round_number
            if round_num in rounds:
                rounds[round_num]['votes'].append({
                    'voter_id': vote.voter_id,
                    'voter_username': vote.voter.username,
                    'target_id': vote.target_id,
                    'target_username': vote.target.username
                })
        
        return {
            'game_id': game_id,
            'players': [
                {
                    'id': p.id,
                    'username': p.username,
                    'role': p.role.value,
                    'word': p.word,
                    'is_alive': p.is_alive
                }
                for p in game_state.players
            ],
            'rounds': [
                {
                    'round_number': round_num,
                    'speeches': round_data['speeches'],
                    'votes': round_data['votes'],
                    'eliminated_player': round_data['eliminated_player']
                }
                for round_num, round_data in sorted(rounds.items())
            ],
            'winner_role': game_state.winner_role.value if game_state.winner_role else None,
            'winner_players': game_state.winner_players or [],
            'duration_minutes': (
                (game_state.finished_at - game_state.started_at).total_seconds() / 60
                if game_state.finished_at else None
            )
        }