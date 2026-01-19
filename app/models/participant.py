"""
Participant model
游戏参与者模型 - 统一管理真人玩家和AI玩家的游戏参与记录
"""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.schemas.game import PlayerRole


class Participant(Base):
    """
    游戏参与者表
    统一存储真人玩家和AI玩家的游戏参与记录
    解决 speeches/votes 表的外键约束问题
    """

    __tablename__ = "participants"

    id = Column(String(36), primary_key=True, index=True)
    game_id = Column(String(36), ForeignKey("games.id"), nullable=False, index=True)

    # 玩家信息
    player_id = Column(String(36), nullable=False, index=True)  # 真人用户ID或AI玩家ID
    username = Column(String(50), nullable=False)
    is_ai = Column(Boolean, default=False, nullable=False)

    # 游戏角色
    role = Column(Enum(PlayerRole, values_callable=lambda obj: [e.value for e in obj]),
                  nullable=False)
    word = Column(String(100), nullable=False)  # 分配的词汇

    # 游戏状态
    is_alive = Column(Boolean, default=True, nullable=False)
    is_ready = Column(Boolean, default=True, nullable=False)

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    game = relationship("Game", foreign_keys=[game_id])

    def __repr__(self):
        return f"<Participant(id={self.id}, game_id={self.game_id}, username={self.username}, is_ai={self.is_ai})>"
