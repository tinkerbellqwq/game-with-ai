"""
Development server runner
开发服务器启动脚本
"""

import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    # reload 模式和 workers 不能同时使用
    if settings.DEBUG:
        # 开发模式：使用 reload
        uvicorn.run(
            "app.main:app",
            host=settings.HOST,
            port=settings.PORT,
            reload=True,
            access_log=True,
            log_level=settings.LOG_LEVEL.lower()
        )
    else:
        # 生产模式：使用 workers
        uvicorn.run(
            "app.main:app",
            host=settings.HOST,
            port=settings.PORT,
            workers=settings.WORKERS,
            access_log=True,
            log_level=settings.LOG_LEVEL.lower()
        )