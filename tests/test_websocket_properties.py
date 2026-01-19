"""
WebSocket通信属性测试
Property-based tests for WebSocket communication
"""

import pytest
import asyncio
import json
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock
from hypothesis import given, strategies as st, settings
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize, invariant

from app.websocket.connection_manager import ConnectionManager


class MockWebSocket:
    """Mock WebSocket for testing"""
    
    def __init__(self):
        self.messages_sent: List[str] = []
        self.closed = False
        self.close_code = None
        self.close_reason = None
        self.accepted = False
    
    async def accept(self):
        """Mock accept method"""
        self.accepted = True
    
    async def close(self, code: int = 1000, reason: str = ""):
        """Mock close method"""
        self.closed = True
        self.close_code = code
        self.close_reason = reason
    
    async def send_text(self, data: str):
        """Mock send_text method"""
        if self.closed:
            raise Exception("WebSocket is closed")
        self.messages_sent.append(data)
    
    async def ping(self):
        """Mock ping method"""
        if self.closed:
            raise Exception("WebSocket is closed")
        return True


# Hypothesis strategies for generating test data
user_id_strategy = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))
room_id_strategy = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))
message_type_strategy = st.sampled_from(['chat_message', 'game_action', 'system_message', 'notification'])
message_content_strategy = st.text(min_size=0, max_size=500)


@pytest.mark.asyncio
@given(
    user_ids=st.lists(user_id_strategy, min_size=1, max_size=10, unique=True),
    room_id=room_id_strategy,
    message_type=message_type_strategy,
    message_content=message_content_strategy
)
@settings(max_examples=100, deadline=5000)
async def test_property_29_message_broadcast_integrity(user_ids, room_id, message_type, message_content):
    """
    Feature: undercover-game-platform, Property 29: 消息广播完整性
    验证需求: 需求 7.1
    
    属性 29: 消息广播完整性
    对于任何玩家发送的消息，系统应该立即广播给房间内所有其他玩家
    """
    # 创建连接管理器
    manager = ConnectionManager()
    
    # 创建模拟WebSocket连接
    websockets = {}
    for user_id in user_ids:
        websocket = MockWebSocket()
        websockets[user_id] = websocket
        
        # 建立连接
        success = await manager.connect(user_id, websocket, room_id)
        assert success, f"Failed to connect user {user_id}"
        assert websocket.accepted, f"WebSocket not accepted for user {user_id}"
    
    # 验证所有用户都在房间中
    room_users = manager.get_room_users(room_id)
    assert room_users == set(user_ids), "Not all users are in the room"
    
    # 选择一个发送者
    sender_id = user_ids[0]
    expected_recipients = set(user_ids) - {sender_id}
    
    # 创建测试消息
    test_message = {
        "type": message_type,
        "data": {"content": message_content},
        "sender_id": sender_id
    }
    
    # 广播消息
    sent_count = await manager.broadcast_to_room(room_id, test_message, exclude_user=sender_id)
    
    # 验证广播完整性
    assert sent_count == len(expected_recipients), f"Expected {len(expected_recipients)} recipients, got {sent_count}"
    
    # 验证每个接收者都收到了消息
    for user_id in expected_recipients:
        websocket = websockets[user_id]
        assert len(websocket.messages_sent) > 0, f"User {user_id} did not receive any messages"
        
        # 解析最后一条消息
        last_message = json.loads(websocket.messages_sent[-1])
        assert last_message["type"] == message_type, f"Message type mismatch for user {user_id}"
        assert last_message["sender_id"] == sender_id, f"Sender ID mismatch for user {user_id}"
        assert last_message["room_id"] == room_id, f"Room ID mismatch for user {user_id}"
    
    # 验证发送者没有收到自己的消息（因为被排除）
    sender_websocket = websockets[sender_id]
    # 发送者应该只收到连接确认消息，不应该收到广播消息
    if sender_websocket.messages_sent:
        for message_str in sender_websocket.messages_sent:
            message = json.loads(message_str)
            # 发送者不应该收到自己发送的消息
            if message.get("type") == message_type and message.get("sender_id") == sender_id:
                assert False, f"Sender {sender_id} received their own message"


@pytest.mark.asyncio
@given(
    user_id=user_id_strategy,
    room_id=room_id_strategy,
    disconnect_scenarios=st.lists(
        st.sampled_from(['network_error', 'client_disconnect', 'server_restart']),
        min_size=1, max_size=3
    )
)
@settings(max_examples=50, deadline=10000)
async def test_property_33_connection_recovery_mechanism(user_id, room_id, disconnect_scenarios):
    """
    Feature: undercover-game-platform, Property 33: 连接恢复机制
    验证需求: 需求 7.5
    
    属性 33: 连接恢复机制
    对于任何连接中断事件，系统应该尝试重连并同步消息历史
    """
    manager = ConnectionManager()
    
    # 测试消息队列功能（离线消息存储）
    test_messages = []
    for i, scenario in enumerate(disconnect_scenarios):
        test_message = {
            "type": "test_message",
            "data": {"scenario": scenario, "index": i},
            "sender_id": "system"
        }
        test_messages.append(test_message)
    
    # 用户离线时发送消息（应该被排队）
    for message in test_messages:
        success = await manager.send_to_user(user_id, message)
        assert not success, "Message should not be sent to offline user"
    
    # 验证消息被排队
    assert user_id in manager.message_queues, "Message queue not created for offline user"
    assert len(manager.message_queues[user_id]) == len(test_messages), "Not all messages were queued"
    
    # 模拟用户重新连接
    websocket = MockWebSocket()
    success = await manager.connect(user_id, websocket, room_id)
    assert success, "Failed to reconnect user"
    
    # 验证连接恢复
    assert manager.is_user_online(user_id), "User should be online after reconnection"
    assert manager.get_user_room(user_id) == room_id, "User should be in the correct room"
    
    # 验证离线消息被发送
    # 连接时会发送连接确认消息 + 排队的消息
    expected_message_count = 1 + len(test_messages)  # 1 for connection_established
    assert len(websocket.messages_sent) >= len(test_messages), "Queued messages were not delivered"
    
    # 验证排队的消息内容
    delivered_test_messages = []
    for message_str in websocket.messages_sent:
        message = json.loads(message_str)
        if message.get("type") == "test_message":
            delivered_test_messages.append(message)
    
    assert len(delivered_test_messages) == len(test_messages), "Not all queued messages were delivered"
    
    # 验证消息顺序和内容
    for i, (original, delivered) in enumerate(zip(test_messages, delivered_test_messages)):
        assert delivered["type"] == original["type"], f"Message {i} type mismatch"
        assert delivered["data"]["scenario"] == original["data"]["scenario"], f"Message {i} scenario mismatch"
        assert delivered["data"]["index"] == original["data"]["index"], f"Message {i} index mismatch"
    
    # 验证消息队列被清空
    assert user_id not in manager.message_queues or len(manager.message_queues[user_id]) == 0, "Message queue not cleared after delivery"


class WebSocketStateMachine(RuleBasedStateMachine):
    """
    状态机测试WebSocket连接管理的复杂场景
    """
    
    def __init__(self):
        super().__init__()
        self.manager = ConnectionManager()
        self.websockets: Dict[str, MockWebSocket] = {}
        self.connected_users: set = set()
        self.room_assignments: Dict[str, str] = {}
    
    @initialize()
    def setup(self):
        """初始化状态机"""
        self.manager = ConnectionManager()
        self.websockets.clear()
        self.connected_users.clear()
        self.room_assignments.clear()
    
    @rule(
        user_id=user_id_strategy,
        room_id=room_id_strategy
    )
    async def connect_user(self, user_id, room_id):
        """连接用户到房间"""
        if user_id not in self.connected_users:
            websocket = MockWebSocket()
            self.websockets[user_id] = websocket
            
            success = await self.manager.connect(user_id, websocket, room_id)
            if success:
                self.connected_users.add(user_id)
                self.room_assignments[user_id] = room_id
    
    @rule(user_id=user_id_strategy)
    async def disconnect_user(self, user_id):
        """断开用户连接"""
        if user_id in self.connected_users:
            await self.manager.disconnect(user_id)
            self.connected_users.discard(user_id)
            if user_id in self.room_assignments:
                del self.room_assignments[user_id]
    
    @rule(
        room_id=room_id_strategy,
        message_content=message_content_strategy
    )
    async def broadcast_message(self, room_id, message_content):
        """向房间广播消息"""
        message = {
            "type": "test_broadcast",
            "data": {"content": message_content}
        }
        await self.manager.broadcast_to_room(room_id, message)
    
    @invariant()
    def connection_consistency(self):
        """验证连接状态的一致性"""
        # 验证连接管理器的状态与我们的跟踪状态一致
        manager_connections = set(self.manager.active_connections.keys())
        assert manager_connections == self.connected_users, "Connection state inconsistency"
        
        # 验证房间分配的一致性
        for user_id, room_id in self.room_assignments.items():
            assert self.manager.get_user_room(user_id) == room_id, f"Room assignment inconsistency for user {user_id}"
    
    @invariant()
    def room_membership_consistency(self):
        """验证房间成员关系的一致性"""
        # 验证每个房间的成员都是已连接的用户
        for room_id, users in self.manager.room_connections.items():
            for user_id in users:
                assert user_id in self.connected_users, f"Disconnected user {user_id} found in room {room_id}"
        
        # 验证每个已连接用户的房间分配
        for user_id in self.connected_users:
            if user_id in self.room_assignments:
                room_id = self.room_assignments[user_id]
                room_users = self.manager.get_room_users(room_id)
                assert user_id in room_users, f"User {user_id} not found in assigned room {room_id}"


# 运行状态机测试
TestWebSocketStateMachine = WebSocketStateMachine.TestCase


@pytest.mark.asyncio
async def test_connection_manager_basic_functionality():
    """基本功能测试，确保连接管理器工作正常"""
    manager = ConnectionManager()
    
    # 测试初始状态
    assert manager.get_connection_count() == 0
    assert manager.get_room_count() == 0
    
    # 测试连接
    websocket = MockWebSocket()
    success = await manager.connect("test_user", websocket, "test_room")
    assert success
    assert manager.get_connection_count() == 1
    assert manager.get_room_count() == 1
    assert manager.is_user_online("test_user")
    assert manager.get_user_room("test_user") == "test_room"
    
    # 测试断开连接
    await manager.disconnect("test_user")
    assert manager.get_connection_count() == 0
    assert manager.get_room_count() == 0
    assert not manager.is_user_online("test_user")
    assert manager.get_user_room("test_user") is None


@pytest.mark.asyncio
async def test_message_queue_functionality():
    """测试消息队列功能"""
    manager = ConnectionManager()
    
    # 向离线用户发送消息
    test_message = {"type": "test", "data": {"content": "test message"}}
    success = await manager.send_to_user("offline_user", test_message)
    assert not success  # 应该失败，因为用户离线
    
    # 验证消息被排队
    assert "offline_user" in manager.message_queues
    assert len(manager.message_queues["offline_user"]) == 1
    
    # 用户上线
    websocket = MockWebSocket()
    await manager.connect("offline_user", websocket)
    
    # 验证消息被发送
    assert len(websocket.messages_sent) >= 1  # 至少有连接确认消息
    
    # 验证队列被清空
    assert "offline_user" not in manager.message_queues or len(manager.message_queues["offline_user"]) == 0


# 聊天权限属性测试
# Chat permission property tests

@pytest.mark.asyncio
@given(
    room_id=room_id_strategy,
    user_id=user_id_strategy,
    game_phase=st.sampled_from(['waiting', 'starting', 'discussion', 'voting', 'result', 'finished']),
    message_content=message_content_strategy
)
@settings(max_examples=100, deadline=5000)
async def test_property_30_chat_phase_restrictions(room_id, user_id, game_phase, message_content):
    """
    Feature: undercover-game-platform, Property 30: 聊天阶段限制
    验证需求: 需求 7.2
    
    属性 30: 聊天阶段限制
    对于任何游戏阶段，系统应该根据当前阶段正确限制或允许玩家聊天
    """
    from app.websocket.chat_manager import ChatManager, GamePhase
    
    # 创建聊天管理器
    chat_manager = ChatManager()
    
    # 设置房间游戏阶段
    phase_enum = GamePhase(game_phase)
    chat_manager.set_room_phase(room_id, phase_enum)
    
    # 检查是否可以发送消息
    can_send, error_msg = chat_manager.can_send_message(room_id, user_id)
    
    # 验证阶段限制规则
    if game_phase == 'voting':
        # 投票阶段应该禁止聊天
        assert not can_send, f"Chat should be restricted during voting phase, but got can_send={can_send}"
        assert "投票阶段禁止聊天" in error_msg, f"Expected voting restriction message, got: {error_msg}"
    
    elif game_phase == 'result':
        # 结果阶段应该禁止聊天
        assert not can_send, f"Chat should be restricted during result phase, but got can_send={can_send}"
        assert "结果公布阶段禁止聊天" in error_msg, f"Expected result restriction message, got: {error_msg}"
    
    elif game_phase in ['waiting', 'starting', 'discussion', 'finished']:
        # 这些阶段应该允许聊天（除非有其他限制）
        # 注意：这里只测试阶段限制，不考虑其他限制如用户权限、频率限制等
        # 如果不能发送，应该不是因为阶段限制
        if not can_send:
            assert "阶段禁止聊天" not in error_msg, f"Phase {game_phase} should allow chat, but got restriction: {error_msg}"
    
    # 验证阶段设置正确
    assert chat_manager.get_room_phase(room_id) == phase_enum, "Room phase not set correctly"


@pytest.mark.asyncio
@given(
    room_id=room_id_strategy,
    user_id=user_id_strategy,
    is_eliminated=st.booleans(),
    message_content=message_content_strategy
)
@settings(max_examples=100, deadline=5000)
async def test_property_31_eliminated_player_permission_management(room_id, user_id, is_eliminated, message_content):
    """
    Feature: undercover-game-platform, Property 31: 淘汰玩家权限管理
    验证需求: 需求 7.3
    
    属性 31: 淘汰玩家权限管理
    对于任何被淘汰的玩家，系统应该限制其发言权限但保留观战权限
    """
    from app.websocket.chat_manager import ChatManager, GamePhase, ChatPermission
    
    # 创建聊天管理器
    chat_manager = ChatManager()
    
    # 设置房间为讨论阶段（允许聊天的阶段）
    chat_manager.set_room_phase(room_id, GamePhase.DISCUSSION)
    
    if is_eliminated:
        # 淘汰玩家
        chat_manager.eliminate_player(room_id, user_id)
        
        # 验证玩家被标记为淘汰
        assert chat_manager.is_player_eliminated(room_id, user_id), "Player should be marked as eliminated"
        
        # 验证权限被设置为观察者
        permission = chat_manager.get_user_permission(user_id)
        assert permission == ChatPermission.OBSERVER, f"Eliminated player should have OBSERVER permission, got {permission}"
        
        # 验证不能发送消息
        can_send, error_msg = chat_manager.can_send_message(room_id, user_id)
        assert not can_send, "Eliminated player should not be able to send messages"
        assert "观察者无法发送消息" in error_msg, f"Expected observer restriction message, got: {error_msg}"
        
        # 验证处理消息时返回错误
        result = chat_manager.process_message(room_id, user_id, message_content)
        assert not result["success"], "Message processing should fail for eliminated player"
        assert result["error"] == "观察者无法发送消息", f"Expected observer error, got: {result['error']}"
        assert result["message"] is None, "No message should be created for eliminated player"
    
    else:
        # 非淘汰玩家
        # 验证玩家未被标记为淘汰
        assert not chat_manager.is_player_eliminated(room_id, user_id), "Player should not be marked as eliminated"
        
        # 验证权限为完全权限（默认）
        permission = chat_manager.get_user_permission(user_id)
        assert permission == ChatPermission.FULL, f"Non-eliminated player should have FULL permission, got {permission}"
        
        # 验证可以发送消息（在讨论阶段）
        can_send, error_msg = chat_manager.can_send_message(room_id, user_id)
        # 注意：这里可能因为其他限制（如频率限制）而失败，但不应该因为权限问题失败
        if not can_send:
            assert "观察者无法发送消息" not in error_msg, f"Non-eliminated player should not have observer restriction: {error_msg}"


@pytest.mark.asyncio
@given(
    room_id=room_id_strategy,
    user_id=user_id_strategy,
    message_content=st.text(min_size=1, max_size=300),
    contains_banned_words=st.booleans()
)
@settings(max_examples=100, deadline=5000)
async def test_property_32_content_filtering_mechanism(room_id, user_id, message_content, contains_banned_words):
    """
    Feature: undercover-game-platform, Property 32: 内容过滤机制
    验证需求: 需求 7.4
    
    属性 32: 内容过滤机制
    对于任何检测到的不当言论，系统应该过滤内容或发出警告
    """
    from app.websocket.chat_manager import ChatManager, GamePhase
    
    # 创建聊天管理器
    chat_manager = ChatManager()
    
    # 设置房间为讨论阶段（允许聊天的阶段）
    chat_manager.set_room_phase(room_id, GamePhase.DISCUSSION)
    
    # 如果需要包含敏感词，添加一些敏感词到消息中
    if contains_banned_words and message_content.strip():
        # 从敏感词列表中随机选择一个词添加到消息中
        banned_word = "卧底"  # 使用一个确定的敏感词
        message_content = f"{message_content} {banned_word}"
    
    # 测试内容过滤
    filtered_content, detected_banned = chat_manager.filter_message_content(message_content)
    
    # 验证过滤结果
    if contains_banned_words and message_content.strip():
        # 应该检测到敏感词
        assert detected_banned, f"Should detect banned words in message: {message_content}"
        
        # 敏感词应该被替换为星号
        assert "卧底" not in filtered_content, f"Banned word should be filtered out: {filtered_content}"
        assert "*" in filtered_content, f"Banned word should be replaced with asterisks: {filtered_content}"
    
    else:
        # 如果消息为空或不包含敏感词，应该不检测到敏感词
        if message_content.strip():  # 非空消息
            # 检查是否意外包含了敏感词
            has_banned = any(banned in message_content for banned in chat_manager.banned_words)
            assert detected_banned == has_banned, f"Banned word detection mismatch for message: {message_content}"
    
    # 验证长度限制
    if len(message_content) > chat_manager.max_message_length:
        assert len(filtered_content) <= chat_manager.max_message_length + 3, "Message should be truncated with '...'"
        assert filtered_content.endswith("..."), "Long message should end with '...'"
    
    # 验证特殊字符过滤
    dangerous_chars = ['<', '>', '"', "'"]
    for char in dangerous_chars:
        assert char not in filtered_content, f"Dangerous character '{char}' should be filtered out"
    
    # 测试完整的消息处理流程
    if message_content.strip():  # 只测试非空消息
        result = chat_manager.process_message(room_id, user_id, message_content)
        
        if result["success"]:
            # 如果处理成功，验证消息内容
            processed_message = result["message"]
            assert processed_message is not None, "Processed message should not be None"
            assert processed_message["content"] == filtered_content, "Processed message content should match filtered content"
            assert processed_message["filtered"] == detected_banned, "Filtered flag should match detection result"
            
            # 如果包含敏感词，应该有警告
            if detected_banned:
                assert result["warning"] is not None, "Should have warning for filtered content"
                assert "敏感词" in result["warning"], f"Warning should mention filtered words: {result['warning']}"
            else:
                # 如果没有敏感词，不应该有过滤警告
                if result["warning"]:
                    assert "敏感词" not in result["warning"], f"Should not have filtering warning for clean content: {result['warning']}"