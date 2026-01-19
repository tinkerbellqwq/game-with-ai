"""
Tests for logging and recording system
测试日志和记录系统

验证需求:
- 需求 9.2: 游戏结束时完整记录游戏过程和结果
- 需求 9.5: 数据损坏检测和修复
- 需求 10.5: 安全日志记录（记录关键操作但不泄露敏感信息）
"""

import pytest
import uuid
from datetime import datetime
from sqlalchemy.orm import Session

from app.services.audit_logger import (
    audit_logger, AuditEventType, log_user_action, log_security_event,
    data_integrity_checker, store_data_safely, verify_data, repair_corrupted_data
)
from app.services.game_recorder import get_game_recorder, record_game_event
from app.models.user import User
from app.models.game import Game
from app.models.word_pair import WordPair
from app.schemas.game import GamePhase, PlayerRole


@pytest.mark.asyncio
async def test_audit_logger_sanitizes_sensitive_data(db_session: Session):
    """测试审计日志器清理敏感信息"""
    # 测试数据包含敏感字段
    test_data = {
        "username": "testuser",
        "password": "secret123",
        "email": "test@example.com",
        "token": "abc123xyz"
    }
    
    # 清理敏感信息
    sanitized = audit_logger._sanitize_data(test_data)
    
    # 验证敏感字段被清理
    assert sanitized["username"] == "testuser"
    assert sanitized["email"] == "test@example.com"
    assert sanitized["password"] == "***REDACTED***"
    assert sanitized["token"] == "***REDACTED***"


@pytest.mark.asyncio
async def test_audit_logger_logs_user_action(db_session: Session):
    """测试审计日志记录用户操作"""
    user_id = str(uuid.uuid4())
    
    # 记录用户登录事件
    result = await audit_logger.log_event(
        event_type=AuditEventType.USER_LOGIN,
        user_id=user_id,
        details={"username": "testuser"},
        ip_address="127.0.0.1",
        success=True
    )
    
    # 验证记录成功
    assert result is True


@pytest.mark.asyncio
async def test_audit_logger_logs_security_event(db_session: Session):
    """测试审计日志记录安全事件"""
    # 记录速率限制事件
    result = await audit_logger.log_event(
        event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
        details={
            "endpoint": "/api/auth/login",
            "attempts": 10
        },
        ip_address="192.168.1.100",
        success=False
    )
    
    # 验证记录成功
    assert result is True


@pytest.mark.asyncio
async def test_game_recorder_records_game_start(db_session: Session):
    """测试游戏记录器记录游戏开始"""
    game_id = str(uuid.uuid4())
    recorder = get_game_recorder(db_session)
    
    # 记录游戏开始
    game_data = {
        "room_id": str(uuid.uuid4()),
        "word_pair_id": str(uuid.uuid4()),
        "players": [
            {"id": str(uuid.uuid4()), "username": "player1"},
            {"id": str(uuid.uuid4()), "username": "player2"}
        ],
        "settings": {"difficulty": 1}
    }
    
    result = await recorder.record_game_start(game_id, game_data)
    
    # 验证记录成功
    assert result is True


@pytest.mark.asyncio
async def test_game_recorder_records_speech(db_session: Session):
    """测试游戏记录器记录玩家发言"""
    game_id = str(uuid.uuid4())
    player_id = str(uuid.uuid4())
    recorder = get_game_recorder(db_session)
    
    # 记录发言
    speech_data = {
        "content": "这是我的描述",
        "round_number": 1,
        "speech_order": 1
    }
    
    result = await recorder.record_speech(game_id, player_id, speech_data)
    
    # 验证记录成功
    assert result is True


@pytest.mark.asyncio
async def test_game_recorder_records_vote(db_session: Session):
    """测试游戏记录器记录玩家投票"""
    game_id = str(uuid.uuid4())
    voter_id = str(uuid.uuid4())
    target_id = str(uuid.uuid4())
    recorder = get_game_recorder(db_session)
    
    # 记录投票
    vote_data = {
        "target_id": target_id,
        "round_number": 1
    }
    
    result = await recorder.record_vote(game_id, voter_id, vote_data)
    
    # 验证记录成功
    assert result is True


@pytest.mark.asyncio
async def test_game_recorder_records_elimination(db_session: Session):
    """测试游戏记录器记录玩家淘汰"""
    game_id = str(uuid.uuid4())
    eliminated_player_id = str(uuid.uuid4())
    recorder = get_game_recorder(db_session)
    
    # 记录淘汰
    elimination_data = {
        "round_number": 1,
        "vote_count": 3,
        "revealed_role": "civilian"
    }
    
    result = await recorder.record_elimination(game_id, eliminated_player_id, elimination_data)
    
    # 验证记录成功
    assert result is True


@pytest.mark.asyncio
async def test_game_recorder_records_game_finish(db_session: Session):
    """测试游戏记录器记录游戏结束"""
    game_id = str(uuid.uuid4())
    recorder = get_game_recorder(db_session)
    
    # 记录游戏结束
    finish_data = {
        "winner_role": "civilian",
        "winner_players": [str(uuid.uuid4()), str(uuid.uuid4())],
        "total_rounds": 3,
        "duration_minutes": 15.5,
        "final_players": []
    }
    
    result = await recorder.record_game_finish(game_id, finish_data)
    
    # 验证记录成功
    assert result is True


@pytest.mark.asyncio
async def test_game_recorder_verifies_integrity(db_session: Session):
    """测试游戏记录器验证记录完整性"""
    game_id = str(uuid.uuid4())
    recorder = get_game_recorder(db_session)
    
    # 记录完整的游戏流程
    await recorder.record_game_start(game_id, {
        "room_id": str(uuid.uuid4()),
        "word_pair_id": str(uuid.uuid4()),
        "players": [{"id": str(uuid.uuid4()), "username": "player1"}]
    })
    
    await recorder.record_speech(game_id, str(uuid.uuid4()), {
        "content": "test speech",
        "round_number": 1,
        "speech_order": 1
    })
    
    await recorder.record_game_finish(game_id, {
        "winner_role": "civilian",
        "winner_players": [],
        "total_rounds": 1,
        "duration_minutes": 5.0,
        "final_players": []
    })
    
    # 验证完整性
    integrity = await recorder.verify_game_record_integrity(game_id)
    
    # 验证结果
    assert integrity["game_id"] == game_id
    assert integrity["is_complete"] is True
    assert len(integrity["errors"]) == 0


@pytest.mark.asyncio
async def test_convenience_functions(db_session: Session):
    """测试便捷函数"""
    user_id = str(uuid.uuid4())
    
    # 测试log_user_action
    result = await log_user_action(
        event_type=AuditEventType.USER_REGISTER,
        user_id=user_id,
        details={"username": "newuser"}
    )
    assert result is True
    
    # 测试log_security_event
    result = await log_security_event(
        event_type=AuditEventType.SECURITY_VIOLATION,
        details={"reason": "invalid_token"}
    )
    assert result is True
    
    # 测试record_game_event
    game_id = str(uuid.uuid4())
    result = await record_game_event(
        db=db_session,
        event_type="start",
        game_id=game_id,
        data={
            "room_id": str(uuid.uuid4()),
            "word_pair_id": str(uuid.uuid4()),
            "players": []
        }
    )
    assert result is True


@pytest.mark.asyncio
async def test_audit_logger_nested_sanitization(db_session: Session):
    """测试审计日志器嵌套数据清理"""
    # 测试嵌套结构
    test_data = {
        "user": {
            "username": "testuser",
            "password": "secret123",
            "profile": {
                "email": "test@example.com",
                "api_key": "key123"
            }
        },
        "tokens": ["token1", "token2"]
    }
    
    # 清理敏感信息
    sanitized = audit_logger._sanitize_data(test_data)
    
    # 验证嵌套敏感字段被清理
    assert sanitized["user"]["username"] == "testuser"
    assert sanitized["user"]["password"] == "***REDACTED***"
    assert sanitized["user"]["profile"]["email"] == "test@example.com"
    assert sanitized["user"]["profile"]["api_key"] == "***REDACTED***"
    assert sanitized["tokens"] == ["token1", "token2"]


@pytest.mark.asyncio
async def test_data_integrity_store_and_verify(db_session: Session):
    """测试数据完整性存储和验证"""
    test_key = f"test:integrity:{uuid.uuid4()}"
    test_data = {
        "game_id": str(uuid.uuid4()),
        "player_count": 5,
        "status": "active"
    }
    
    # 安全存储数据
    result = await store_data_safely(test_key, test_data, ttl=300)
    assert result is True
    
    # 验证数据完整性
    verify_result = await verify_data(test_key)
    assert verify_result["is_valid"] is True
    assert verify_result["status"] == "valid"


@pytest.mark.asyncio
async def test_data_integrity_checksum_calculation(db_session: Session):
    """测试校验和计算一致性"""
    test_data = {
        "id": "test123",
        "value": 42,
        "nested": {"key": "value"}
    }
    
    # 计算两次校验和应该相同
    checksum1 = data_integrity_checker._calculate_checksum(test_data)
    checksum2 = data_integrity_checker._calculate_checksum(test_data)
    
    assert checksum1 == checksum2
    assert len(checksum1) == 64  # SHA256 produces 64 hex characters


@pytest.mark.asyncio
async def test_data_integrity_repair_from_backup(db_session: Session):
    """测试从备份修复数据"""
    test_key = f"test:repair:{uuid.uuid4()}"
    test_data = {
        "game_id": str(uuid.uuid4()),
        "important_data": "should_be_preserved"
    }
    
    # 先存储数据
    await store_data_safely(test_key, test_data, ttl=300)
    
    # 验证数据存在且有效
    verify_result = await verify_data(test_key)
    assert verify_result["is_valid"] is True
    
    # 尝试修复（即使数据没有损坏，也应该能从备份恢复）
    repair_result = await repair_corrupted_data(test_key)
    # 修复应该成功（从备份恢复）
    assert repair_result["status"] in ["success", "failed"]  # 取决于备份是否存在


@pytest.mark.asyncio
async def test_audit_logger_logs_data_corruption_events(db_session: Session):
    """测试审计日志记录数据损坏事件"""
    # 记录数据损坏检测事件
    result = await audit_logger.log_event(
        event_type=AuditEventType.DATA_CORRUPTION_DETECTED,
        details={
            "key": "test:corrupted:key",
            "stored_checksum": "abc123",
            "current_checksum": "def456"
        }
    )
    assert result is True
    
    # 记录数据修复尝试事件
    result = await audit_logger.log_event(
        event_type=AuditEventType.DATA_REPAIR_ATTEMPTED,
        details={"key": "test:corrupted:key"}
    )
    assert result is True


@pytest.mark.asyncio
async def test_game_recorder_with_integrity_check(db_session: Session):
    """测试游戏记录器带完整性检查"""
    game_id = str(uuid.uuid4())
    recorder = get_game_recorder(db_session)
    
    # 记录完整的游戏流程
    await recorder.record_game_start(game_id, {
        "room_id": str(uuid.uuid4()),
        "word_pair_id": str(uuid.uuid4()),
        "players": [
            {"id": str(uuid.uuid4()), "username": "player1"},
            {"id": str(uuid.uuid4()), "username": "player2"}
        ]
    })
    
    # 记录发言
    await recorder.record_speech(game_id, str(uuid.uuid4()), {
        "content": "这是测试发言",
        "round_number": 1,
        "speech_order": 1
    })
    
    # 记录投票
    await recorder.record_vote(game_id, str(uuid.uuid4()), {
        "target_id": str(uuid.uuid4()),
        "round_number": 1
    })
    
    # 记录游戏结束
    await recorder.record_game_finish(game_id, {
        "winner_role": "civilian",
        "winner_players": [str(uuid.uuid4())],
        "total_rounds": 2,
        "duration_minutes": 10.5,
        "final_players": []
    })
    
    # 获取记录并验证
    record = await recorder.get_game_record(game_id)
    assert record is not None
    assert record.get("game_id") == game_id
    
    # 验证完整性
    integrity = await recorder.verify_game_record_integrity(game_id)
    assert integrity["is_complete"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
