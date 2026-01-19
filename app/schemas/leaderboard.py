"""
Leaderboard Pydantic schemas
排行榜数据验证和序列化模型
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class LeaderboardEntry(BaseModel):
    """Single leaderboard entry"""
    rank: int = Field(..., description="排名")
    user_id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    score: int = Field(..., description="积分")
    games_played: int = Field(..., description="游戏总数")
    games_won: int = Field(..., description="获胜次数")
    win_rate: float = Field(..., description="胜率")
    last_game_at: Optional[datetime] = Field(None, description="最后游戏时间")
    is_ai: bool = Field(default=False, description="是否是AI玩家")

    class Config:
        from_attributes = True


class LeaderboardResponse(BaseModel):
    """Leaderboard response with pagination"""
    entries: List[LeaderboardEntry] = Field(..., description="排行榜条目")
    total_count: int = Field(..., description="总用户数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    total_pages: int = Field(..., description="总页数")
    has_next: bool = Field(..., description="是否有下一页")
    has_prev: bool = Field(..., description="是否有上一页")


class UserRankInfo(BaseModel):
    """User's ranking information"""
    user_id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    current_rank: int = Field(..., description="当前排名")
    score: int = Field(..., description="当前积分")
    games_played: int = Field(..., description="游戏总数")
    games_won: int = Field(..., description="获胜次数")
    win_rate: float = Field(..., description="胜率")
    rank_change: Optional[int] = Field(None, description="排名变化")
    
    class Config:
        from_attributes = True


class PersonalStats(BaseModel):
    """Personal detailed statistics"""
    user_id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    current_rank: int = Field(..., description="当前排名")
    score: int = Field(..., description="当前积分")
    games_played: int = Field(..., description="游戏总数")
    games_won: int = Field(..., description="获胜次数")
    games_lost: int = Field(..., description="失败次数")
    win_rate: float = Field(..., description="胜率")
    best_rank: Optional[int] = Field(None, description="历史最佳排名")
    total_score_earned: int = Field(default=0, description="累计获得积分")
    average_score_per_game: float = Field(default=0.0, description="平均每局积分")
    consecutive_wins: int = Field(default=0, description="连胜次数")
    max_consecutive_wins: int = Field(default=0, description="最大连胜记录")
    created_at: datetime = Field(..., description="注册时间")
    last_game_at: Optional[datetime] = Field(None, description="最后游戏时间")
    
    class Config:
        from_attributes = True


class LeaderboardQuery(BaseModel):
    """Leaderboard query parameters"""
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页大小")
    sort_by: str = Field(default="score", description="排序字段")
    order: str = Field(default="desc", description="排序方向")
    
    class Config:
        schema_extra = {
            "example": {
                "page": 1,
                "page_size": 20,
                "sort_by": "score",
                "order": "desc"
            }
        }