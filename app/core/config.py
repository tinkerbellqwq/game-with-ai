"""
Application configuration settings
应用配置设置 - 针对2C2G环境优化
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings optimized for 2C2G server environment"""
    
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # Server configuration - optimized for 2C2G
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1  # Single worker for 2C2G memory constraints
    
    # Database configuration - MySQL optimized for 2C2G
    DATABASE_URL: str = "mysql+pymysql://root:password@localhost:3306/undercover_game"
    DB_POOL_SIZE: int = 5  # Reduced pool size for memory efficiency
    DB_MAX_OVERFLOW: int = 3  # Reduced overflow for 2C2G
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800  # Recycle connections every 30 minutes
    DB_POOL_PRE_PING: bool = True  # Validate connections before use
    
    # Redis configuration - optimized for 2C2G
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 5  # Limited connections for memory efficiency
    REDIS_SOCKET_TIMEOUT: int = 5
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5
    REDIS_MAX_MEMORY: str = "256mb"  # Redis memory limit for 2C2G
    
    # JWT configuration
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # OpenAI 默认配置（用于新建 AI 玩家的初始值）
    # 注意：每个 AI 玩家可以有独立的 API 配置，以下仅为创建新 AI 时的默认值
    OPENAI_BASE_URL: Optional[str] = None  # 可选，用于第三方兼容 API
    OPENAI_API_KEY: Optional[str] = None   # API 密钥（创建 AI 时复制到 AI 玩家）
    OPENAI_MODEL: str = "gpt-3.5-turbo"    # 默认模型
    OPENAI_MAX_TOKENS: int = 150           # 生成参数：最大 token 数
    OPENAI_TEMPERATURE: float = 0.7        # 生成参数：温度
    OPENAI_DAILY_REQUEST_LIMIT: int = 1000 # 每日请求限制
    OPENAI_TIMEOUT: int = 30               # 请求超时（秒）

    # 可用的 AI 模型列表（用逗号分隔）
    AI_AVAILABLE_MODELS: str = "deepseek-v3.2-chat,gemini-3-flash-preview,glm-4.7,grok-4.1,minimaxai/minimax-m2.1,moonshotai/kimi-k2-instruct,qwen3-235b-a22b-thinking-2507"

    @property
    def ai_models_list(self) -> list:
        """获取可用 AI 模型列表"""
        if self.AI_AVAILABLE_MODELS:
            return [m.strip() for m in self.AI_AVAILABLE_MODELS.split(",") if m.strip()]
        return [self.OPENAI_MODEL]
    
    # WebSocket configuration - optimized for 2C2G
    MAX_WEBSOCKET_CONNECTIONS: int = 50  # Limited for 2C2G environment
    WEBSOCKET_PING_INTERVAL: int = 30  # Increased interval to reduce overhead
    WEBSOCKET_PING_TIMEOUT: int = 10
    WEBSOCKET_MESSAGE_QUEUE_SIZE: int = 100  # Limit message queue size
    
    # Game configuration - optimized for 2C2G
    MAX_ROOMS: int = 10  # Limited concurrent rooms for 2C2G
    MAX_PLAYERS_PER_ROOM: int = 8
    ROOM_IDLE_TIMEOUT: int = 1800  # 30 minutes
    GAME_SPEECH_TIME_LIMIT: int = 60  # 60 seconds per speech
    MAX_CONCURRENT_GAMES: int = 5  # Limit concurrent games
    GAME_STATE_CACHE_TTL: int = 3600  # 1 hour cache TTL
    
    # Resource limits for 2C2G environment
    MAX_MEMORY_MB: int = 1500  # Reserve 500MB for system
    MAX_CPU_PERCENT: int = 80
    CLEANUP_INTERVAL: int = 300  # 5 minutes
    GC_THRESHOLD: int = 1200  # Trigger GC when memory exceeds 1200MB
    
    # Rate limiting - optimized for 2C2G
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60  # per minute
    RATE_LIMIT_BURST: int = 20  # Allow burst of 20 requests
    
    # Caching configuration
    CACHE_DEFAULT_TTL: int = 300  # 5 minutes default cache TTL
    LEADERBOARD_CACHE_TTL: int = 60  # 1 minute for leaderboard
    USER_STATS_CACHE_TTL: int = 300  # 5 minutes for user stats
    
    # Background task configuration
    BACKGROUND_TASK_INTERVAL: int = 60  # 1 minute
    ROOM_CLEANUP_INTERVAL: int = 300  # 5 minutes
    SESSION_CLEANUP_INTERVAL: int = 600  # 10 minutes
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_MAX_SIZE: int = 10485760  # 10MB max log file size
    LOG_BACKUP_COUNT: int = 3  # Keep 3 backup log files
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()