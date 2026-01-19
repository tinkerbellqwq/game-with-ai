"""
AI Player model and configuration
AI玩家模型和配置
"""

from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from enum import Enum
from typing import Dict, Any, Optional
import json
import uuid

from app.core.database import Base


class AIDifficulty(str, Enum):
    """AI difficulty levels"""
    BEGINNER = "beginner"
    NORMAL = "normal"
    EXPERT = "expert"


class AIPersonality(str, Enum):
    """AI personality types"""
    CAUTIOUS = "cautious"
    AGGRESSIVE = "aggressive"
    NORMAL = "normal"
    RANDOM = "random"


class AIPlayer(Base):
    """
    AI Player model for managing AI opponents
    验证需求: 需求 4.1
    """

    __tablename__ = "ai_players"

    id = Column(String(36), primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    difficulty = Column(SQLEnum(AIDifficulty), default=AIDifficulty.NORMAL, nullable=False)
    personality = Column(SQLEnum(AIPersonality), default=AIPersonality.NORMAL, nullable=False)

    # LLM API configuration - 每个 AI 可以有独立的 API 配置
    api_base_url = Column(String(500), nullable=True)  # API 基础 URL
    api_key = Column(String(500), nullable=True)       # API 密钥
    model_name = Column(String(100), nullable=True)    # 使用的 LLM 模型名称

    # AI configuration
    config = Column(Text, nullable=True)  # JSON configuration

    # Statistics
    games_played = Column(Integer, default=0, nullable=False)
    games_won = Column(Integer, default=0, nullable=False)
    total_speeches = Column(Integer, default=0, nullable=False)
    total_votes = Column(Integer, default=0, nullable=False)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<AIPlayer(id={self.id}, name={self.name}, difficulty={self.difficulty})>"
    
    @property
    def win_rate(self) -> float:
        """Calculate AI win rate percentage"""
        if self.games_played == 0:
            return 0.0
        return (self.games_won / self.games_played) * 100
    
    @property
    def config_dict(self) -> Dict[str, Any]:
        """Get configuration as dictionary"""
        if self.config:
            try:
                return json.loads(self.config)
            except json.JSONDecodeError:
                return {}
        return {}
    
    @config_dict.setter
    def config_dict(self, value: Dict[str, Any]) -> None:
        """Set configuration from dictionary"""
        self.config = json.dumps(value) if value else None
    
    def get_strategy_config(self) -> Dict[str, Any]:
        """Get strategy configuration based on difficulty and personality"""
        base_config = {
            "speech_length_range": (15, 30),
            "response_time_range": (2, 8),
            "voting_confidence": 0.7,
            "bluff_probability": 0.3,
            "analysis_depth": 2
        }
        
        # Adjust based on difficulty
        if self.difficulty == AIDifficulty.BEGINNER:
            base_config.update({
                "voting_confidence": 0.5,
                "bluff_probability": 0.1,
                "analysis_depth": 1,
                "speech_length_range": (10, 20)
            })
        elif self.difficulty == AIDifficulty.EXPERT:
            base_config.update({
                "voting_confidence": 0.9,
                "bluff_probability": 0.5,
                "analysis_depth": 3,
                "speech_length_range": (20, 35)
            })
        
        # Adjust based on personality
        if self.personality == AIPersonality.CAUTIOUS:
            base_config.update({
                "bluff_probability": base_config["bluff_probability"] * 0.5,
                "voting_confidence": base_config["voting_confidence"] * 0.8,
                "response_time_range": (3, 10)
            })
        elif self.personality == AIPersonality.AGGRESSIVE:
            base_config.update({
                "bluff_probability": base_config["bluff_probability"] * 1.5,
                "voting_confidence": base_config["voting_confidence"] * 1.2,
                "response_time_range": (1, 5)
            })
        
        # Merge with custom config
        custom_config = self.config_dict
        base_config.update(custom_config)
        
        return base_config


class AIPlayerConfig:
    """AI Player configuration templates"""
    
    @staticmethod
    def get_default_names() -> Dict[AIDifficulty, list]:
        """Get default AI player names by difficulty"""
        return {
            AIDifficulty.BEGINNER: [
                "小白", "新手", "学徒", "初心者", "菜鸟"
            ],
            AIDifficulty.NORMAL: [
                "智者", "分析师", "推理家", "观察者", "思考者"
            ],
            AIDifficulty.EXPERT: [
                "大师", "专家", "高手", "智囊", "策略家"
            ]
        }
    
    @staticmethod
    def get_personality_traits() -> Dict[AIPersonality, Dict[str, Any]]:
        """Get personality trait configurations"""
        return {
            AIPersonality.CAUTIOUS: {
                "description": "谨慎小心，发言保守",
                "speech_style": "conservative",
                "risk_tolerance": 0.3,
                "cooperation_tendency": 0.8
            },
            AIPersonality.AGGRESSIVE: {
                "description": "积极主动，发言大胆",
                "speech_style": "bold",
                "risk_tolerance": 0.8,
                "cooperation_tendency": 0.4
            },
            AIPersonality.NORMAL: {
                "description": "正常发挥，平衡策略",
                "speech_style": "balanced",
                "risk_tolerance": 0.5,
                "cooperation_tendency": 0.6
            },
            AIPersonality.RANDOM: {
                "description": "随机行为，不可预测",
                "speech_style": "unpredictable",
                "risk_tolerance": 0.6,
                "cooperation_tendency": 0.5
            }
        }
    
    @staticmethod
    def create_default_config(
        difficulty: AIDifficulty, 
        personality: AIPersonality
    ) -> Dict[str, Any]:
        """Create default configuration for AI player"""
        base_config = {
            "version": "1.0",
            "created_at": func.now().isoformat() if hasattr(func.now(), 'isoformat') else None,
            "difficulty_settings": {},
            "personality_settings": {},
            "custom_prompts": {},
            "behavior_modifiers": {}
        }
        
        # Add difficulty-specific settings
        if difficulty == AIDifficulty.BEGINNER:
            base_config["difficulty_settings"] = {
                "mistake_probability": 0.2,
                "learning_rate": 0.1,
                "complexity_limit": 2
            }
        elif difficulty == AIDifficulty.EXPERT:
            base_config["difficulty_settings"] = {
                "mistake_probability": 0.05,
                "learning_rate": 0.3,
                "complexity_limit": 5
            }
        else:  # NORMAL
            base_config["difficulty_settings"] = {
                "mistake_probability": 0.1,
                "learning_rate": 0.2,
                "complexity_limit": 3
            }
        
        # Add personality-specific settings
        personality_traits = AIPlayerConfig.get_personality_traits()
        if personality in personality_traits:
            base_config["personality_settings"] = personality_traits[personality]
        
        return base_config