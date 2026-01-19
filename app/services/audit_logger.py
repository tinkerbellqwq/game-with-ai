"""
Audit logging service
审计日志服务 - 安全的日志记录机制

实现需求:
- 需求 9.5: 数据损坏检测和修复
- 需求 10.5: 安全日志记录（记录关键操作但不泄露敏感信息）
"""

import logging
import json
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

from app.core.redis_client import redis_manager
from app.core.database import db_manager

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """审计事件类型"""
    USER_REGISTER = "user_register"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    ROOM_CREATE = "room_create"
    ROOM_JOIN = "room_join"
    ROOM_LEAVE = "room_leave"
    GAME_START = "game_start"
    GAME_FINISH = "game_finish"
    PLAYER_SPEECH = "player_speech"
    PLAYER_VOTE = "player_vote"
    PLAYER_ELIMINATE = "player_eliminate"
    SCORE_UPDATE = "score_update"
    SECURITY_VIOLATION = "security_violation"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SYSTEM_ERROR = "system_error"
    DATA_CORRUPTION_DETECTED = "data_corruption_detected"
    DATA_REPAIR_ATTEMPTED = "data_repair_attempted"
    DATA_REPAIR_SUCCESS = "data_repair_success"
    DATA_REPAIR_FAILED = "data_repair_failed"
    DATA_ROLLBACK = "data_rollback"


class AuditLogger:
    """审计日志记录器 - 记录关键操作但不泄露敏感信息"""
    
    def __init__(self):
        self.audit_key_prefix = "audit:log:"
        self.audit_ttl = 2592000  # 30天
        self.sensitive_fields = {
            "password", "password_hash", "token", "secret", 
            "api_key", "private_key", "credit_card"
        }
    
    def _sanitize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        清理敏感信息
        
        Args:
            data: 原始数据
            
        Returns:
            Dict: 清理后的数据
        """
        sanitized = {}
        
        for key, value in data.items():
            # 检查是否是敏感字段
            if any(sensitive in key.lower() for sensitive in self.sensitive_fields):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_data(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self._sanitize_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        
        return sanitized
    
    async def log_event(
        self,
        event_type: AuditEventType,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        success: bool = True
    ) -> bool:
        """
        记录审计事件
        
        Args:
            event_type: 事件类型
            user_id: 用户ID
            details: 事件详情
            ip_address: IP地址
            success: 操作是否成功
            
        Returns:
            bool: 记录是否成功
        """
        try:
            # 清理敏感信息
            sanitized_details = self._sanitize_data(details) if details else {}
            
            # 构建审计日志条目
            audit_entry = {
                "event_type": event_type.value,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "ip_address": ip_address,
                "success": success,
                "details": sanitized_details
            }
            
            # 记录到应用日志
            log_message = f"Audit: {event_type.value} - User: {user_id} - Success: {success}"
            if success:
                logger.info(log_message)
            else:
                logger.warning(log_message)
            
            # 保存到Redis（用于快速查询最近的审计日志）
            try:
                redis_client = await redis_manager.get_client()
                audit_key = f"{self.audit_key_prefix}{event_type.value}:{datetime.utcnow().strftime('%Y%m%d')}"
                
                # 使用列表存储当天的审计日志
                await redis_client.lpush(audit_key, json.dumps(audit_entry, default=str))
                await redis_client.expire(audit_key, self.audit_ttl)
                
            except Exception as e:
                logger.error(f"Failed to save audit log to Redis: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
            return False
    
    async def get_user_audit_log(
        self,
        user_id: str,
        event_types: Optional[List[AuditEventType]] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取用户的审计日志
        
        Args:
            user_id: 用户ID
            event_types: 事件类型过滤
            limit: 返回数量限制
            
        Returns:
            List: 审计日志列表
        """
        audit_logs = []
        
        try:
            redis_client = await redis_manager.get_client()
            
            # 获取最近7天的日志
            for days_ago in range(7):
                date_str = (datetime.utcnow() - timedelta(days=days_ago)).strftime('%Y%m%d')
                
                # 如果指定了事件类型，只查询这些类型
                if event_types:
                    keys_to_check = [
                        f"{self.audit_key_prefix}{et.value}:{date_str}"
                        for et in event_types
                    ]
                else:
                    # 查询所有事件类型
                    pattern = f"{self.audit_key_prefix}*:{date_str}"
                    keys_to_check = await redis_client.keys(pattern)
                
                for key in keys_to_check:
                    # 获取列表中的所有日志
                    logs = await redis_client.lrange(key, 0, -1)
                    
                    for log_json in logs:
                        try:
                            log_entry = json.loads(log_json)
                            if log_entry.get("user_id") == user_id:
                                audit_logs.append(log_entry)
                                
                                if len(audit_logs) >= limit:
                                    break
                        except json.JSONDecodeError:
                            continue
                    
                    if len(audit_logs) >= limit:
                        break
                
                if len(audit_logs) >= limit:
                    break
            
            # 按时间戳排序（最新的在前）
            audit_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            return audit_logs[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get user audit log: {e}")
            return []
    
    async def get_security_events(
        self,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取安全相关事件
        
        Args:
            hours: 查询最近多少小时的事件
            limit: 返回数量限制
            
        Returns:
            List: 安全事件列表
        """
        security_events = []
        
        try:
            redis_client = await redis_manager.get_client()
            
            # 安全相关的事件类型
            security_event_types = [
                AuditEventType.SECURITY_VIOLATION,
                AuditEventType.RATE_LIMIT_EXCEEDED,
                AuditEventType.SYSTEM_ERROR
            ]
            
            # 计算需要查询的天数
            days_to_check = (hours // 24) + 1
            
            for days_ago in range(days_to_check):
                date_str = (datetime.utcnow() - timedelta(days=days_ago)).strftime('%Y%m%d')
                
                for event_type in security_event_types:
                    key = f"{self.audit_key_prefix}{event_type.value}:{date_str}"
                    
                    try:
                        logs = await redis_client.lrange(key, 0, -1)
                        
                        for log_json in logs:
                            try:
                                log_entry = json.loads(log_json)
                                
                                # 检查时间范围
                                log_time = datetime.fromisoformat(log_entry.get("timestamp", ""))
                                if (datetime.utcnow() - log_time).total_seconds() <= hours * 3600:
                                    security_events.append(log_entry)
                                    
                                    if len(security_events) >= limit:
                                        break
                            except (json.JSONDecodeError, ValueError):
                                continue
                        
                        if len(security_events) >= limit:
                            break
                    except Exception as e:
                        logger.debug(f"Error reading security events from {key}: {e}")
                        continue
                
                if len(security_events) >= limit:
                    break
            
            # 按时间戳排序（最新的在前）
            security_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            return security_events[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get security events: {e}")
            return []


# 导入timedelta
from datetime import timedelta


class DataIntegrityChecker:
    """数据完整性检查器 - 检测和修复数据损坏"""
    
    def __init__(self):
        self.checksum_key_prefix = "data:checksum:"
        self.backup_key_prefix = "data:backup:"
        self.backup_ttl = 604800  # 7天
    
    def _calculate_checksum(self, data: Dict[str, Any]) -> str:
        """
        计算数据校验和
        
        Args:
            data: 数据字典
            
        Returns:
            str: SHA256校验和
        """
        # 排序键以确保一致性
        sorted_data = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(sorted_data.encode()).hexdigest()
    
    async def store_with_checksum(
        self,
        key: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        存储数据并保存校验和
        
        Args:
            key: 数据键
            data: 数据内容
            ttl: 过期时间（秒）
            
        Returns:
            bool: 存储是否成功
        """
        try:
            redis_client = await redis_manager.get_client()
            
            # 计算校验和
            checksum = self._calculate_checksum(data)
            
            # 存储数据
            data_json = json.dumps(data, default=str)
            if ttl:
                await redis_client.setex(key, ttl, data_json)
            else:
                await redis_client.set(key, data_json)
            
            # 存储校验和
            checksum_key = f"{self.checksum_key_prefix}{key}"
            if ttl:
                await redis_client.setex(checksum_key, ttl, checksum)
            else:
                await redis_client.set(checksum_key, checksum)
            
            # 创建备份
            await self._create_backup(key, data, ttl)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store data with checksum for {key}: {e}")
            return False
    
    async def _create_backup(
        self,
        key: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        创建数据备份
        
        Args:
            key: 原始数据键
            data: 数据内容
            ttl: 过期时间
            
        Returns:
            bool: 备份是否成功
        """
        try:
            redis_client = await redis_manager.get_client()
            
            backup_key = f"{self.backup_key_prefix}{key}"
            backup_data = {
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
                "checksum": self._calculate_checksum(data)
            }
            
            backup_ttl = ttl if ttl else self.backup_ttl
            await redis_client.setex(
                backup_key,
                backup_ttl,
                json.dumps(backup_data, default=str)
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create backup for {key}: {e}")
            return False
    
    async def verify_data_integrity(self, key: str) -> Dict[str, Any]:
        """
        验证数据完整性
        
        Args:
            key: 数据键
            
        Returns:
            Dict: 验证结果
        """
        try:
            redis_client = await redis_manager.get_client()
            
            # 获取数据
            data_json = await redis_client.get(key)
            if not data_json:
                return {
                    "key": key,
                    "status": "not_found",
                    "is_valid": False,
                    "error": "数据不存在"
                }
            
            # 获取存储的校验和
            checksum_key = f"{self.checksum_key_prefix}{key}"
            stored_checksum = await redis_client.get(checksum_key)
            
            if not stored_checksum:
                return {
                    "key": key,
                    "status": "no_checksum",
                    "is_valid": False,
                    "error": "校验和不存在"
                }
            
            # 解析数据并计算当前校验和
            try:
                data = json.loads(data_json)
                current_checksum = self._calculate_checksum(data)
            except json.JSONDecodeError:
                return {
                    "key": key,
                    "status": "corrupted",
                    "is_valid": False,
                    "error": "数据格式损坏"
                }
            
            # 比较校验和
            if current_checksum == stored_checksum:
                return {
                    "key": key,
                    "status": "valid",
                    "is_valid": True,
                    "checksum": current_checksum
                }
            else:
                # 记录数据损坏事件
                await audit_logger.log_event(
                    event_type=AuditEventType.DATA_CORRUPTION_DETECTED,
                    details={
                        "key": key,
                        "stored_checksum": stored_checksum,
                        "current_checksum": current_checksum
                    }
                )
                
                return {
                    "key": key,
                    "status": "corrupted",
                    "is_valid": False,
                    "error": "数据校验和不匹配",
                    "stored_checksum": stored_checksum,
                    "current_checksum": current_checksum
                }
                
        except Exception as e:
            logger.error(f"Failed to verify data integrity for {key}: {e}")
            return {
                "key": key,
                "status": "error",
                "is_valid": False,
                "error": str(e)
            }
    
    async def repair_data(self, key: str) -> Dict[str, Any]:
        """
        尝试修复损坏的数据
        
        Args:
            key: 数据键
            
        Returns:
            Dict: 修复结果
        """
        try:
            redis_client = await redis_manager.get_client()
            
            # 记录修复尝试
            await audit_logger.log_event(
                event_type=AuditEventType.DATA_REPAIR_ATTEMPTED,
                details={"key": key}
            )
            
            # 尝试从备份恢复
            backup_key = f"{self.backup_key_prefix}{key}"
            backup_json = await redis_client.get(backup_key)
            
            if not backup_json:
                await audit_logger.log_event(
                    event_type=AuditEventType.DATA_REPAIR_FAILED,
                    details={"key": key, "reason": "no_backup"}
                )
                return {
                    "key": key,
                    "status": "failed",
                    "error": "没有可用的备份数据"
                }
            
            try:
                backup_data = json.loads(backup_json)
                original_data = backup_data.get("data")
                backup_checksum = backup_data.get("checksum")
                backup_timestamp = backup_data.get("timestamp")
                
                # 验证备份数据的完整性
                if self._calculate_checksum(original_data) != backup_checksum:
                    await audit_logger.log_event(
                        event_type=AuditEventType.DATA_REPAIR_FAILED,
                        details={"key": key, "reason": "backup_corrupted"}
                    )
                    return {
                        "key": key,
                        "status": "failed",
                        "error": "备份数据也已损坏"
                    }
                
                # 恢复数据
                await redis_client.set(key, json.dumps(original_data, default=str))
                
                # 更新校验和
                checksum_key = f"{self.checksum_key_prefix}{key}"
                await redis_client.set(checksum_key, backup_checksum)
                
                # 记录修复成功
                await audit_logger.log_event(
                    event_type=AuditEventType.DATA_REPAIR_SUCCESS,
                    details={
                        "key": key,
                        "backup_timestamp": backup_timestamp
                    }
                )
                
                return {
                    "key": key,
                    "status": "success",
                    "restored_from": backup_timestamp,
                    "checksum": backup_checksum
                }
                
            except json.JSONDecodeError:
                await audit_logger.log_event(
                    event_type=AuditEventType.DATA_REPAIR_FAILED,
                    details={"key": key, "reason": "backup_parse_error"}
                )
                return {
                    "key": key,
                    "status": "failed",
                    "error": "备份数据解析失败"
                }
                
        except Exception as e:
            logger.error(f"Failed to repair data for {key}: {e}")
            await audit_logger.log_event(
                event_type=AuditEventType.DATA_REPAIR_FAILED,
                details={"key": key, "reason": str(e)}
            )
            return {
                "key": key,
                "status": "error",
                "error": str(e)
            }
    
    async def rollback_data(self, key: str) -> Dict[str, Any]:
        """
        回滚数据到备份版本
        
        Args:
            key: 数据键
            
        Returns:
            Dict: 回滚结果
        """
        try:
            # 记录回滚事件
            await audit_logger.log_event(
                event_type=AuditEventType.DATA_ROLLBACK,
                details={"key": key}
            )
            
            # 使用修复功能进行回滚
            return await self.repair_data(key)
            
        except Exception as e:
            logger.error(f"Failed to rollback data for {key}: {e}")
            return {
                "key": key,
                "status": "error",
                "error": str(e)
            }


# Global data integrity checker instance
data_integrity_checker = DataIntegrityChecker()


# Global audit logger instance
audit_logger = AuditLogger()


# Convenience functions
async def log_user_action(
    event_type: AuditEventType,
    user_id: str,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    success: bool = True
) -> bool:
    """记录用户操作"""
    return await audit_logger.log_event(event_type, user_id, details, ip_address, success)


async def log_security_event(
    event_type: AuditEventType,
    details: Dict[str, Any],
    ip_address: Optional[str] = None
) -> bool:
    """记录安全事件"""
    return await audit_logger.log_event(event_type, None, details, ip_address, False)


async def get_user_history(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """获取用户操作历史"""
    return await audit_logger.get_user_audit_log(user_id, limit=limit)


async def get_recent_security_events(hours: int = 24) -> List[Dict[str, Any]]:
    """获取最近的安全事件"""
    return await audit_logger.get_security_events(hours=hours)


# Data integrity convenience functions
async def store_data_safely(
    key: str,
    data: Dict[str, Any],
    ttl: Optional[int] = None
) -> bool:
    """安全存储数据（带校验和和备份）"""
    return await data_integrity_checker.store_with_checksum(key, data, ttl)


async def verify_data(key: str) -> Dict[str, Any]:
    """验证数据完整性"""
    return await data_integrity_checker.verify_data_integrity(key)


async def repair_corrupted_data(key: str) -> Dict[str, Any]:
    """修复损坏的数据"""
    return await data_integrity_checker.repair_data(key)


async def rollback_to_backup(key: str) -> Dict[str, Any]:
    """回滚数据到备份版本"""
    return await data_integrity_checker.rollback_data(key)
