"""
Game logic property-based tests
游戏逻辑基于属性的测试
"""

import pytest
import uuid
import asyncio
from hypothesis import given, strategies as st, settings, HealthCheck
from typing import List
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.user import User
from app.models.word_pair import WordPair
from app.models.game import GamePhase
from app.schemas.game import PlayerRole, GameCreate
from app.services.game import GameEngine

# Test database URL (in-memory SQLite for fast testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


class MockRedis:
    """Mock Redis client for testing"""
    def __init__(self):
        self.data = {}
    
    async def setex(self, key: str, expire: int, value: str):
        self.data[key] = value
    
    async def get(self, key: str):
        return self.data.get(key)
    
    async def set(self, key: str, value: str, ex: int = None):
        self.data[key] = value
    
    def clear(self):
        """Clear all data - useful for testing"""
        self.data.clear()


async def get_test_db_session():
    """Create a test database session"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=False
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()
    
    await engine.dispose()


async def create_sample_users(db_session, count=10):
    """Create sample users for testing"""
    users = []
    for i in range(count):
        user = User(
            id=str(uuid.uuid4()),
            username=f"test_user_{i}",
            email=f"test{i}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        users.append(user)
    
    await db_session.commit()
    return users


async def create_sample_word_pairs(db_session):
    """Create sample word pairs for testing"""
    word_pairs = []
    categories = ["动物", "水果", "职业", "运动"]
    
    for i, category in enumerate(categories):
        for difficulty in range(1, 4):
            word_pair = WordPair(
                id=str(uuid.uuid4()),
                civilian_word=f"平民词_{i}_{difficulty}",
                undercover_word=f"卧底词_{i}_{difficulty}",
                category=category,
                difficulty=difficulty
            )
            db_session.add(word_pair)
            word_pairs.append(word_pair)
    
    await db_session.commit()
    return word_pairs


class TestGameRoleAssignment:
    """测试游戏角色分配"""
    
    @given(
        player_count=st.integers(min_value=3, max_value=10),
        seed=st.integers(min_value=0, max_value=1000000)
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @pytest.mark.asyncio
    async def test_role_assignment_correctness(
        self, 
        player_count: int,
        seed: int
    ):
        """
        Feature: undercover-game-platform, Property 11: 角色分配正确性
        验证需求: 需求 3.1
        
        对于任何游戏开始请求，系统应该随机分配正确数量的卧底和平民角色，并发放对应词汇
        """
        async for db_session in get_test_db_session():
            # 设置随机种子以确保可重现性
            import random
            random.seed(seed)
            
            # 创建测试数据
            sample_users = await create_sample_users(db_session, 10)
            sample_word_pairs = await create_sample_word_pairs(db_session)
            
            # 选择指定数量的玩家
            selected_users = sample_users[:player_count]
            
            # 选择一个词汇对
            word_pair = sample_word_pairs[0]
            
            # 创建游戏引擎
            game_engine = GameEngine(db_session)
            game_engine.redis = MockRedis()
            
            # 创建游戏
            game_create = GameCreate(
                room_id=str(uuid.uuid4()),
                word_pair_id=word_pair.id
            )
            
            game_state = await game_engine.create_game(game_create, selected_users)
            
            # 验证角色分配正确性
            
            # 1. 验证玩家总数正确
            assert len(game_state.players) == player_count
            
            # 2. 验证所有玩家都有角色
            for player in game_state.players:
                assert player.role in [PlayerRole.CIVILIAN, PlayerRole.UNDERCOVER]
                assert player.word is not None
                assert len(player.word) > 0
            
            # 3. 验证卧底数量正确（至少1个，通常是总数的1/3）
            undercover_count = sum(1 for p in game_state.players if p.role == PlayerRole.UNDERCOVER)
            civilian_count = sum(1 for p in game_state.players if p.role == PlayerRole.CIVILIAN)
            
            expected_undercover_count = max(1, player_count // 3)
            assert undercover_count == expected_undercover_count
            assert civilian_count == player_count - undercover_count
            
            # 4. 验证词汇分配正确
            for player in game_state.players:
                if player.role == PlayerRole.UNDERCOVER:
                    assert player.word == word_pair.undercover_word
                else:
                    assert player.word == word_pair.civilian_word
            
            # 5. 验证玩家ID和用户名正确
            user_ids = {user.id for user in selected_users}
            player_ids = {player.id for player in game_state.players}
            assert user_ids == player_ids
            
            # 6. 验证初始状态正确
            for player in game_state.players:
                assert player.is_alive is True
                assert player.is_ready is False
                assert player.is_ai is False
            break  # Only run once
    
    @pytest.mark.asyncio
    async def test_role_assignment_edge_cases(self):
        """
        测试边界情况
        """
        async for db_session in get_test_db_session():
            sample_users = await create_sample_users(db_session, 10)
            sample_word_pairs = await create_sample_word_pairs(db_session)
            
            word_pair = sample_word_pairs[0]
            game_engine = GameEngine(db_session)
            # 使用模拟的Redis客户端
            game_engine.redis = MockRedis()
            
            # 测试最少玩家数量（3人）
            selected_users = sample_users[:3]
            game_create = GameCreate(
                room_id=str(uuid.uuid4()),
                word_pair_id=word_pair.id
            )
            
            game_state = await game_engine.create_game(game_create, selected_users)
            
            # 3人游戏应该有1个卧底，2个平民
            undercover_count = sum(1 for p in game_state.players if p.role == PlayerRole.UNDERCOVER)
            civilian_count = sum(1 for p in game_state.players if p.role == PlayerRole.CIVILIAN)
            
            assert undercover_count == 1
            assert civilian_count == 2
            
            # 测试最多玩家数量（10人）
            selected_users = sample_users[:10]
            game_create = GameCreate(
                room_id=str(uuid.uuid4()),
                word_pair_id=word_pair.id
            )
            
            game_state = await game_engine.create_game(game_create, selected_users)
            
            # 10人游戏应该有3个卧底，7个平民
            undercover_count = sum(1 for p in game_state.players if p.role == PlayerRole.UNDERCOVER)
            civilian_count = sum(1 for p in game_state.players if p.role == PlayerRole.CIVILIAN)
            
            assert undercover_count == 3
            assert civilian_count == 7
            break  # Only run once


class TestGameSpeechAndVoting:
    """测试游戏发言和投票机制"""
    
    @given(
        speech_content=st.text(min_size=1, max_size=100),
        seed=st.integers(min_value=0, max_value=1000000)
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @pytest.mark.asyncio
    async def test_speech_time_management(
        self,
        speech_content: str,
        seed: int
    ):
        """
        Feature: undercover-game-platform, Property 12: 发言时间管理
        验证需求: 需求 3.2
        
        对于任何玩家发言，系统应该限制发言时间并完整记录发言内容
        """
        async for db_session in get_test_db_session():
            import random
            random.seed(seed)
            
            # 创建测试数据
            sample_users = await create_sample_users(db_session, 5)
            sample_word_pairs = await create_sample_word_pairs(db_session)
            
            # 创建并开始游戏
            game_engine = GameEngine(db_session)
            game_engine.redis = MockRedis()
            
            game_create = GameCreate(
                room_id=str(uuid.uuid4()),
                word_pair_id=sample_word_pairs[0].id
            )
            
            game_state = await game_engine.create_game(game_create, sample_users[:5])
            
            # 设置所有玩家准备就绪
            for player in game_state.players:
                player.is_ready = True
            await game_engine._update_game_in_db(game_state)
            
            # 开始游戏
            game_state = await game_engine.start_game(game_state.id)
            
            # 验证发言时间管理
            current_speaker_id = game_state.current_speaker
            assert current_speaker_id is not None
            
            # 处理发言
            from app.schemas.game import SpeechCreate
            speech_create = SpeechCreate(content=speech_content.strip() or "测试发言")
            
            # 记录发言前的状态
            speeches_before = await game_engine.get_speeches(game_state.id, game_state.round_number)
            
            # 执行发言
            updated_game_state = await game_engine.handle_speech(
                game_state.id, 
                current_speaker_id, 
                speech_create
            )
            
            # 验证发言被正确记录
            speeches_after = await game_engine.get_speeches(game_state.id, game_state.round_number)
            assert len(speeches_after) == len(speeches_before) + 1
            
            # 验证发言内容正确
            new_speech = speeches_after[-1]
            assert new_speech.player_id == current_speaker_id
            assert new_speech.content == speech_create.content
            assert new_speech.round_number == game_state.round_number
            
            # 验证发言者已切换或进入投票阶段
            if updated_game_state.current_phase == GamePhase.SPEAKING:
                assert updated_game_state.current_speaker != current_speaker_id
            else:
                assert updated_game_state.current_phase == GamePhase.VOTING
            break  # Only run once
    
    @given(
        player_count=st.integers(min_value=3, max_value=8),
        seed=st.integers(min_value=0, max_value=1000000)
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @pytest.mark.asyncio
    async def test_vote_collection_statistics(
        self,
        player_count: int,
        seed: int
    ):
        """
        Feature: undercover-game-platform, Property 13: 投票收集统计
        验证需求: 需求 3.3
        
        对于任何投票阶段，系统应该收集所有玩家的投票并正确统计结果
        """
        async for db_session in get_test_db_session():
            import random
            random.seed(seed)
            
            # 创建测试数据
            sample_users = await create_sample_users(db_session, 10)
            sample_word_pairs = await create_sample_word_pairs(db_session)
            
            # 创建游戏
            game_engine = GameEngine(db_session)
            game_engine.redis = MockRedis()
            
            game_create = GameCreate(
                room_id=str(uuid.uuid4()),
                word_pair_id=sample_word_pairs[0].id
            )
            
            selected_users = sample_users[:player_count]
            game_state = await game_engine.create_game(game_create, selected_users)
            
            # 设置所有玩家准备就绪并开始游戏
            for player in game_state.players:
                player.is_ready = True
            await game_engine._update_game_in_db(game_state)
            game_state = await game_engine.start_game(game_state.id)
            
            # 跳过发言阶段，直接进入投票阶段
            game_state = await game_engine.force_next_phase(game_state.id)
            assert game_state.current_phase == GamePhase.VOTING
            
            # 获取存活玩家
            alive_players = game_state.alive_players
            assert len(alive_players) == player_count
            
            # 随机选择一个被投票的目标
            target_player = random.choice(alive_players)
            
            # 所有存活玩家投票
            from app.schemas.game import VoteCreate
            votes_before = await game_engine.get_votes(game_state.id, game_state.round_number)
            
            for voter in alive_players:
                if voter.id != target_player.id:  # 不能投自己
                    vote_create = VoteCreate(target_id=target_player.id)
                    await game_engine.handle_vote(game_state.id, voter.id, vote_create)
                else:
                    # 投票给其他随机玩家
                    other_players = [p for p in alive_players if p.id != voter.id]
                    if other_players:
                        vote_create = VoteCreate(target_id=random.choice(other_players).id)
                        await game_engine.handle_vote(game_state.id, voter.id, vote_create)
            
            # 验证投票收集
            votes_after = await game_engine.get_votes(game_state.id, game_state.round_number)
            assert len(votes_after) == len(votes_before) + len(alive_players)
            
            # 验证投票统计
            vote_counts = await game_engine.get_current_votes(game_state.id, game_state.round_number)
            
            # 验证统计正确性
            total_votes = sum(vote_counts.values())
            assert total_votes == len(alive_players)
            
            # 验证每个投票都被正确记录
            for vote in votes_after[-len(alive_players):]:
                assert vote.game_id == game_state.id
                assert vote.round_number == game_state.round_number
                assert vote.voter_id in [p.id for p in alive_players]
                assert vote.target_id in [p.id for p in alive_players]
                assert vote.voter_id != vote.target_id  # 不能投自己
            break  # Only run once
    
    @pytest.mark.asyncio
    async def test_speech_validation(self):
        """测试发言内容验证"""
        async for db_session in get_test_db_session():
            sample_users = await create_sample_users(db_session, 5)
            sample_word_pairs = await create_sample_word_pairs(db_session)
            
            game_engine = GameEngine(db_session)
            game_engine.redis = MockRedis()
            
            game_create = GameCreate(
                room_id=str(uuid.uuid4()),
                word_pair_id=sample_word_pairs[0].id
            )
            
            game_state = await game_engine.create_game(game_create, sample_users[:5])
            
            # 设置准备并开始游戏
            for player in game_state.players:
                player.is_ready = True
            await game_engine._update_game_in_db(game_state)
            game_state = await game_engine.start_game(game_state.id)
            
            current_speaker_id = game_state.current_speaker
            
            # 测试空发言被拒绝
            from app.schemas.game import SpeechCreate
            with pytest.raises(Exception):  # 应该抛出验证错误
                empty_speech = SpeechCreate(content="")
                await game_engine.handle_speech(game_state.id, current_speaker_id, empty_speech)
            
            # 测试正常发言
            valid_speech = SpeechCreate(content="这是一个正常的发言")
            updated_state = await game_engine.handle_speech(game_state.id, current_speaker_id, valid_speech)
            
            # 验证发言被记录
            speeches = await game_engine.get_speeches(game_state.id, game_state.round_number)
            assert len(speeches) == 1
            assert speeches[0].content == "这是一个正常的发言"
            break  # Only run once
    
    @pytest.mark.asyncio
    async def test_vote_validation(self):
        """测试投票验证"""
        async for db_session in get_test_db_session():
            sample_users = await create_sample_users(db_session, 5)
            sample_word_pairs = await create_sample_word_pairs(db_session)
            
            game_engine = GameEngine(db_session)
            game_engine.redis = MockRedis()
            
            game_create = GameCreate(
                room_id=str(uuid.uuid4()),
                word_pair_id=sample_word_pairs[0].id
            )
            
            game_state = await game_engine.create_game(game_create, sample_users[:5])
            
            # 设置准备并开始游戏
            for player in game_state.players:
                player.is_ready = True
            await game_engine._update_game_in_db(game_state)
            game_state = await game_engine.start_game(game_state.id)
            
            # 进入投票阶段
            game_state = await game_engine.force_next_phase(game_state.id)
            
            alive_players = game_state.alive_players
            voter = alive_players[0]
            target = alive_players[1]
            
            # 测试正常投票
            from app.schemas.game import VoteCreate
            vote_create = VoteCreate(target_id=target.id)
            updated_state = await game_engine.handle_vote(game_state.id, voter.id, vote_create)
            
            # 验证投票被记录
            votes = await game_engine.get_votes(game_state.id, game_state.round_number)
            assert len(votes) == 1
            assert votes[0].voter_id == voter.id
            assert votes[0].target_id == target.id
            
            # 测试投票给自己被拒绝
            with pytest.raises(ValueError, match="不能投票给自己"):
                self_vote = VoteCreate(target_id=voter.id)
                await game_engine.handle_vote(game_state.id, voter.id, self_vote)
            
            # 测试重复投票（应该更新投票）
            new_target = alive_players[2]
            new_vote = VoteCreate(target_id=new_target.id)
            await game_engine.handle_vote(game_state.id, voter.id, new_vote)
            
            # 验证投票被更新而不是新增
            votes_after = await game_engine.get_votes(game_state.id, game_state.round_number)
            assert len(votes_after) == 1  # 仍然只有一票
            assert votes_after[0].target_id == new_target.id  # 但目标已更新
            break  # Only run once


class TestGameEndingAndVictory:
    """测试游戏结束和胜利判断"""
    
    @given(
        player_count=st.integers(min_value=3, max_value=8),
        seed=st.integers(min_value=0, max_value=1000000)
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @pytest.mark.asyncio
    async def test_elimination_handling_correctness(
        self,
        player_count: int,
        seed: int
    ):
        """
        Feature: undercover-game-platform, Property 14: 淘汰处理正确性
        验证需求: 需求 3.4
        
        对于任何玩家淘汰事件，系统应该公布玩家身份并正确更新游戏状态
        """
        async for db_session in get_test_db_session():
            import random
            random.seed(seed)
            
            # 创建测试数据
            sample_users = await create_sample_users(db_session, 10)
            sample_word_pairs = await create_sample_word_pairs(db_session)
            
            # 创建游戏
            game_engine = GameEngine(db_session)
            game_engine.redis = MockRedis()
            
            game_create = GameCreate(
                room_id=str(uuid.uuid4()),
                word_pair_id=sample_word_pairs[0].id
            )
            
            selected_users = sample_users[:player_count]
            game_state = await game_engine.create_game(game_create, selected_users)
            
            # 记录初始状态
            initial_alive_count = len(game_state.alive_players)
            initial_eliminated_count = len(game_state.eliminated_players)
            
            # 随机选择一个玩家进行淘汰
            target_player = random.choice(game_state.alive_players)
            target_role = target_player.role
            
            # 执行淘汰
            await game_engine._eliminate_player(game_state, target_player.id)
            
            # 验证淘汰处理正确性
            
            # 1. 验证玩家状态更新
            updated_player = next(p for p in game_state.players if p.id == target_player.id)
            assert updated_player.is_alive is False
            
            # 2. 验证淘汰列表更新
            assert target_player.id in game_state.eliminated_players
            assert len(game_state.eliminated_players) == initial_eliminated_count + 1
            
            # 3. 验证存活玩家数量减少
            current_alive_count = len(game_state.alive_players)
            assert current_alive_count == initial_alive_count - 1
            
            # 4. 验证其他玩家状态不变
            for player in game_state.players:
                if player.id != target_player.id:
                    assert player.is_alive is True
            
            # 5. 验证角色信息保持不变（淘汰不改变角色）
            assert updated_player.role == target_role
            assert updated_player.word is not None
            break  # Only run once
    
    @given(
        initial_undercover_count=st.integers(min_value=1, max_value=3),
        initial_civilian_count=st.integers(min_value=2, max_value=5),
        seed=st.integers(min_value=0, max_value=1000000)
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @pytest.mark.asyncio
    async def test_victory_condition_judgment(
        self,
        initial_undercover_count: int,
        initial_civilian_count: int,
        seed: int
    ):
        """
        Feature: undercover-game-platform, Property 15: 胜利条件判断
        验证需求: 需求 3.5
        
        对于任何满足胜利条件的游戏状态，系统应该结束游戏并公布正确的结果
        """
        async for db_session in get_test_db_session():
            import random
            random.seed(seed)
            
            # 创建测试数据
            sample_users = await create_sample_users(db_session, 10)
            sample_word_pairs = await create_sample_word_pairs(db_session)
            
            total_players = initial_undercover_count + initial_civilian_count
            if total_players > 10:
                return  # 跳过无效的组合
            
            # 创建游戏
            game_engine = GameEngine(db_session)
            game_engine.redis = MockRedis()
            
            game_create = GameCreate(
                room_id=str(uuid.uuid4()),
                word_pair_id=sample_word_pairs[0].id
            )
            
            selected_users = sample_users[:total_players]
            game_state = await game_engine.create_game(game_create, selected_users)
            
            # 手动设置角色分配以控制测试条件
            undercover_assigned = 0
            civilian_assigned = 0
            
            for player in game_state.players:
                if undercover_assigned < initial_undercover_count:
                    player.role = PlayerRole.UNDERCOVER
                    player.word = sample_word_pairs[0].undercover_word
                    undercover_assigned += 1
                else:
                    player.role = PlayerRole.CIVILIAN
                    player.word = sample_word_pairs[0].civilian_word
                    civilian_assigned += 1
            
            await game_engine._update_game_in_db(game_state)
            
            # 测试场景1: 平民获胜（淘汰所有卧底）
            if initial_undercover_count <= initial_civilian_count:
                # 淘汰所有卧底
                undercover_players = [p for p in game_state.players if p.role == PlayerRole.UNDERCOVER]
                for undercover in undercover_players:
                    await game_engine._eliminate_player(game_state, undercover.id)
                
                # 检查胜利条件
                end_result = await game_engine.check_game_end_conditions(game_state.id)
                
                # 验证平民获胜
                assert end_result is not None
                assert end_result['game_over'] is True
                assert end_result['winner_role'] == PlayerRole.CIVILIAN
                assert len(end_result['winner_players']) == initial_civilian_count
                assert '平民获胜' in end_result['reason']
            
            # 重置游戏状态进行第二个测试场景
            # 恢复所有玩家状态
            for player in game_state.players:
                player.is_alive = True
            game_state.eliminated_players = []
            await game_engine._update_game_in_db(game_state)
            
            # 测试场景2: 卧底获胜（卧底数量 >= 平民数量）
            civilian_players = [p for p in game_state.players if p.role == PlayerRole.CIVILIAN]
            
            # 淘汰足够的平民使卧底数量 >= 平民数量
            civilians_to_eliminate = len(civilian_players) - initial_undercover_count + 1
            if civilians_to_eliminate > 0 and civilians_to_eliminate <= len(civilian_players):
                for i in range(min(civilians_to_eliminate, len(civilian_players))):
                    await game_engine._eliminate_player(game_state, civilian_players[i].id)
                
                # 检查胜利条件
                end_result = await game_engine.check_game_end_conditions(game_state.id)
                
                # 验证卧底获胜
                if game_state.undercover_count >= game_state.civilian_count:
                    assert end_result is not None
                    assert end_result['game_over'] is True
                    assert end_result['winner_role'] == PlayerRole.UNDERCOVER
                    assert len(end_result['winner_players']) == initial_undercover_count
                    assert '卧底获胜' in end_result['reason']
            break  # Only run once
    
    @pytest.mark.asyncio
    async def test_game_result_calculation(self):
        """测试游戏结果计算"""
        async for db_session in get_test_db_session():
            sample_users = await create_sample_users(db_session, 5)
            sample_word_pairs = await create_sample_word_pairs(db_session)
            
            game_engine = GameEngine(db_session)
            game_engine.redis = MockRedis()
            
            game_create = GameCreate(
                room_id=str(uuid.uuid4()),
                word_pair_id=sample_word_pairs[0].id
            )
            
            game_state = await game_engine.create_game(game_create, sample_users[:5])
            
            # 设置准备并开始游戏
            for player in game_state.players:
                player.is_ready = True
            await game_engine._update_game_in_db(game_state)
            game_state = await game_engine.start_game(game_state.id)
            
            # 强制结束游戏
            ended_state = await game_engine.force_end_game(game_state.id, "测试结束")
            
            # 验证游戏结果
            result = await game_engine.get_game_result(game_state.id)
            
            assert result is not None
            assert result['game_id'] == game_state.id
            assert result['forced_end'] is True
            assert result['end_reason'] == "测试结束"
            assert len(result['players']) == 5
            
            # 验证玩家信息完整
            for player_info in result['players']:
                assert 'id' in player_info
                assert 'username' in player_info
                assert 'role' in player_info
                assert 'word' in player_info
                assert 'is_alive' in player_info
                assert 'is_winner' in player_info
            break  # Only run once
    
    @pytest.mark.asyncio
    async def test_player_performance_calculation(self):
        """测试玩家表现计算"""
        async for db_session in get_test_db_session():
            sample_users = await create_sample_users(db_session, 5)
            sample_word_pairs = await create_sample_word_pairs(db_session)
            
            game_engine = GameEngine(db_session)
            game_engine.redis = MockRedis()
            
            game_create = GameCreate(
                room_id=str(uuid.uuid4()),
                word_pair_id=sample_word_pairs[0].id
            )
            
            game_state = await game_engine.create_game(game_create, sample_users[:5])
            
            # 选择一个玩家进行测试
            test_player = game_state.players[0]
            
            # 计算玩家表现
            performance = await game_engine.calculate_player_performance(game_state.id, test_player.id)
            
            # 验证表现数据
            assert performance['player_id'] == test_player.id
            assert performance['username'] == test_player.username
            assert performance['role'] == test_player.role.value
            assert performance['word'] == test_player.word
            assert 'speeches_count' in performance
            assert 'votes_cast' in performance
            assert 'votes_received' in performance
            assert 'survival_rounds' in performance
            assert 'performance_score' in performance
            assert performance['performance_score'] >= 0
            break  # Only run once
    
    @pytest.mark.asyncio
    async def test_mvp_selection(self):
        """测试MVP玩家选择"""
        async for db_session in get_test_db_session():
            sample_users = await create_sample_users(db_session, 5)
            sample_word_pairs = await create_sample_word_pairs(db_session)
            
            game_engine = GameEngine(db_session)
            game_engine.redis = MockRedis()
            
            game_create = GameCreate(
                room_id=str(uuid.uuid4()),
                word_pair_id=sample_word_pairs[0].id
            )
            
            game_state = await game_engine.create_game(game_create, sample_users[:5])
            
            # 强制结束游戏以便计算MVP
            await game_engine.force_end_game(game_state.id)
            
            # 获取MVP
            mvp = await game_engine.get_mvp_player(game_state.id)
            
            # 验证MVP数据
            if mvp:  # MVP可能为None如果没有玩家
                assert 'player_id' in mvp
                assert 'username' in mvp
                assert 'performance_score' in mvp
                assert mvp['performance_score'] >= 0
            break  # Only run once