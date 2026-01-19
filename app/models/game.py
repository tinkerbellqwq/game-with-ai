"""
Game model
游戏数据模型
"""

from sqlalchemy import Column, String, Integer, DateTime, Enum, JSON, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from app.core.database import Base

# 导入统一的enum定义
from app.schemas.game import GamePhase, PlayerRole


class Game(Base):
    """Game model for storing game sessions"""
    
    __tablename__ = "games"
    
    id = Column(String(36), primary_key=True, index=True)
    room_id = Column(String(36), ForeignKey("rooms.id"), nullable=False)
    word_pair_id = Column(String(36), ForeignKey("word_pairs.id"), nullable=False)
    
    # Game state
    current_phase = Column(Enum(GamePhase, values_callable=lambda obj: [e.value for e in obj]), 
                          default=GamePhase.PREPARING, nullable=False)
    current_speaker = Column(String(36), nullable=True)
    round_number = Column(Integer, default=1, nullable=False)
    
    # Players and roles (stored as JSON)
    players = Column(JSON, nullable=False)  # List of player objects with roles
    eliminated_players = Column(JSON, default=list, nullable=False)
    
    # Game results
    winner_role = Column(Enum(PlayerRole, values_callable=lambda obj: [e.value for e in obj]), 
                        nullable=True)
    winner_players = Column(JSON, nullable=True)
    
    # Timestamps
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    room = relationship("Room", foreign_keys=[room_id])
    word_pair = relationship("WordPair", foreign_keys=[word_pair_id])
    
    def __repr__(self):
        return f"<Game(id={self.id}, room_id={self.room_id}, phase={self.current_phase})>"


class Speech(Base):
    """Speech model for storing player speeches"""

    __tablename__ = "speeches"

    id = Column(String(36), primary_key=True, index=True)
    game_id = Column(String(36), ForeignKey("games.id"), nullable=False)
    # 改为指向 participants 表，支持真人和AI玩家
    participant_id = Column(String(36), ForeignKey("participants.id"), nullable=False)

    # Speech content
    content = Column(Text, nullable=False)
    round_number = Column(Integer, nullable=False)
    speech_order = Column(Integer, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    game = relationship("Game", foreign_keys=[game_id])
    participant = relationship("Participant", foreign_keys=[participant_id])

    def __repr__(self):
        return f"<Speech(id={self.id}, participant_id={self.participant_id}, round={self.round_number})>"


class Vote(Base):
    """Vote model for storing player votes"""

    __tablename__ = "votes"

    id = Column(String(36), primary_key=True, index=True)
    game_id = Column(String(36), ForeignKey("games.id"), nullable=False)
    # 改为指向 participants 表，支持真人和AI玩家
    voter_id = Column(String(36), ForeignKey("participants.id"), nullable=False)
    target_id = Column(String(36), ForeignKey("participants.id"), nullable=False)

    round_number = Column(Integer, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    game = relationship("Game", foreign_keys=[game_id])
    voter = relationship("Participant", foreign_keys=[voter_id])
    target = relationship("Participant", foreign_keys=[target_id])

    def __repr__(self):
        return f"<Vote(id={self.id}, voter_id={self.voter_id}, target_id={self.target_id})>"