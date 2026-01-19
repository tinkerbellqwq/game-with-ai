"""
Room model
房间数据模型
"""

from sqlalchemy import Column, String, Integer, DateTime, Enum, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from app.core.database import Base


class RoomStatus(PyEnum):
    """Room status enumeration"""
    WAITING = "waiting"
    STARTING = "starting"
    PLAYING = "playing"
    FINISHED = "finished"


class Room(Base):
    """Room model for game sessions"""
    
    __tablename__ = "rooms"
    
    id = Column(String(36), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    creator_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    
    # Room configuration
    max_players = Column(Integer, default=4, nullable=False)
    ai_count = Column(Integer, default=0, nullable=False)
    password = Column(String(50), nullable=True)  # 房间密码（可选）
    status = Column(Enum(RoomStatus), default=RoomStatus.WAITING, nullable=False)
    
    # Room settings stored as JSON
    settings = Column(JSON, nullable=True)
    
    # Current players (stored as JSON array of user IDs)
    current_players = Column(JSON, default=list, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    creator = relationship("User", foreign_keys=[creator_id])
    
    def __repr__(self):
        return f"<Room(id={self.id}, name={self.name}, status={self.status})>"
    
    @property
    def current_player_count(self) -> int:
        """Get current number of players"""
        return len(self.current_players) if self.current_players else 0
    
    @property
    def is_full(self) -> bool:
        """Check if room is at capacity"""
        return self.current_player_count >= self.max_players
    
    @property
    def can_start_game(self) -> bool:
        """Check if room has enough players to start"""
        total_players = self.current_player_count + self.ai_count
        return total_players >= 3 and self.status == RoomStatus.WAITING