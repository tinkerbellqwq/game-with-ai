"""
Background tasks service
后台任务服务
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.core.database import db_manager
from app.services.room import RoomService

logger = logging.getLogger(__name__)


class BackgroundTaskService:
    """后台任务服务类"""
    
    def __init__(self):
        self.is_running = False
        self.cleanup_task: Optional[asyncio.Task] = None
        self.websocket_cleanup_task: Optional[asyncio.Task] = None
    
    async def start_room_cleanup_task(self, interval_minutes: int = 10, max_idle_minutes: int = 30):
        """
        启动房间清理任务
        验证需求: 需求 2.5 - 当房间空闲超过设定时间时，系统应自动解散房间
        """
        if self.is_running:
            logger.warning("房间清理任务已在运行")
            return
        
        self.is_running = True
        self.cleanup_task = asyncio.create_task(
            self._room_cleanup_loop(interval_minutes, max_idle_minutes)
        )
        logger.info(f"房间清理任务已启动，检查间隔: {interval_minutes}分钟，空闲超时: {max_idle_minutes}分钟")
    
    async def start_websocket_cleanup_task(self, interval_minutes: int = 5):
        """
        启动WebSocket连接清理任务
        验证需求: 需求 7.5 - 当连接中断时，系统应尝试重连并同步消息历史
        """
        if self.websocket_cleanup_task and not self.websocket_cleanup_task.done():
            logger.warning("WebSocket清理任务已在运行")
            return
        
        self.websocket_cleanup_task = asyncio.create_task(
            self._websocket_cleanup_loop(interval_minutes)
        )
        logger.info(f"WebSocket清理任务已启动，检查间隔: {interval_minutes}分钟")
    
    async def stop_room_cleanup_task(self):
        """停止房间清理任务"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("房间清理任务已停止")
    
    async def stop_websocket_cleanup_task(self):
        """停止WebSocket清理任务"""
        if self.websocket_cleanup_task:
            self.websocket_cleanup_task.cancel()
            try:
                await self.websocket_cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("WebSocket清理任务已停止")
    
    async def _room_cleanup_loop(self, interval_minutes: int, max_idle_minutes: int):
        """房间清理循环任务"""
        while self.is_running:
            try:
                # 使用 db_manager 获取数据库会话
                if not db_manager.session_factory:
                    await db_manager.initialize()

                session = db_manager.session_factory()
                try:
                    room_service = RoomService(session)

                    # 执行清理
                    cleaned_count = await room_service.cleanup_empty_rooms(max_idle_minutes)

                    if cleaned_count > 0:
                        logger.info(f"清理了 {cleaned_count} 个空闲房间")
                finally:
                    await session.close()

            except Exception as e:
                logger.error(f"房间清理任务执行失败: {str(e)}")

            # 等待下次执行
            await asyncio.sleep(interval_minutes * 60)
    
    async def _websocket_cleanup_loop(self, interval_minutes: int):
        """WebSocket连接清理循环任务"""
        while True:
            try:
                # 导入连接管理器（避免循环导入）
                from app.websocket.connection_manager import connection_manager
                
                # 执行清理
                cleaned_count = await connection_manager.cleanup_inactive_connections()
                
                if cleaned_count > 0:
                    logger.info(f"清理了 {cleaned_count} 个不活跃的WebSocket连接")
                
            except Exception as e:
                logger.error(f"WebSocket清理任务执行失败: {str(e)}")
            
            # 等待下次执行
            await asyncio.sleep(interval_minutes * 60)
    
    async def cleanup_rooms_once(self, max_idle_minutes: int = 30) -> int:
        """执行一次房间清理"""
        try:
            if not db_manager.session_factory:
                await db_manager.initialize()

            session = db_manager.session_factory()
            try:
                room_service = RoomService(session)
                cleaned_count = await room_service.cleanup_empty_rooms(max_idle_minutes)
                logger.info(f"手动清理了 {cleaned_count} 个空闲房间")
                return cleaned_count
            finally:
                await session.close()

        except Exception as e:
            logger.error(f"手动房间清理失败: {str(e)}")
            raise
    
    async def cleanup_websockets_once(self) -> int:
        """执行一次WebSocket连接清理"""
        try:
            from app.websocket.connection_manager import connection_manager
            
            cleaned_count = await connection_manager.cleanup_inactive_connections()
            logger.info(f"手动清理了 {cleaned_count} 个不活跃的WebSocket连接")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"手动WebSocket清理失败: {str(e)}")
            raise


# 全局后台任务服务实例
background_service = BackgroundTaskService()


async def start_background_tasks():
    """启动所有后台任务"""
    await background_service.start_room_cleanup_task()
    await background_service.start_websocket_cleanup_task()


async def stop_background_tasks():
    """停止所有后台任务"""
    await background_service.stop_room_cleanup_task()
    await background_service.stop_websocket_cleanup_task()


def get_background_service() -> BackgroundTaskService:
    """获取后台任务服务实例"""
    return background_service