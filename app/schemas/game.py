"""
Game Pydantic schemas
游戏数据验证和序列化模型
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum


class GamePhase(str, Enum):
    """游戏阶段枚举"""
    PREPARING = "preparing"
    SPEAKING = "speaking"
    VOTING = "voting"
    RESULT = "result"
    FINISHED = "finished"


class PlayerRole(str, Enum):
    """玩家角色枚举"""
    CIVILIAN = "civilian"
    UNDERCOVER = "undercover"


class GamePlayer(BaseModel):
    """游戏中的玩家信息"""
    id: str
    username: str
    role: PlayerRole
    word: str
    is_ai: bool = False
    is_alive: bool = True
    is_ready: bool = False


class SpeechCreate(BaseModel):
    """发言创建请求"""
    content: str = Field(..., min_length=1, max_length=500, description="发言内容")
    
    @validator('content')
    def validate_content(cls, v):
        """验证发言内容"""
        # 移除首尾空白字符
        v = v.strip()
        if not v:
            raise ValueError('发言内容不能为空')
        
        # 检查是否包含敏感词汇（简单示例）
        forbidden_words = ['卧底', '平民', '词汇']  # 实际应用中应该更完善
        for word in forbidden_words:
            if word in v:
                raise ValueError(f'发言不能直接提及"{word}"')
        
        return v


class SpeechResponse(BaseModel):
    """发言响应"""
    id: str
    game_id: str
    player_id: str
    player_username: str
    content: str
    round_number: int
    speech_order: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class VoteCreate(BaseModel):
    """投票创建请求"""
    target_id: str = Field(..., description="投票目标玩家ID")


class VoteResponse(BaseModel):
    """投票响应"""
    id: str
    game_id: str
    voter_id: str
    voter_username: str
    target_id: str
    target_username: str
    round_number: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class VoteResult(BaseModel):
    """投票结果"""
    target_id: str
    target_username: str
    vote_count: int
    is_eliminated: bool
    revealed_role: Optional[PlayerRole] = None


class GameState(BaseModel):
    """游戏状态"""
    id: str
    room_id: str
    word_pair_id: str
    current_phase: GamePhase
    current_speaker: Optional[str] = None
    current_speaker_username: Optional[str] = None
    current_voter: Optional[str] = None  # 当前投票者
    current_voter_username: Optional[str] = None  # 当前投票者用户名
    round_number: int
    players: List[GamePlayer]
    eliminated_players: List[str] = Field(default_factory=list)
    winner_role: Optional[PlayerRole] = None
    winner_players: Optional[List[str]] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    
    # 计算属性
    @property
    def alive_players(self) -> List[GamePlayer]:
        """存活玩家列表"""
        return [p for p in self.players if p.is_alive]
    
    @property
    def civilian_count(self) -> int:
        """存活平民数量"""
        return len([p for p in self.alive_players if p.role == PlayerRole.CIVILIAN])
    
    @property
    def undercover_count(self) -> int:
        """存活卧底数量"""
        return len([p for p in self.alive_players if p.role == PlayerRole.UNDERCOVER])
    
    @property
    def is_game_over(self) -> bool:
        """游戏是否结束"""
        return self.undercover_count == 0 or self.undercover_count >= self.civilian_count
    
    class Config:
        from_attributes = True


class GameCreate(BaseModel):
    """创建游戏请求"""
    room_id: str
    word_pair_id: Optional[str] = None  # 如果不指定，系统随机选择
    difficulty: Optional[int] = Field(None, ge=1, le=5, description="词汇难度")
    category: Optional[str] = Field(None, description="词汇类别")


class GameAction(BaseModel):
    """游戏操作请求"""
    action: str = Field(..., description="操作类型")
    data: Optional[Dict[str, Any]] = Field(None, description="操作数据")
    
    @validator('action')
    def validate_action(cls, v):
        allowed_actions = [
            'ready', 'unready', 'speak', 'vote', 
            'skip_speech', 'request_hint', 'surrender'
        ]
        if v not in allowed_actions:
            raise ValueError(f'无效的操作类型，允许的操作: {", ".join(allowed_actions)}')
        return v


class GameResponse(BaseModel):
    """游戏响应"""
    game: GameState
    current_user_role: Optional[PlayerRole] = None
    current_user_word: Optional[str] = None
    can_speak: bool = False
    can_vote: bool = False
    time_remaining: Optional[int] = None  # 剩余时间(秒)


class GameHistory(BaseModel):
    """游戏历史记录"""
    id: str
    room_name: str
    players: List[str]  # 玩家用户名列表
    winner_role: Optional[PlayerRole]
    user_role: PlayerRole
    user_won: bool
    score_change: int
    started_at: datetime
    finished_at: Optional[datetime]
    duration_minutes: Optional[int]
    
    class Config:
        from_attributes = True


class GameStats(BaseModel):
    """游戏统计"""
    total_games: int
    games_won: int
    games_lost: int
    win_rate: float
    civilian_games: int
    civilian_wins: int
    undercover_games: int
    undercover_wins: int
    average_score_change: float
    best_performance: Optional[GameHistory] = None


class RoundSummary(BaseModel):
    """轮次总结"""
    round_number: int
    speeches: List[SpeechResponse]
    votes: List[VoteResponse]
    vote_result: Optional[VoteResult]
    eliminated_player: Optional[Dict[str, Any]]


class GameSummary(BaseModel):
    """游戏总结"""
    game_id: str
    room_name: str
    word_pair: Dict[str, str]  # {"civilian": "苹果", "undercover": "梨"}
    players: List[Dict[str, Any]]  # 玩家信息和角色
    rounds: List[RoundSummary]
    winner_role: PlayerRole
    winner_players: List[str]
    duration_minutes: int
    mvp_player: Optional[str] = None  # 最佳表现玩家