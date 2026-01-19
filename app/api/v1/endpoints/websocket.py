"""
WebSocket endpoints
WebSocket连接端点
"""

import json
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket.connection_manager import connection_manager
from app.services.auth import AuthService

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_user_from_websocket_token(websocket: WebSocket, token: Optional[str] = None) -> Optional[str]:
    """
    从WebSocket连接中验证用户身份
    """
    try:
        if not token:
            # 尝试从查询参数获取token
            token = websocket.query_params.get("token")

        if not token:
            logger.warning("No token provided for WebSocket connection")
            return None

        # 验证token并获取用户ID - AuthService 不需要 db 参数
        auth_service = AuthService()
        payload = auth_service.verify_token(token)

        if not payload:
            logger.warning("Invalid token for WebSocket connection")
            return None

        # payload 中包含 sub 字段，即 user_id
        user_id = payload.get("sub")
        if not user_id:
            logger.warning("Token payload missing user_id")
            return None

        return user_id

    except Exception as e:
        logger.error(f"Error verifying WebSocket token: {e}")
        return None


@router.websocket("/{room_id}")
async def websocket_room_endpoint(websocket: WebSocket, room_id: str):
    """
    房间WebSocket连接端点
    验证需求: 需求 7.1, 7.5 - WebSocket连接管理和消息路由
    """
    logger.info(f"[WS_CONNECT] WebSocket connection attempt for room {room_id}")
    user_id = None

    try:
        # 验证用户身份
        logger.info(f"[WS_CONNECT] Verifying user token for room {room_id}")
        user_id = await get_user_from_websocket_token(websocket)
        if not user_id:
            logger.warning(f"[WS_CONNECT] Auth failed for room {room_id}")
            await websocket.close(code=4001, reason="Authentication required")
            return

        logger.info(f"[WS_CONNECT] User {user_id} authenticated for room {room_id}")

        # 建立连接
        connected = await connection_manager.connect(user_id, websocket, room_id)
        if not connected:
            logger.warning(f"[WS_CONNECT] Connection failed for user {user_id} in room {room_id}")
            await websocket.close(code=4002, reason="Connection failed")
            return

        logger.info(f"[WS_CONNECT] User {user_id} connected to room {room_id}")
        
        # 消息处理循环
        while True:
            try:
                # 接收消息
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                # 验证消息格式
                if not isinstance(message_data, dict) or "type" not in message_data:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "data": {"message": "Invalid message format"}
                    }))
                    continue
                
                # 处理不同类型的消息
                await handle_websocket_message(user_id, room_id, message_data)
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for user {user_id} in room {room_id}")
                break
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": {"message": "Invalid JSON format"}
                }))
            except Exception as e:
                logger.error(f"Error handling WebSocket message from user {user_id}: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": {"message": "Internal server error"}
                }))
    
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")

    finally:
        # 清理连接
        if user_id:
            await connection_manager.disconnect(user_id, "Connection closed")
            # 注意：这里只清理 WebSocket 连接，不从数据库房间中移除用户
            # 用户可能只是网络断开，真正的离开房间应通过 API 调用


@router.websocket("/")
async def websocket_general_endpoint(websocket: WebSocket):
    """
    通用WebSocket连接端点（不绑定特定房间）
    验证需求: 需求 7.1, 7.5 - WebSocket连接管理和消息路由
    """
    user_id = None
    
    try:
        # 验证用户身份
        user_id = await get_user_from_websocket_token(websocket)
        if not user_id:
            await websocket.close(code=4001, reason="Authentication required")
            return
        
        # 建立连接（不绑定房间）
        connected = await connection_manager.connect(user_id, websocket)
        if not connected:
            await websocket.close(code=4002, reason="Connection failed")
            return
        
        # 消息处理循环
        while True:
            try:
                # 接收消息
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                # 验证消息格式
                if not isinstance(message_data, dict) or "type" not in message_data:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "data": {"message": "Invalid message format"}
                    }))
                    continue
                
                # 处理不同类型的消息
                await handle_websocket_message(user_id, None, message_data)
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for user {user_id}")
                break
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": {"message": "Invalid JSON format"}
                }))
            except Exception as e:
                logger.error(f"Error handling WebSocket message from user {user_id}: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": {"message": "Internal server error"}
                }))
    
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    
    finally:
        # 清理连接
        if user_id:
            await connection_manager.disconnect(user_id, "Connection closed")


async def handle_websocket_message(user_id: str, room_id: Optional[str], message_data: dict) -> None:
    """
    处理WebSocket消息
    验证需求: 需求 7.1, 7.2, 7.3, 7.4 - 完整的WebSocket消息处理和聊天权限控制
    """
    try:
        message_type = message_data.get("type")
        data = message_data.get("data", {})
        
        if message_type == "ping":
            # 心跳响应
            await connection_manager.send_to_user(user_id, {
                "type": "pong",
                "data": {"timestamp": data.get("timestamp")}
            })

        elif message_type == "pong":
            # 客户端响应心跳，更新 last_ping 时间
            from datetime import datetime
            if user_id in connection_manager.connection_metadata:
                connection_manager.connection_metadata[user_id]["last_ping"] = datetime.now()

        elif message_type == "join_room":
            # 加入房间
            target_room_id = data.get("room_id")
            if target_room_id:
                success = await connection_manager.join_room(user_id, target_room_id)
                await connection_manager.send_to_user(user_id, {
                    "type": "join_room_response",
                    "data": {
                        "success": success,
                        "room_id": target_room_id
                    }
                })
        
        elif message_type == "leave_room":
            # 离开房间
            target_room_id = data.get("room_id") or room_id
            if target_room_id:
                success = await connection_manager.leave_room(user_id, target_room_id)
                await connection_manager.send_to_user(user_id, {
                    "type": "leave_room_response",
                    "data": {
                        "success": success,
                        "room_id": target_room_id
                    }
                })
        
        elif message_type == "chat_message":
            # 聊天消息处理
            if room_id:
                content = data.get("content", "").strip()
                if content:
                    # 使用聊天管理器处理消息
                    from app.websocket.chat_manager import chat_manager
                    
                    result = chat_manager.process_message(room_id, user_id, content)
                    
                    if result["success"]:
                        # 广播处理后的消息到房间
                        processed_message = result["message"]
                        await connection_manager.broadcast_to_room(room_id, {
                            "type": "chat_message",
                            "data": processed_message
                        })
                        
                        # 如果有警告，发送给发送者
                        if result["warning"]:
                            await connection_manager.send_to_user(user_id, {
                                "type": "chat_warning",
                                "data": {"message": result["warning"]}
                            })
                    else:
                        # 发送错误消息给发送者
                        await connection_manager.send_to_user(user_id, {
                            "type": "chat_error",
                            "data": {"message": result["error"]}
                        })
        
        elif message_type == "set_game_phase":
            # 设置游戏阶段（房主或管理员权限）
            if room_id:
                from app.websocket.chat_manager import chat_manager, GamePhase
                
                phase_str = data.get("phase")
                if phase_str:
                    try:
                        phase = GamePhase(phase_str)
                        chat_manager.set_room_phase(room_id, phase)
                        
                        # 广播阶段变更到房间
                        await connection_manager.broadcast_to_room(room_id, {
                            "type": "game_phase_changed",
                            "data": {
                                "phase": phase.value,
                                "changed_by": user_id
                            }
                        })
                    except ValueError:
                        await connection_manager.send_to_user(user_id, {
                            "type": "error",
                            "data": {"message": f"Invalid game phase: {phase_str}"}
                        })
        
        elif message_type == "eliminate_player":
            # 淘汰玩家（游戏逻辑触发）
            if room_id:
                target_user_id = data.get("target_user_id")
                if target_user_id:
                    from app.websocket.chat_manager import chat_manager
                    
                    chat_manager.eliminate_player(room_id, target_user_id)
                    
                    # 广播玩家淘汰信息
                    await connection_manager.broadcast_to_room(room_id, {
                        "type": "player_eliminated",
                        "data": {
                            "eliminated_user_id": target_user_id,
                            "eliminated_by": user_id
                        }
                    })
                    
                    # 通知被淘汰玩家权限变更
                    await connection_manager.send_to_user(target_user_id, {
                        "type": "permission_changed",
                        "data": {
                            "new_permission": "observer",
                            "reason": "eliminated"
                        }
                    })
        
        elif message_type == "mute_room":
            # 房间静音控制（管理员权限）
            if room_id:
                from app.websocket.chat_manager import chat_manager
                
                muted = data.get("muted", True)
                
                # 检查管理员权限
                if chat_manager.is_moderator(room_id, user_id):
                    chat_manager.mute_room(room_id, muted)
                    
                    # 广播房间静音状态变更
                    await connection_manager.broadcast_to_room(room_id, {
                        "type": "room_mute_changed",
                        "data": {
                            "muted": muted,
                            "changed_by": user_id
                        }
                    })
                else:
                    await connection_manager.send_to_user(user_id, {
                        "type": "error",
                        "data": {"message": "权限不足：只有管理员可以静音房间"}
                    })
        
        elif message_type == "set_user_permission":
            # 设置用户聊天权限（管理员权限）
            if room_id:
                from app.websocket.chat_manager import chat_manager, ChatPermission
                
                target_user_id = data.get("target_user_id")
                permission_str = data.get("permission")
                
                if target_user_id and permission_str:
                    # 检查管理员权限
                    if chat_manager.is_moderator(room_id, user_id):
                        try:
                            permission = ChatPermission(permission_str)
                            chat_manager.set_user_permission(target_user_id, permission)
                            
                            # 通知目标用户权限变更
                            await connection_manager.send_to_user(target_user_id, {
                                "type": "permission_changed",
                                "data": {
                                    "new_permission": permission.value,
                                    "changed_by": user_id
                                }
                            })
                            
                            # 通知管理员操作成功
                            await connection_manager.send_to_user(user_id, {
                                "type": "permission_change_success",
                                "data": {
                                    "target_user_id": target_user_id,
                                    "new_permission": permission.value
                                }
                            })
                        except ValueError:
                            await connection_manager.send_to_user(user_id, {
                                "type": "error",
                                "data": {"message": f"Invalid permission: {permission_str}"}
                            })
                    else:
                        await connection_manager.send_to_user(user_id, {
                            "type": "error",
                            "data": {"message": "权限不足：只有管理员可以修改用户权限"}
                        })
        
        elif message_type == "get_message_history":
            # 获取消息历史
            if room_id:
                from app.websocket.chat_manager import chat_manager
                
                limit = data.get("limit", 50)
                messages = chat_manager.get_message_history(room_id, limit)
                
                await connection_manager.send_to_user(user_id, {
                    "type": "message_history",
                    "data": {
                        "room_id": room_id,
                        "messages": messages
                    }
                })
        
        elif message_type == "get_room_stats":
            # 获取房间聊天统计信息
            if room_id:
                from app.websocket.chat_manager import chat_manager
                
                # 检查管理员权限
                if chat_manager.is_moderator(room_id, user_id):
                    stats = chat_manager.get_room_stats(room_id)
                    
                    await connection_manager.send_to_user(user_id, {
                        "type": "room_stats",
                        "data": stats
                    })
                else:
                    await connection_manager.send_to_user(user_id, {
                        "type": "error",
                        "data": {"message": "权限不足：只有管理员可以查看房间统计"}
                    })
        
        elif message_type == "subscribe_leaderboard":
            # 订阅排行榜更新
            from app.services.leaderboard_realtime import leaderboard_realtime_service
            
            await leaderboard_realtime_service.subscribe_to_leaderboard_updates(user_id)
            await connection_manager.send_to_user(user_id, {
                "type": "leaderboard_subscription",
                "data": {"subscribed": True}
            })
        
        elif message_type == "unsubscribe_leaderboard":
            # 取消订阅排行榜更新
            from app.services.leaderboard_realtime import leaderboard_realtime_service
            
            await leaderboard_realtime_service.unsubscribe_from_leaderboard_updates(user_id)
            await connection_manager.send_to_user(user_id, {
                "type": "leaderboard_subscription",
                "data": {"subscribed": False}
            })
        
        elif message_type == "get_live_rank":
            # 获取实时排名信息
            from app.services.leaderboard_realtime import leaderboard_realtime_service
            from app.core.database import db_manager

            async with db_manager.get_session() as db:
                live_rank_data = await leaderboard_realtime_service.get_live_rank_updates(user_id, db)
                await connection_manager.send_to_user(user_id, {
                    "type": "live_rank_update",
                    "data": live_rank_data
                })
        
        elif message_type == "game_action":
            # 游戏动作（发言、投票等）
            if room_id:
                action_type = data.get("action_type")
                action_data = data.get("action_data", {})
                
                # 广播游戏动作到房间
                await connection_manager.broadcast_to_room(room_id, {
                    "type": "game_action",
                    "data": {
                        "sender_id": user_id,
                        "action_type": action_type,
                        "action_data": action_data,
                        "timestamp": message_data.get("timestamp")
                    },
                    "sender_id": user_id
                })
        
        else:
            logger.warning(f"Unknown message type: {message_type} from user {user_id}")
            await connection_manager.send_to_user(user_id, {
                "type": "error",
                "data": {"message": f"Unknown message type: {message_type}"}
            })
    
    except Exception as e:
        logger.error(f"Error handling message type {message_data.get('type')} from user {user_id}: {e}")
        await connection_manager.send_to_user(user_id, {
            "type": "error",
            "data": {"message": "Failed to process message"}
        })


@router.get("/connections/stats")
async def get_connection_stats():
    """
    获取WebSocket连接统计信息
    """
    return {
        "active_connections": connection_manager.get_connection_count(),
        "active_rooms": connection_manager.get_room_count(),
        "max_connections": connection_manager.max_connections
    }


@router.post("/connections/cleanup")
async def cleanup_connections():
    """
    清理不活跃的连接
    """
    cleaned_count = await connection_manager.cleanup_inactive_connections()
    return {
        "message": f"Cleaned up {cleaned_count} inactive connections",
        "cleaned_count": cleaned_count
    }


@router.get("/rooms/{room_id}/users")
async def get_room_users(room_id: str):
    """
    获取房间内的用户列表
    """
    users = connection_manager.get_room_users(room_id)
    return {
        "room_id": room_id,
        "users": users,
        "user_count": len(users)
    }


@router.get("/rooms/{room_id}/chat/stats")
async def get_room_chat_stats(room_id: str):
    """
    获取房间聊天统计信息
    """
    from app.websocket.chat_manager import chat_manager
    
    stats = chat_manager.get_room_stats(room_id)
    return stats


@router.post("/rooms/{room_id}/chat/mute")
async def mute_room_chat(room_id: str, muted: bool = True):
    """
    设置房间聊天静音状态
    """
    from app.websocket.chat_manager import chat_manager
    
    chat_manager.mute_room(room_id, muted)
    
    # 广播状态变更
    await connection_manager.broadcast_to_room(room_id, {
        "type": "room_mute_changed",
        "data": {
            "muted": muted,
            "changed_by": "system"
        }
    })
    
    return {
        "message": f"Room {room_id} {'muted' if muted else 'unmuted'}",
        "room_id": room_id,
        "muted": muted
    }


@router.get("/rooms/{room_id}/chat/history")
async def get_room_chat_history(room_id: str, limit: int = 50):
    """
    获取房间聊天历史
    """
    from app.websocket.chat_manager import chat_manager
    
    messages = chat_manager.get_message_history(room_id, limit)
    return {
        "room_id": room_id,
        "messages": messages,
        "message_count": len(messages)
    }