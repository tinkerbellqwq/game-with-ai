"""
WebSocket连接管理器
管理用户WebSocket连接、消息路由和房间广播
"""

import json
import logging
import asyncio
from typing import Dict, Set, Optional, List, Any
from datetime import datetime
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    WebSocket连接管理器
    负责管理用户连接、消息路由和房间广播
    验证需求: 需求 7.1, 7.5
    """
    
    def __init__(self):
        # 活跃连接: user_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        
        # 房间连接映射: room_id -> Set[user_id]
        self.room_connections: Dict[str, Set[str]] = {}
        
        # 用户房间映射: user_id -> room_id
        self.user_rooms: Dict[str, str] = {}
        
        # 连接元数据: user_id -> connection_info
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        
        # 消息队列用于离线用户
        self.message_queues: Dict[str, List[Any]] = {}
        
        # 连接限制 - 使用默认值避免循环导入
        self.max_connections = 50
        
        # 心跳配置
        self.ping_interval = 20
        self.ping_timeout = 10
        
        # 心跳任务
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}
    
    async def connect(self, user_id: str, websocket: WebSocket, room_id: Optional[str] = None) -> bool:
        """
        建立WebSocket连接
        验证需求: 需求 7.1 - WebSocket连接管理
        """
        try:
            # 检查连接数限制
            if len(self.active_connections) >= self.max_connections:
                logger.warning(f"Connection limit reached, rejecting user {user_id}")
                return False
            
            # 接受WebSocket连接
            await websocket.accept()
            
            # 如果用户已有连接，先断开旧连接
            if user_id in self.active_connections:
                await self.disconnect(user_id, "New connection established")
            
            # 存储连接
            self.active_connections[user_id] = websocket
            
            # 存储连接元数据
            self.connection_metadata[user_id] = {
                "connected_at": datetime.now(),
                "last_ping": datetime.now(),
                "room_id": room_id
            }
            
            # 如果指定了房间，加入房间
            if room_id:
                await self.join_room(user_id, room_id)
            
            # 启动心跳监控
            self._start_heartbeat(user_id)
            
            # 发送离线消息队列
            await self._send_queued_messages(user_id)
            
            logger.info(f"User {user_id} connected to WebSocket" + (f" in room {room_id}" if room_id else ""))
            return True
            
        except Exception as e:
            logger.error(f"Error connecting user {user_id}: {e}")
            return False
    
    async def disconnect(self, user_id: str, reason: str = "Connection closed") -> None:
        """
        断开WebSocket连接
        验证需求: 需求 7.1 - WebSocket连接管理
        """
        try:
            # 停止心跳任务
            if user_id in self._heartbeat_tasks:
                self._heartbeat_tasks[user_id].cancel()
                del self._heartbeat_tasks[user_id]
            
            # 从房间中移除
            if user_id in self.user_rooms:
                room_id = self.user_rooms[user_id]
                await self.leave_room(user_id, room_id)
            
            # 关闭WebSocket连接
            if user_id in self.active_connections:
                websocket = self.active_connections[user_id]
                try:
                    await websocket.close(code=1000, reason=reason)
                except:
                    pass  # 连接可能已经关闭
                
                del self.active_connections[user_id]
            
            # 清理元数据
            self.connection_metadata.pop(user_id, None)
            
            logger.info(f"User {user_id} disconnected: {reason}")
            
        except Exception as e:
            logger.error(f"Error disconnecting user {user_id}: {e}")
    
    async def join_room(self, user_id: str, room_id: str) -> bool:
        """
        用户加入房间
        验证需求: 需求 7.1 - 房间消息路由
        """
        try:
            # 检查用户是否已连接
            if user_id not in self.active_connections:
                logger.warning(f"User {user_id} not connected, cannot join room {room_id}")
                return False
            
            # 如果用户已在其他房间，先离开
            if user_id in self.user_rooms:
                old_room_id = self.user_rooms[user_id]
                if old_room_id != room_id:
                    await self.leave_room(user_id, old_room_id)
            
            # 加入新房间
            if room_id not in self.room_connections:
                self.room_connections[room_id] = set()
            
            self.room_connections[room_id].add(user_id)
            self.user_rooms[user_id] = room_id
            
            # 更新连接元数据
            if user_id in self.connection_metadata:
                self.connection_metadata[user_id]["room_id"] = room_id
            
            # 通知房间其他用户
            await self.broadcast_to_room(room_id, {
                "type": "user_joined",
                "data": {
                    "user_id": user_id,
                    "timestamp": datetime.now().isoformat()
                }
            }, exclude_user=user_id)
            
            logger.info(f"User {user_id} joined room {room_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error joining room {room_id} for user {user_id}: {e}")
            return False
    
    async def leave_room(self, user_id: str, room_id: str) -> bool:
        """
        用户离开房间
        验证需求: 需求 7.1 - 房间消息路由
        """
        try:
            # 从房间中移除用户
            if room_id in self.room_connections:
                self.room_connections[room_id].discard(user_id)
                
                # 如果房间为空，清理房间
                if not self.room_connections[room_id]:
                    del self.room_connections[room_id]
                    
                    # 清理聊天管理器中的房间数据
                    try:
                        from app.websocket.chat_manager import chat_manager
                        chat_manager.clear_room_data(room_id)
                    except ImportError:
                        pass
            
            # 更新用户房间映射
            if user_id in self.user_rooms and self.user_rooms[user_id] == room_id:
                del self.user_rooms[user_id]
            
            # 更新连接元数据
            if user_id in self.connection_metadata:
                self.connection_metadata[user_id]["room_id"] = None
            
            # 通知房间其他用户
            if room_id in self.room_connections:
                await self.broadcast_to_room(room_id, {
                    "type": "user_left",
                    "data": {
                        "user_id": user_id,
                        "timestamp": datetime.now().isoformat()
                    }
                }, exclude_user=user_id)
            
            logger.info(f"User {user_id} left room {room_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error leaving room {room_id} for user {user_id}: {e}")
            return False
    
    async def send_to_user(self, user_id: str, message: dict) -> bool:
        """
        发送消息给特定用户
        验证需求: 需求 7.1 - 消息路由
        """
        try:
            if user_id in self.active_connections:
                websocket = self.active_connections[user_id]
                await websocket.send_text(json.dumps(message))
                return True
            else:
                # 用户不在线，加入消息队列
                if user_id not in self.message_queues:
                    self.message_queues[user_id] = []
                
                self.message_queues[user_id].append({
                    **message,
                    "queued_at": datetime.now().isoformat()
                })
                
                # 限制队列长度
                if len(self.message_queues[user_id]) > 100:
                    self.message_queues[user_id] = self.message_queues[user_id][-100:]
                
                logger.debug(f"Message queued for offline user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending message to user {user_id}: {e}")
            return False
    
    async def broadcast_to_room(self, room_id: str, message: dict, exclude_user: Optional[str] = None) -> int:
        """
        广播消息到房间所有用户
        验证需求: 需求 7.1 - 当玩家发送消息时，系统应立即广播给房间内所有玩家
        """
        sent_count = 0

        try:
            if room_id in self.room_connections:
                users_in_room = self.room_connections[room_id].copy()
                logger.info(f"[BROADCAST] Room {room_id} has {len(users_in_room)} users: {users_in_room}")

                for user_id in users_in_room:
                    if exclude_user and user_id == exclude_user:
                        continue

                    success = await self.send_to_user(user_id, message)
                    if success:
                        sent_count += 1
            else:
                logger.warning(f"[BROADCAST] Room {room_id} not found in room_connections. Available rooms: {list(self.room_connections.keys())}")

            logger.info(f"[BROADCAST] Sent message type '{message.get('type', 'unknown')}' to {sent_count} users in room {room_id}")
            return sent_count

        except Exception as e:
            logger.error(f"Error broadcasting to room {room_id}: {e}")
            return sent_count
    
    async def _send_queued_messages(self, user_id: str) -> None:
        """发送排队的离线消息"""
        try:
            if user_id in self.message_queues:
                messages = self.message_queues[user_id]
                
                for message in messages:
                    await self.send_to_user(user_id, message)
                
                # 清空消息队列
                del self.message_queues[user_id]
                
                logger.info(f"Sent {len(messages)} queued messages to user {user_id}")
                
        except Exception as e:
            logger.error(f"Error sending queued messages to user {user_id}: {e}")
    
    def _start_heartbeat(self, user_id: str) -> None:
        """启动心跳监控"""
        async def heartbeat_task():
            try:
                while user_id in self.active_connections:
                    await asyncio.sleep(self.ping_interval)

                    if user_id not in self.active_connections:
                        break

                    # 先检查上次心跳响应时间（在发送新ping之前检查）
                    if user_id in self.connection_metadata:
                        last_pong = self.connection_metadata[user_id].get("last_ping")
                        if last_pong:
                            time_since_pong = (datetime.now() - last_pong).total_seconds()
                            # 如果超过 3 个心跳周期没有响应，断开连接
                            if time_since_pong > self.ping_interval * 3:
                                logger.warning(f"User {user_id} heartbeat timeout ({time_since_pong:.1f}s), disconnecting")
                                await self.disconnect(user_id, "Heartbeat timeout")
                                break

                    # 发送心跳
                    await self.send_to_user(user_id, {
                        "type": "ping",
                        "data": {"timestamp": datetime.now().isoformat()}
                    })

            except asyncio.CancelledError:
                logger.debug(f"Heartbeat task cancelled for user {user_id}")
            except Exception as e:
                logger.error(f"Heartbeat error for user {user_id}: {e}")
        
        # 取消现有任务
        if user_id in self._heartbeat_tasks:
            self._heartbeat_tasks[user_id].cancel()
        
        # 启动新任务
        self._heartbeat_tasks[user_id] = asyncio.create_task(heartbeat_task())
    
    async def cleanup_inactive_connections(self) -> int:
        """
        清理不活跃的连接
        验证需求: 需求 7.5 - 连接恢复机制
        """
        cleaned_count = 0
        current_time = datetime.now()
        
        try:
            # 检查所有连接
            inactive_users = []
            
            for user_id, metadata in self.connection_metadata.items():
                if user_id not in self.active_connections:
                    inactive_users.append(user_id)
                    continue
                
                # 检查连接是否超时
                last_ping = metadata.get("last_ping")
                if last_ping:
                    time_since_ping = (current_time - last_ping).total_seconds()
                    if time_since_ping > self.ping_timeout * 3:
                        inactive_users.append(user_id)
            
            # 清理不活跃连接
            for user_id in inactive_users:
                await self.disconnect(user_id, "Inactive connection cleanup")
                cleaned_count += 1
            
            logger.info(f"Cleaned up {cleaned_count} inactive connections")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error during connection cleanup: {e}")
            return cleaned_count
    
    def get_connection_count(self) -> int:
        """获取当前连接数"""
        return len(self.active_connections)
    
    def get_room_count(self) -> int:
        """获取当前房间数"""
        return len(self.room_connections)
    
    def get_room_users(self, room_id: str) -> List[str]:
        """获取房间内的用户列表"""
        return list(self.room_connections.get(room_id, set()))
    
    def get_user_room(self, user_id: str) -> Optional[str]:
        """获取用户所在的房间"""
        return self.user_rooms.get(user_id)
    
    def is_user_connected(self, user_id: str) -> bool:
        """检查用户是否已连接"""
        return user_id in self.active_connections


# 全局连接管理器实例
connection_manager = ConnectionManager()