"""
API v1 router
API v1 路由配置 - 完整系统集成
"""

from fastapi import APIRouter

# Import route modules
from app.api.v1.endpoints import auth, rooms, websocket, settlement, leaderboard, health, games, admin, ai_players

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(rooms.router, prefix="/rooms", tags=["rooms"])
api_router.include_router(games.router, prefix="/games", tags=["games"])
api_router.include_router(ai_players.router, prefix="/ai-players", tags=["ai-players"])
api_router.include_router(websocket.router, prefix="/ws", tags=["websocket"])
api_router.include_router(settlement.router, prefix="/settlement", tags=["settlement"])
api_router.include_router(leaderboard.router, prefix="/leaderboard", tags=["leaderboard"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])