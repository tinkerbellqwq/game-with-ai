"""
Room Pydantic schemas
房间数据验证和序列化模型
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class RoomStatus(str, Enum):
    """房间状态枚举"""
    WAITING = "waiting"
    STARTING = "starting"
    PLAYING = "playing"
    FINISHED = "finished"


class RoomSettings(BaseModel):
    """房间设置"""
    speech_time_limit: int = Field(default=60, ge=30, le=180, description="发言时间限制(秒)")
    voting_time_limit: int = Field(default=30, ge=15, le=60, description="投票时间限制(秒)")
    auto_start: bool = Field(default=False, description="人满自动开始")
    allow_spectators: bool = Field(default=True, description="允许观战")
    difficulty_level: int = Field(default=1, ge=1, le=5, description="词汇难度等级")
    category_filter: Optional[str] = Field(None, description="词汇类别过滤")


class RoomBase(BaseModel):
    """房间基础模型"""
    name: str = Field(..., min_length=1, max_length=100, description="房间名称")
    max_players: int = Field(default=4, ge=3, le=10, description="最大玩家数")
    ai_count: int = Field(default=0, ge=0, le=5, description="AI玩家数量")
    settings: Optional[RoomSettings] = Field(default_factory=RoomSettings, description="房间设置")
    
    @validator('max_players', 'ai_count')
    def validate_player_counts(cls, v, values):
        """验证玩家数量设置"""
        if 'max_players' in values and 'ai_count' in values:
            max_players = values.get('max_players', v if 'max_players' not in values else values['max_players'])
            ai_count = values.get('ai_count', v if 'ai_count' not in values else values['ai_count'])
            
            if ai_count > max_players:
                raise ValueError('AI玩家数量不能超过最大玩家数')
            
            total_min_players = 3
            if max_players < total_min_players:
                raise ValueError(f'房间至少需要{total_min_players}个玩家')
        
        return v


class RoomCreate(RoomBase):
    """创建房间请求模型"""
    password: Optional[str] = Field(None, max_length=50, description="房间密码(可选)")
    ai_template_ids: Optional[List[str]] = Field(default=None, description="指定的AI模板ID列表")


class RoomUpdate(BaseModel):
    """更新房间请求模型"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    max_players: Optional[int] = Field(None, ge=3, le=10)
    ai_count: Optional[int] = Field(None, ge=0, le=5)
    settings: Optional[RoomSettings] = None


class PlayerInfo(BaseModel):
    """玩家信息"""
    id: str
    username: str
    is_ai: bool = False
    is_ready: bool = False
    is_creator: bool = False


class RoomResponse(BaseModel):
    """房间响应模型"""
    id: str
    name: str
    creator_id: str
    creator_name: str = ""
    max_players: int
    current_players: int = 0  # 当前玩家数量
    ai_count: int = 0
    has_password: bool = False  # 是否有密码保护
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoomDetailResponse(RoomResponse):
    """房间详细信息响应"""
    players: List[PlayerInfo] = Field(default_factory=list, description="玩家详细信息")


class RoomListResponse(BaseModel):
    """房间列表响应"""
    rooms: List[RoomResponse]
    total: int
    page: int
    page_size: int
    total_pages: int = 1
    has_next: bool


class RoomJoinRequest(BaseModel):
    """加入房间请求"""
    password: Optional[str] = Field(None, description="房间密码(如果需要)")


class RoomJoinResponse(BaseModel):
    """加入房间响应"""
    success: bool
    message: str
    room: Optional[RoomResponse] = None


class RoomFilters(BaseModel):
    """房间过滤条件"""
    status: Optional[RoomStatus] = None
    has_slots: Optional[bool] = None  # 是否有空位
    min_players: Optional[int] = Field(None, ge=1, le=10)
    max_players: Optional[int] = Field(None, ge=1, le=10)
    search: Optional[str] = Field(None, max_length=100, description="搜索关键词")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


class RoomAction(BaseModel):
    """房间操作请求"""
    action: str = Field(..., description="操作类型: start_game, kick_player, transfer_owner")
    target_user_id: Optional[str] = Field(None, description="目标用户ID(踢人或转移房主时使用)")
    
    @validator('action')
    def validate_action(cls, v):
        allowed_actions = ['start_game', 'kick_player', 'transfer_owner', 'ready', 'unready']
        if v not in allowed_actions:
            raise ValueError(f'无效的操作类型，允许的操作: {", ".join(allowed_actions)}')
        return v