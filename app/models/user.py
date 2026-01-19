"""
User model
用户数据模型
"""

from sqlalchemy import Column, String, Integer, DateTime, Boolean
from sqlalchemy.sql import func
from app.core.database import Base


class User(Base):
    """User model for authentication and game statistics"""
    
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    # Game statistics
    score = Column(Integer, default=0, nullable=False)
    games_played = Column(Integer, default=0, nullable=False)
    games_won = Column(Integer, default=0, nullable=False)

    # Advanced leaderboard statistics
    best_rank = Column(Integer, nullable=True)  # 历史最佳排名
    total_score_earned = Column(Integer, default=0, nullable=False)  # 累计获得积分
    consecutive_wins = Column(Integer, default=0, nullable=False)  # 当前连胜次数
    max_consecutive_wins = Column(Integer, default=0, nullable=False)  # 最大连胜记录
    last_game_at = Column(DateTime(timezone=True), nullable=True)  # 最后游戏时间

    # Account status
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage"""
        if self.games_played == 0:
            return 0.0
        return (self.games_won / self.games_played) * 100