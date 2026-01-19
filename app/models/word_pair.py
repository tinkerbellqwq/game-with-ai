"""
Word pair model
词汇对数据模型
"""

from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class WordPair(Base):
    """Word pair model for game words"""
    
    __tablename__ = "word_pairs"
    
    id = Column(String(36), primary_key=True, index=True)
    civilian_word = Column(String(50), nullable=False)  # 平民词汇
    undercover_word = Column(String(50), nullable=False)  # 卧底词汇
    category = Column(String(50), nullable=False)
    difficulty = Column(Integer, default=1, nullable=False)  # 1-5 difficulty level
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<WordPair(id={self.id}, category={self.category}, difficulty={self.difficulty})>"
    
    def get_word_for_role(self, role: str) -> str:
        """Get appropriate word for player role"""
        if role == "undercover":
            return self.undercover_word
        return self.civilian_word