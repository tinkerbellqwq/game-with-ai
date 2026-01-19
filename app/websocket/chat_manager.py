"""
聊天管理器
管理游戏内聊天、消息过滤和权限控制
"""

import re
import logging
from typing import Dict, Set, Optional, List, Any
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class GamePhase(Enum):
    """游戏阶段枚举"""
    WAITING = "waiting"
    STARTING = "starting"
    DISCUSSION = "discussion"
    VOTING = "voting"
    RESULT = "result"
    FINISHED = "finished"


class ChatPermission(Enum):
    """聊天权限枚举"""
    FULL = "full"          # 完全聊天权限
    RESTRICTED = "restricted"  # 受限聊天权限
    OBSERVER = "observer"  # 观察者权限（只能观看）
    BANNED = "banned"      # 被禁言


class ChatManager:
    """
    聊天管理器
    负责管理游戏内聊天、消息过滤和权限控制
    验证需求: 需求 7.2, 7.3, 7.4
    """
    
    def __init__(self):
        # 房间游戏阶段: room_id -> GamePhase
        self.room_phases: Dict[str, GamePhase] = {}
        
        # 用户聊天权限: user_id -> ChatPermission
        self.user_permissions: Dict[str, ChatPermission] = {}
        
        # 淘汰玩家: room_id -> Set[user_id]
        self.eliminated_players: Dict[str, Set[str]] = {}
        
        # 房间静音状态: room_id -> bool
        self.muted_rooms: Dict[str, bool] = {}
        
        # 房间管理员: room_id -> Set[user_id]
        self.room_moderators: Dict[str, Set[str]] = {}
        
        # 敏感词过滤列表
        self.banned_words = [
            "卧底", "平民", "词汇", "答案", "我是", "他是", "她是",
            "作弊", "外挂", "透题", "剧透"
        ]
        
        # 消息历史: room_id -> List[message]
        self.message_history: Dict[str, List[Dict[str, Any]]] = {}
        
        # 消息限制配置
        self.max_message_length = 200
        self.max_messages_per_minute = 10
        self.message_cooldown = 2  # 秒
        
        # 用户消息计数: user_id -> List[timestamp]
        self.user_message_counts: Dict[str, List[datetime]] = {}
        
        # 用户最后消息时间: user_id -> datetime
        self.user_last_message: Dict[str, datetime] = {}
    
    def set_room_phase(self, room_id: str, phase: GamePhase) -> None:
        """
        设置房间游戏阶段
        验证需求: 需求 7.2 - 当游戏进行中时，系统应根据游戏阶段限制或允许聊天
        """
        self.room_phases[room_id] = phase
        logger.info(f"Room {room_id} phase set to {phase.value}")
    
    def get_room_phase(self, room_id: str) -> GamePhase:
        """获取房间游戏阶段"""
        return self.room_phases.get(room_id, GamePhase.WAITING)
    
    def set_user_permission(self, user_id: str, permission: ChatPermission) -> None:
        """设置用户聊天权限"""
        self.user_permissions[user_id] = permission
        logger.info(f"User {user_id} chat permission set to {permission.value}")
    
    def get_user_permission(self, user_id: str) -> ChatPermission:
        """获取用户聊天权限"""
        return self.user_permissions.get(user_id, ChatPermission.FULL)
    
    def eliminate_player(self, room_id: str, user_id: str) -> None:
        """
        淘汰玩家
        验证需求: 需求 7.3 - 当玩家被淘汰时，系统应限制其继续发言但允许观战
        """
        if room_id not in self.eliminated_players:
            self.eliminated_players[room_id] = set()
        
        self.eliminated_players[room_id].add(user_id)
        self.set_user_permission(user_id, ChatPermission.OBSERVER)
        
        logger.info(f"Player {user_id} eliminated in room {room_id}")
    
    def is_player_eliminated(self, room_id: str, user_id: str) -> bool:
        """检查玩家是否被淘汰"""
        return user_id in self.eliminated_players.get(room_id, set())
    
    def mute_room(self, room_id: str, muted: bool = True) -> None:
        """设置房间静音状态"""
        self.muted_rooms[room_id] = muted
        logger.info(f"Room {room_id} {'muted' if muted else 'unmuted'}")
    
    def is_room_muted(self, room_id: str) -> bool:
        """检查房间是否被静音"""
        return self.muted_rooms.get(room_id, False)
    
    def add_moderator(self, room_id: str, user_id: str) -> None:
        """添加房间管理员"""
        if room_id not in self.room_moderators:
            self.room_moderators[room_id] = set()
        
        self.room_moderators[room_id].add(user_id)
        logger.info(f"User {user_id} added as moderator in room {room_id}")
    
    def is_moderator(self, room_id: str, user_id: str) -> bool:
        """检查用户是否为房间管理员"""
        return user_id in self.room_moderators.get(room_id, set())
    
    def can_send_message(self, room_id: str, user_id: str) -> tuple[bool, str]:
        """
        检查用户是否可以发送消息
        验证需求: 需求 7.2, 7.3 - 游戏阶段限制和淘汰玩家权限管理
        
        Returns:
            tuple[bool, str]: (是否可以发送, 错误信息)
        """
        # 检查用户权限
        permission = self.get_user_permission(user_id)
        if permission == ChatPermission.BANNED:
            return False, "您已被禁言"
        
        if permission == ChatPermission.OBSERVER:
            return False, "观察者无法发送消息"
        
        # 检查房间是否静音
        if self.is_room_muted(room_id) and not self.is_moderator(room_id, user_id):
            return False, "房间已被静音"
        
        # 检查游戏阶段限制
        phase = self.get_room_phase(room_id)
        if phase == GamePhase.VOTING:
            return False, "投票阶段禁止聊天"
        
        if phase == GamePhase.RESULT:
            return False, "结果公布阶段禁止聊天"
        
        # 检查消息频率限制
        current_time = datetime.now()
        
        # 检查冷却时间
        if user_id in self.user_last_message:
            time_since_last = (current_time - self.user_last_message[user_id]).total_seconds()
            if time_since_last < self.message_cooldown:
                return False, f"请等待 {self.message_cooldown - time_since_last:.1f} 秒后再发送消息"
        
        # 检查每分钟消息数限制
        if user_id not in self.user_message_counts:
            self.user_message_counts[user_id] = []
        
        # 清理一分钟前的消息记录
        one_minute_ago = current_time.timestamp() - 60
        self.user_message_counts[user_id] = [
            msg_time for msg_time in self.user_message_counts[user_id]
            if msg_time.timestamp() > one_minute_ago
        ]
        
        if len(self.user_message_counts[user_id]) >= self.max_messages_per_minute:
            return False, "发送消息过于频繁，请稍后再试"
        
        return True, ""
    
    def filter_message_content(self, content: str) -> tuple[str, bool]:
        """
        过滤消息内容
        验证需求: 需求 7.4 - 当检测到不当言论时，系统应过滤或警告相关内容
        
        Returns:
            tuple[str, bool]: (过滤后的内容, 是否包含敏感词)
        """
        if not content or len(content.strip()) == 0:
            return "", False
        
        # 长度限制
        if len(content) > self.max_message_length:
            content = content[:self.max_message_length] + "..."
        
        original_content = content
        contains_banned_words = False
        
        # 敏感词过滤
        for banned_word in self.banned_words:
            if banned_word in content:
                contains_banned_words = True
                # 用星号替换敏感词
                content = content.replace(banned_word, "*" * len(banned_word))
        
        # 过滤特殊字符和潜在的恶意内容
        content = re.sub(r'[<>"\']', '', content)  # 移除可能的HTML/脚本字符
        content = re.sub(r'\s+', ' ', content)     # 规范化空白字符
        content = content.strip()
        
        if contains_banned_words:
            logger.warning(f"Message contains banned words: {original_content}")
        
        return content, contains_banned_words
    
    def process_message(self, room_id: str, user_id: str, content: str) -> Dict[str, Any]:
        """
        处理聊天消息
        验证需求: 需求 7.1, 7.2, 7.3, 7.4 - 完整的聊天消息处理流程
        
        Returns:
            Dict: 处理结果，包含是否成功、消息内容、错误信息等
        """
        # 检查发送权限
        can_send, error_msg = self.can_send_message(room_id, user_id)
        if not can_send:
            return {
                "success": False,
                "error": error_msg,
                "message": None
            }
        
        # 过滤消息内容
        filtered_content, contains_banned = self.filter_message_content(content)
        
        if not filtered_content:
            return {
                "success": False,
                "error": "消息内容为空",
                "message": None
            }
        
        # 创建消息对象
        current_time = datetime.now()
        message = {
            "id": f"{room_id}_{user_id}_{int(current_time.timestamp() * 1000)}",
            "room_id": room_id,
            "sender_id": user_id,
            "content": filtered_content,
            "timestamp": current_time.isoformat(),
            "type": "chat_message",
            "filtered": contains_banned,
            "is_eliminated": self.is_player_eliminated(room_id, user_id),
            "is_moderator": self.is_moderator(room_id, user_id)
        }
        
        # 更新用户消息统计
        self.user_last_message[user_id] = current_time
        if user_id not in self.user_message_counts:
            self.user_message_counts[user_id] = []
        self.user_message_counts[user_id].append(current_time)
        
        # 保存消息历史
        if room_id not in self.message_history:
            self.message_history[room_id] = []
        
        self.message_history[room_id].append(message)
        
        # 限制消息历史长度
        if len(self.message_history[room_id]) > 100:
            self.message_history[room_id] = self.message_history[room_id][-100:]
        
        logger.info(f"Message processed: {user_id} in {room_id}")
        
        return {
            "success": True,
            "error": None,
            "message": message,
            "warning": "消息包含敏感词已被过滤" if contains_banned else None
        }
    
    def get_message_history(self, room_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取房间消息历史"""
        messages = self.message_history.get(room_id, [])
        return messages[-limit:] if limit > 0 else messages
    
    def clear_room_data(self, room_id: str) -> None:
        """清理房间相关数据"""
        self.room_phases.pop(room_id, None)
        self.eliminated_players.pop(room_id, None)
        self.muted_rooms.pop(room_id, None)
        self.room_moderators.pop(room_id, None)
        self.message_history.pop(room_id, None)
        
        logger.info(f"Cleared chat data for room {room_id}")
    
    def get_room_stats(self, room_id: str) -> Dict[str, Any]:
        """获取房间聊天统计信息"""
        messages = self.message_history.get(room_id, [])
        eliminated = self.eliminated_players.get(room_id, set())
        moderators = self.room_moderators.get(room_id, set())
        
        return {
            "room_id": room_id,
            "phase": self.get_room_phase(room_id).value,
            "is_muted": self.is_room_muted(room_id),
            "message_count": len(messages),
            "eliminated_players": list(eliminated),
            "moderators": list(moderators),
            "last_message_time": messages[-1]["timestamp"] if messages else None
        }


# 全局聊天管理器实例
chat_manager = ChatManager()