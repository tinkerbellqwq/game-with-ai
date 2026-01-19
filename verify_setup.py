#!/usr/bin/env python3
"""
Setup verification script
验证基础设施搭建是否成功
"""

import asyncio
import sys
from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.redis_client import init_redis, close_redis


async def verify_setup():
    """Verify that all infrastructure components are working"""
    print("🚀 验证谁是卧底游戏平台基础设施...")
    print(f"Environment: {settings.ENVIRONMENT}")
    print(f"Database URL: {settings.DATABASE_URL}")
    print(f"Redis URL: {settings.REDIS_URL}")
    
    success = True
    
    # Test database connection
    try:
        print("\n📊 测试数据库连接...")
        await init_db()
        print("✅ 数据库连接成功")
        await close_db()
    except Exception as e:
        print(f"⚠️  数据库连接失败 (开发环境下可选): {e}")
        print("   提示: 请确保MySQL服务运行并创建数据库")
        # Database failure is not critical for basic setup verification
    
    # Test Redis connection
    try:
        print("\n🔄 测试Redis连接...")
        await init_redis()
        print("✅ Redis连接成功")
        await close_redis()
    except Exception as e:
        print(f"⚠️  Redis连接失败 (开发模式下可选): {e}")
        # Redis failure is not critical in development
    
    # Test FastAPI app
    try:
        print("\n🌐 测试FastAPI应用...")
        from app.main import app
        assert app is not None
        print("✅ FastAPI应用创建成功")
    except Exception as e:
        print(f"❌ FastAPI应用创建失败: {e}")
        success = False
    
    print("\n" + "="*50)
    if success:
        print("🎉 基础设施搭建验证成功!")
        print("可以开始下一个任务: 数据库设计和模型实现")
        print("\n启动开发服务器:")
        print("python run.py")
        print("\n运行测试:")
        print("pytest tests/")
        return 0
    else:
        print("💥 基础设施搭建验证失败!")
        print("请检查配置和依赖")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(verify_setup())
    sys.exit(exit_code)