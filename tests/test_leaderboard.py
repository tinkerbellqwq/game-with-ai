"""
Leaderboard system tests
排行榜系统测试
"""

import pytest
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.leaderboard import leaderboard_service
from app.schemas.leaderboard import LeaderboardQuery
from app.models.user import User


class TestLeaderboardService:
    """排行榜服务测试"""
    
    @pytest.mark.asyncio
    async def test_get_leaderboard_basic(self, db_session: AsyncSession, sample_users):
        """测试基本排行榜获取功能"""
        # 创建查询
        query = LeaderboardQuery(page=1, page_size=10, sort_by="score", order="desc")
        
        # 获取排行榜
        leaderboard = await leaderboard_service.get_leaderboard(query, db_session)
        
        # 验证结果
        assert leaderboard is not None
        assert leaderboard.page == 1
        assert leaderboard.page_size == 10
        assert len(leaderboard.entries) <= 10
        assert leaderboard.total_count >= 0
        
        # 验证排序正确性（按积分降序）
        if len(leaderboard.entries) > 1:
            for i in range(len(leaderboard.entries) - 1):
                assert leaderboard.entries[i].score >= leaderboard.entries[i + 1].score
    
    @pytest.mark.asyncio
    async def test_get_user_rank(self, db_session: AsyncSession, sample_users):
        """测试获取用户排名"""
        if not sample_users:
            pytest.skip("No sample users available")
        
        user_id = sample_users[0].id
        
        # 获取用户排名
        user_rank = await leaderboard_service.get_user_rank(user_id, db_session)
        
        # 验证结果
        assert user_rank is not None
        assert user_rank.user_id == user_id
        assert user_rank.current_rank > 0
        assert user_rank.score >= 0
        assert user_rank.games_played >= 0
        assert user_rank.games_won >= 0
        assert 0 <= user_rank.win_rate <= 100
    
    @pytest.mark.asyncio
    async def test_get_personal_stats(self, db_session: AsyncSession, sample_users):
        """测试获取个人统计信息"""
        if not sample_users:
            pytest.skip("No sample users available")
        
        user_id = sample_users[0].id
        
        # 获取个人统计
        personal_stats = await leaderboard_service.get_personal_stats(user_id, db_session)
        
        # 验证结果
        assert personal_stats is not None
        assert personal_stats.user_id == user_id
        assert personal_stats.current_rank > 0
        assert personal_stats.score >= 0
        assert personal_stats.games_played >= 0
        assert personal_stats.games_won >= 0
        assert personal_stats.games_lost >= 0
        assert personal_stats.games_played == personal_stats.games_won + personal_stats.games_lost
        assert 0 <= personal_stats.win_rate <= 100
    
    @pytest.mark.asyncio
    async def test_leaderboard_pagination(self, db_session: AsyncSession):
        """测试排行榜分页功能"""
        # 测试第一页
        query1 = LeaderboardQuery(page=1, page_size=5, sort_by="score", order="desc")
        leaderboard1 = await leaderboard_service.get_leaderboard(query1, db_session)
        
        # 测试第二页
        query2 = LeaderboardQuery(page=2, page_size=5, sort_by="score", order="desc")
        leaderboard2 = await leaderboard_service.get_leaderboard(query2, db_session)
        
        # 验证分页逻辑
        assert leaderboard1.page == 1
        assert leaderboard2.page == 2
        assert leaderboard1.page_size == 5
        assert leaderboard2.page_size == 5
        
        # 如果有足够的用户，验证分页内容不重复
        if leaderboard1.total_count > 5:
            assert leaderboard1.has_next == True
            if len(leaderboard2.entries) > 0:
                # 确保两页的用户不重复
                page1_users = {entry.user_id for entry in leaderboard1.entries}
                page2_users = {entry.user_id for entry in leaderboard2.entries}
                assert page1_users.isdisjoint(page2_users)
    
    @pytest.mark.asyncio
    async def test_leaderboard_sorting(self, db_session: AsyncSession):
        """测试排行榜排序功能"""
        # 测试按积分降序
        query_desc = LeaderboardQuery(page=1, page_size=10, sort_by="score", order="desc")
        leaderboard_desc = await leaderboard_service.get_leaderboard(query_desc, db_session)
        
        # 测试按积分升序
        query_asc = LeaderboardQuery(page=1, page_size=10, sort_by="score", order="asc")
        leaderboard_asc = await leaderboard_service.get_leaderboard(query_asc, db_session)
        
        # 验证排序正确性
        if len(leaderboard_desc.entries) > 1:
            for i in range(len(leaderboard_desc.entries) - 1):
                assert leaderboard_desc.entries[i].score >= leaderboard_desc.entries[i + 1].score
        
        if len(leaderboard_asc.entries) > 1:
            for i in range(len(leaderboard_asc.entries) - 1):
                assert leaderboard_asc.entries[i].score <= leaderboard_asc.entries[i + 1].score
    
    @pytest.mark.asyncio
    async def test_cache_invalidation(self, db_session: AsyncSession, sample_users):
        """测试缓存失效功能"""
        if not sample_users:
            pytest.skip("No sample users available")
        
        user_id = sample_users[0].id
        
        # 清除缓存
        await leaderboard_service.invalidate_leaderboard_cache()
        await leaderboard_service.invalidate_user_rank_cache(user_id)
        
        # 验证操作不会抛出异常
        assert True  # 如果到达这里说明缓存清除成功
    
    @pytest.mark.asyncio
    async def test_nonexistent_user_rank(self, db_session: AsyncSession):
        """测试获取不存在用户的排名"""
        fake_user_id = "nonexistent-user-id"
        
        # 获取不存在用户的排名
        user_rank = await leaderboard_service.get_user_rank(fake_user_id, db_session)
        
        # 应该返回None
        assert user_rank is None
    
    @pytest.mark.asyncio
    async def test_nonexistent_user_stats(self, db_session: AsyncSession):
        """测试获取不存在用户的统计信息"""
        fake_user_id = "nonexistent-user-id"
        
        # 获取不存在用户的统计信息
        personal_stats = await leaderboard_service.get_personal_stats(fake_user_id, db_session)
        
        # 应该返回None
        assert personal_stats is None


class TestLeaderboardIntegration:
    """排行榜集成测试"""
    
    @pytest.mark.asyncio
    async def test_leaderboard_after_score_update(self, db_session: AsyncSession, sample_users):
        """测试积分更新后排行榜的变化"""
        if len(sample_users) < 2:
            pytest.skip("Need at least 2 users for this test")
        
        user1 = sample_users[0]
        user2 = sample_users[1]
        
        # 获取初始排名
        initial_rank1 = await leaderboard_service.get_user_rank(user1.id, db_session)
        initial_rank2 = await leaderboard_service.get_user_rank(user2.id, db_session)
        
        # 更新用户1的积分
        user1.score += 100
        user1.games_played += 1
        user1.games_won += 1
        await db_session.commit()
        
        # 清除缓存以确保获取最新数据
        await leaderboard_service.invalidate_leaderboard_cache()
        await leaderboard_service.invalidate_user_rank_cache(user1.id)
        
        # 获取更新后的排名
        updated_rank1 = await leaderboard_service.get_user_rank(user1.id, db_session)
        
        # 验证排名可能发生变化
        assert updated_rank1 is not None
        assert updated_rank1.score == initial_rank1.score + 100
        assert updated_rank1.games_played == initial_rank1.games_played + 1
        assert updated_rank1.games_won == initial_rank1.games_won + 1
    
    @pytest.mark.asyncio
    async def test_win_rate_calculation(self, db_session: AsyncSession, sample_users):
        """测试胜率计算的正确性"""
        if not sample_users:
            pytest.skip("No sample users available")
        
        user = sample_users[0]
        
        # 设置测试数据
        user.games_played = 10
        user.games_won = 7
        await db_session.commit()
        
        # 清除缓存
        await leaderboard_service.invalidate_user_rank_cache(user.id)
        
        # 获取用户排名信息
        user_rank = await leaderboard_service.get_user_rank(user.id, db_session)
        
        # 验证胜率计算
        assert user_rank is not None
        expected_win_rate = (7 / 10) * 100
        assert abs(user_rank.win_rate - expected_win_rate) < 0.01  # 允许小数点误差
    
    @pytest.mark.asyncio
    async def test_rank_consistency(self, db_session: AsyncSession):
        """测试排名一致性"""
        # 获取排行榜
        query = LeaderboardQuery(page=1, page_size=20, sort_by="score", order="desc")
        leaderboard = await leaderboard_service.get_leaderboard(query, db_session)
        
        # 验证排名的连续性
        for i, entry in enumerate(leaderboard.entries):
            expected_rank = i + 1
            assert entry.rank == expected_rank
        
        # 验证每个用户的个人排名与排行榜中的排名一致
        for entry in leaderboard.entries[:5]:  # 只测试前5名以节省时间
            user_rank = await leaderboard_service.get_user_rank(entry.user_id, db_session)
            assert user_rank is not None
            assert user_rank.current_rank == entry.rank
            assert user_rank.score == entry.score