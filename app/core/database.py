"""
Database configuration and connection management
数据库配置和连接管理 - MySQL优化配置，增强稳定性和重连机制
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import DisconnectionError, OperationalError
from sqlalchemy import event, text
from app.core.config import settings
import logging
import asyncio
import time
from typing import Optional
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all database models"""
    pass


class DatabaseManager:
    """Enhanced database manager with connection recovery and transaction management"""
    
    def __init__(self):
        self.engine: Optional[create_async_engine] = None
        self.session_factory: Optional[async_sessionmaker] = None
        self._connection_retries = 0
        self._max_retries = 3
        self._retry_delay = 1.0
        self._health_check_interval = 30
        self._last_health_check = 0
    
    async def initialize(self):
        """Initialize database engine with enhanced connection management"""
        try:
            # Create async engine with optimized settings for 2C2G
            self.engine = create_async_engine(
                settings.DATABASE_URL.replace("mysql+pymysql", "mysql+aiomysql"),
                poolclass=QueuePool,
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_MAX_OVERFLOW,
                pool_timeout=settings.DB_POOL_TIMEOUT,
                pool_recycle=settings.DB_POOL_RECYCLE,
                pool_pre_ping=True,  # Validate connections before use
                echo=settings.DEBUG,
                # Enhanced MySQL connection settings for stability
                connect_args={
                    "charset": "utf8mb4",
                    "autocommit": False,
                    "connect_timeout": 10,
                },
                # Connection pool events for monitoring
                pool_reset_on_return='commit',
            )
            
            # Create async session factory
            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=True,
                autocommit=False
            )
            
            # Test initial connection
            await self._test_connection()
            logger.info("Database manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database manager: {e}")
            raise
    
    async def _test_connection(self) -> bool:
        """Test database connection health"""
        try:
            if not self.engine:
                return False
                
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            
            self._connection_retries = 0
            self._last_health_check = time.time()
            return True
            
        except (DisconnectionError, OperationalError) as e:
            logger.warning(f"Database connection test failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during connection test: {e}")
            return False
    
    async def _reconnect(self) -> bool:
        """Attempt to reconnect to database with exponential backoff"""
        if self._connection_retries >= self._max_retries:
            logger.error("Maximum database reconnection attempts exceeded")
            return False
        
        self._connection_retries += 1
        delay = self._retry_delay * (2 ** (self._connection_retries - 1))
        
        logger.info(f"Attempting database reconnection {self._connection_retries}/{self._max_retries} after {delay}s")
        await asyncio.sleep(delay)
        
        try:
            # Dispose old engine and create new one
            if self.engine:
                await self.engine.dispose()
            
            await self.initialize()
            return True
            
        except Exception as e:
            logger.error(f"Database reconnection attempt {self._connection_retries} failed: {e}")
            return False
    
    async def health_check(self) -> bool:
        """Perform periodic health check"""
        current_time = time.time()
        if current_time - self._last_health_check < self._health_check_interval:
            return True
        
        if await self._test_connection():
            return True
        
        # Attempt reconnection if health check fails
        return await self._reconnect()
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session with automatic retry and transaction management"""
        if not self.session_factory:
            raise RuntimeError("Database manager not initialized")
        
        # Perform health check
        if not await self.health_check():
            raise RuntimeError("Database connection unavailable")
        
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except (DisconnectionError, OperationalError) as e:
            logger.warning(f"Database connection error during session: {e}")
            await session.rollback()
            
            # Attempt reconnection and retry once
            if await self._reconnect():
                session = self.session_factory()
                try:
                    yield session
                    await session.commit()
                except Exception as retry_e:
                    await session.rollback()
                    logger.error(f"Database operation failed after reconnection: {retry_e}")
                    raise
                finally:
                    await session.close()
            else:
                raise RuntimeError("Database connection could not be restored")
        except Exception as e:
            await session.rollback()
            logger.error(f"Database transaction error: {e}")
            raise
        finally:
            await session.close()
    
    async def execute_with_retry(self, operation, *args, **kwargs):
        """Execute database operation with automatic retry on connection failure"""
        max_attempts = 2
        
        for attempt in range(max_attempts):
            try:
                async with self.get_session() as session:
                    return await operation(session, *args, **kwargs)
            except (DisconnectionError, OperationalError) as e:
                if attempt == max_attempts - 1:
                    logger.error(f"Database operation failed after {max_attempts} attempts: {e}")
                    raise
                logger.warning(f"Database operation attempt {attempt + 1} failed, retrying: {e}")
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Database operation failed with non-connection error: {e}")
                raise
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")


# Global database manager instance
db_manager = DatabaseManager()

# Legacy compatibility - will be deprecated
engine = None
AsyncSessionLocal = None

async def init_db():
    """Initialize database connection and create tables if needed"""
    try:
        await db_manager.initialize()
        
        async with db_manager.get_session() as session:
            # Import all models to ensure they are registered
            from app.models import user, room, game, word_pair  # noqa
            
            # Create all tables
            async with db_manager.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


async def get_db() -> AsyncSession:
    """Dependency to get database session with enhanced error handling"""
    # For backward compatibility with existing code and tests
    if not db_manager.session_factory:
        await db_manager.initialize()
    
    session = db_manager.session_factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def close_db():
    """Close database connections"""
    await db_manager.close()


# Transaction management utilities
@asynccontextmanager
async def transaction():
    """Context manager for explicit transaction management"""
    async with db_manager.get_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def execute_with_retry(operation, *args, **kwargs):
    """Execute database operation with automatic retry"""
    return await db_manager.execute_with_retry(operation, *args, **kwargs)


async def health_check() -> dict:
    """Database health check for monitoring"""
    try:
        is_healthy = await db_manager.health_check()
        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "connection_retries": db_manager._connection_retries,
            "last_health_check": db_manager._last_health_check
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "connection_retries": db_manager._connection_retries
        }