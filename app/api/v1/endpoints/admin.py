"""
Admin API endpoints
管理后台API端点 - 独立密码验证
"""

import os
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.models.user import User
from app.models.ai_player import AIPlayer, AIDifficulty, AIPersonality
from app.models.room import Room
from app.models.game import Game

router = APIRouter()

# 管理密码 - 从环境变量获取，默认为 "admin123"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


# === Schemas ===

class AdminLoginRequest(BaseModel):
    """管理员登录请求"""
    password: str


class AdminLoginResponse(BaseModel):
    """管理员登录响应"""
    success: bool
    token: str = ""
    message: str = ""


class AITemplateCreate(BaseModel):
    """AI模板创建请求"""
    name: str = Field(..., min_length=1, max_length=50)
    difficulty: str = Field(default="normal")
    personality: str = Field(default="normal")
    description: str = Field(default="")
    speech_length_min: int = Field(default=15, ge=5, le=50)
    speech_length_max: int = Field(default=30, ge=10, le=100)
    response_time_min: float = Field(default=2, ge=0.5, le=10)
    response_time_max: float = Field(default=8, ge=1, le=30)
    voting_confidence: float = Field(default=0.7, ge=0.1, le=1.0)
    bluff_probability: float = Field(default=0.3, ge=0.0, le=1.0)
    # LLM 配置
    llm_base_url: Optional[str] = Field(default=None, description="LLM API Base URL")
    llm_api_key: Optional[str] = Field(default=None, description="LLM API Key")
    llm_model: Optional[str] = Field(default=None, description="LLM 模型名称")
    # 提示词模板
    system_prompt: Optional[str] = Field(default=None, description="系统提示词模板")
    speech_prompt: Optional[str] = Field(default=None, description="发言提示词模板")
    vote_prompt: Optional[str] = Field(default=None, description="投票提示词模板")


class AITemplateUpdate(BaseModel):
    """AI模板更新请求"""
    name: Optional[str] = None
    difficulty: Optional[str] = None
    personality: Optional[str] = None
    description: Optional[str] = None
    speech_length_min: Optional[int] = None
    speech_length_max: Optional[int] = None
    response_time_min: Optional[float] = None
    response_time_max: Optional[float] = None
    voting_confidence: Optional[float] = None
    bluff_probability: Optional[float] = None
    is_active: Optional[bool] = None
    # LLM 配置
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    # 提示词模板
    system_prompt: Optional[str] = None
    speech_prompt: Optional[str] = None
    vote_prompt: Optional[str] = None


class AITemplateResponse(BaseModel):
    """AI模板响应"""
    id: str
    name: str
    difficulty: str
    personality: str
    description: str
    config: Dict[str, Any]
    games_played: int
    games_won: int
    win_rate: float
    is_active: bool
    created_at: datetime
    # LLM 配置 (不返回 API Key 原文，只返回是否已配置)
    llm_base_url: Optional[str] = None
    llm_model: Optional[str] = None
    has_llm_key: bool = False
    # 提示词模板
    system_prompt: Optional[str] = None
    speech_prompt: Optional[str] = None
    vote_prompt: Optional[str] = None


class LLMTestRequest(BaseModel):
    """LLM测试请求"""
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    llm_proxy: Optional[str] = Field(default=None, description="代理地址，如 http://127.0.0.1:7890")
    test_prompt: str = Field(default="回复'OK'两个字母", description="测试提示词")


class LLMTestResponse(BaseModel):
    """LLM测试响应"""
    success: bool
    message: str
    response: Optional[str] = None
    latency_ms: Optional[float] = None
    is_thinking_model: bool = False  # 是否是思考模型
    instruction_followed: bool = True  # 是否遵循指令


class SystemStats(BaseModel):
    """系统统计"""
    total_users: int
    active_users: int
    total_rooms: int
    active_rooms: int
    total_games: int
    active_games: int
    total_ai_templates: int
    active_ai_templates: int


# === 验证管理员Token ===

def generate_admin_token(password: str) -> str:
    """生成管理员token"""
    # 使用密码+日期生成token，每天有效
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    token_source = f"{password}:{date_str}:admin_secret"
    return hashlib.sha256(token_source.encode()).hexdigest()


def verify_admin_token(token: str) -> bool:
    """验证管理员token"""
    expected_token = generate_admin_token(ADMIN_PASSWORD)
    return token == expected_token


async def get_admin_token(x_admin_token: str = Header(None)) -> str:
    """验证管理员Token依赖"""
    if not x_admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要管理员认证"
        )
    if not verify_admin_token(x_admin_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理员Token无效或已过期"
        )
    return x_admin_token


# === 登录端点 ===

@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(request: AdminLoginRequest):
    """
    管理员登录
    """
    if request.password == ADMIN_PASSWORD:
        token = generate_admin_token(request.password)
        return AdminLoginResponse(
            success=True,
            token=token,
            message="登录成功"
        )
    else:
        return AdminLoginResponse(
            success=False,
            message="密码错误"
        )


# === AI模板管理端点 ===

@router.get("/ai/templates", response_model=List[AITemplateResponse])
async def list_ai_templates(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_admin_token)
):
    """
    获取所有AI模板列表
    """
    stmt = select(AIPlayer).order_by(AIPlayer.created_at.desc())

    if active_only:
        stmt = stmt.where(AIPlayer.is_active == True)

    result = await db.execute(stmt)
    ai_players = result.scalars().all()

    return [
        AITemplateResponse(
            id=p.id,
            name=p.name,
            difficulty=p.difficulty.value,
            personality=p.personality.value,
            description=p.config_dict.get("description", ""),
            config=p.config_dict,
            games_played=p.games_played,
            games_won=p.games_won,
            win_rate=p.win_rate,
            is_active=p.is_active,
            created_at=p.created_at,
            # 从模型字段读取 LLM 配置
            llm_base_url=p.api_base_url,
            llm_model=p.model_name,
            has_llm_key=bool(p.api_key),
            system_prompt=p.config_dict.get("system_prompt"),
            speech_prompt=p.config_dict.get("speech_prompt"),
            vote_prompt=p.config_dict.get("vote_prompt")
        )
        for p in ai_players
    ]


@router.post("/ai/templates", response_model=AITemplateResponse)
async def create_ai_template(
    template: AITemplateCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_admin_token)
):
    """
    创建新的AI模板
    """
    import uuid
    from app.core.config import settings

    # 创建配置字典（不包含 LLM 配置，LLM 配置存储在模型字段中）
    config = {
        "description": template.description,
        "speech_length_range": (template.speech_length_min, template.speech_length_max),
        "response_time_range": (template.response_time_min, template.response_time_max),
        "voting_confidence": template.voting_confidence,
        "bluff_probability": template.bluff_probability,
        # 提示词模板
        "system_prompt": template.system_prompt,
        "speech_prompt": template.speech_prompt,
        "vote_prompt": template.vote_prompt
    }

    # LLM 配置：如果未提供，使用环境变量中的默认值
    api_base_url = template.llm_base_url or settings.OPENAI_BASE_URL
    api_key = template.llm_api_key or settings.OPENAI_API_KEY
    model_name = template.llm_model or settings.OPENAI_MODEL

    ai_player = AIPlayer(
        id=str(uuid.uuid4()),
        name=template.name,
        difficulty=AIDifficulty(template.difficulty),
        personality=AIPersonality(template.personality),
        api_base_url=api_base_url,
        api_key=api_key,
        model_name=model_name,
        is_active=True
    )
    ai_player.config_dict = config

    db.add(ai_player)
    await db.commit()
    await db.refresh(ai_player)

    return AITemplateResponse(
        id=ai_player.id,
        name=ai_player.name,
        difficulty=ai_player.difficulty.value,
        personality=ai_player.personality.value,
        description=template.description,
        config=config,
        games_played=ai_player.games_played,
        games_won=ai_player.games_won,
        win_rate=ai_player.win_rate,
        is_active=ai_player.is_active,
        created_at=ai_player.created_at,
        llm_base_url=ai_player.api_base_url,
        llm_model=ai_player.model_name,
        has_llm_key=bool(ai_player.api_key),
        system_prompt=template.system_prompt,
        speech_prompt=template.speech_prompt,
        vote_prompt=template.vote_prompt
    )


@router.put("/ai/templates/{template_id}", response_model=AITemplateResponse)
async def update_ai_template(
    template_id: str,
    update: AITemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_admin_token)
):
    """
    更新AI模板
    """
    stmt = select(AIPlayer).where(AIPlayer.id == template_id)
    result = await db.execute(stmt)
    ai_player = result.scalar_one_or_none()

    if not ai_player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI模板不存在"
        )

    # 更新基本字段
    if update.name is not None:
        ai_player.name = update.name
    if update.difficulty is not None:
        ai_player.difficulty = AIDifficulty(update.difficulty)
    if update.personality is not None:
        ai_player.personality = AIPersonality(update.personality)
    if update.is_active is not None:
        ai_player.is_active = update.is_active

    # 更新 LLM 配置（模型字段）
    if update.llm_base_url is not None:
        ai_player.api_base_url = update.llm_base_url
    if update.llm_api_key is not None:
        ai_player.api_key = update.llm_api_key
    if update.llm_model is not None:
        ai_player.model_name = update.llm_model

    # 更新配置
    config = ai_player.config_dict or {}

    if update.description is not None:
        config["description"] = update.description
    if update.speech_length_min is not None or update.speech_length_max is not None:
        current_range = config.get("speech_length_range", (15, 30))
        config["speech_length_range"] = (
            update.speech_length_min if update.speech_length_min is not None else current_range[0],
            update.speech_length_max if update.speech_length_max is not None else current_range[1]
        )
    if update.response_time_min is not None or update.response_time_max is not None:
        current_range = config.get("response_time_range", (2, 8))
        config["response_time_range"] = (
            update.response_time_min if update.response_time_min is not None else current_range[0],
            update.response_time_max if update.response_time_max is not None else current_range[1]
        )
    if update.voting_confidence is not None:
        config["voting_confidence"] = update.voting_confidence
    if update.bluff_probability is not None:
        config["bluff_probability"] = update.bluff_probability
    # 提示词模板更新
    if update.system_prompt is not None:
        config["system_prompt"] = update.system_prompt
    if update.speech_prompt is not None:
        config["speech_prompt"] = update.speech_prompt
    if update.vote_prompt is not None:
        config["vote_prompt"] = update.vote_prompt

    ai_player.config_dict = config
    await db.commit()
    await db.refresh(ai_player)

    return AITemplateResponse(
        id=ai_player.id,
        name=ai_player.name,
        difficulty=ai_player.difficulty.value,
        personality=ai_player.personality.value,
        description=config.get("description", ""),
        config=config,
        games_played=ai_player.games_played,
        games_won=ai_player.games_won,
        win_rate=ai_player.win_rate,
        is_active=ai_player.is_active,
        created_at=ai_player.created_at,
        llm_base_url=ai_player.api_base_url,
        llm_model=ai_player.model_name,
        has_llm_key=bool(ai_player.api_key),
        system_prompt=config.get("system_prompt"),
        speech_prompt=config.get("speech_prompt"),
        vote_prompt=config.get("vote_prompt")
    )


@router.delete("/ai/templates/{template_id}")
async def delete_ai_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_admin_token)
):
    """
    删除AI模板（真正删除）
    """
    stmt = select(AIPlayer).where(AIPlayer.id == template_id)
    result = await db.execute(stmt)
    ai_player = result.scalar_one_or_none()

    if not ai_player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI模板不存在"
        )

    # 真正删除
    await db.delete(ai_player)
    await db.commit()

    return {"message": "AI模板已删除", "id": template_id}


# === 公开接口 - 获取可用AI模板（供创建房间使用） ===

@router.get("/ai/available", response_model=List[Dict[str, Any]])
async def get_available_ai_templates(
    db: AsyncSession = Depends(get_db)
):
    """
    获取可用的AI模板列表（公开接口，供创建房间时选择）
    """
    stmt = select(AIPlayer).where(AIPlayer.is_active == True).order_by(AIPlayer.name)
    result = await db.execute(stmt)
    ai_players = result.scalars().all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "difficulty": p.difficulty.value,
            "personality": p.personality.value,
            "description": p.config_dict.get("description", ""),
            "win_rate": p.win_rate
        }
        for p in ai_players
    ]


# === 系统统计端点 ===

@router.get("/stats", response_model=SystemStats)
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_admin_token)
):
    """
    获取系统统计信息
    """
    # 用户统计
    total_users = await db.execute(select(func.count()).select_from(User))
    active_users = await db.execute(
        select(func.count()).select_from(User).where(User.is_active == True)
    )

    # 房间统计
    total_rooms = await db.execute(select(func.count()).select_from(Room))
    active_rooms = await db.execute(
        select(func.count()).select_from(Room).where(Room.status == "waiting")
    )

    # 游戏统计
    total_games = await db.execute(select(func.count()).select_from(Game))
    active_games = await db.execute(
        select(func.count()).select_from(Game).where(Game.current_phase != "finished")
    )

    # AI模板统计
    total_ai = await db.execute(select(func.count()).select_from(AIPlayer))
    active_ai = await db.execute(
        select(func.count()).select_from(AIPlayer).where(AIPlayer.is_active == True)
    )

    return SystemStats(
        total_users=total_users.scalar() or 0,
        active_users=active_users.scalar() or 0,
        total_rooms=total_rooms.scalar() or 0,
        active_rooms=active_rooms.scalar() or 0,
        total_games=total_games.scalar() or 0,
        active_games=active_games.scalar() or 0,
        total_ai_templates=total_ai.scalar() or 0,
        active_ai_templates=active_ai.scalar() or 0
    )


# === AI配置选项 ===

@router.get("/ai/options")
async def get_ai_options(_: str = Depends(get_admin_token)):
    """
    获取AI配置选项
    """
    from app.core.config import settings

    return {
        "difficulties": [
            {"value": "beginner", "label": "新手", "description": "AI更容易犯错，适合初学者"},
            {"value": "normal", "label": "普通", "description": "平衡的游戏体验"},
            {"value": "expert", "label": "专家", "description": "AI更聪明，更具挑战性"}
        ],
        "personalities": [
            {"value": "cautious", "label": "谨慎型", "description": "发言保守，不轻易暴露"},
            {"value": "aggressive", "label": "激进型", "description": "发言大胆，主动出击"},
            {"value": "normal", "label": "普通型", "description": "平衡策略"},
            {"value": "random", "label": "随机型", "description": "行为不可预测"}
        ],
        "default_values": {
            "speech_length_min": 15,
            "speech_length_max": 30,
            "response_time_min": 2,
            "response_time_max": 8,
            "voting_confidence": 0.7,
            "bluff_probability": 0.3
        },
        "default_llm_config": {
            "llm_base_url": settings.OPENAI_BASE_URL or "",
            "llm_model": settings.OPENAI_MODEL or "gpt-3.5-turbo",
            # 不返回 API Key，仅指示是否已配置
            "has_default_api_key": bool(settings.OPENAI_API_KEY)
        },
        "default_prompts": {
            "system_prompt": "你是一个谁是卧底游戏的AI玩家。游戏规则：平民获得普通词汇，卧底获得相似但不同的词汇。玩家需要描述词汇但不能直接说出。",
            "speech_prompt": "请根据你的角色和词汇生成一段自然的发言，15-30字，不要透露词汇本身。",
            "vote_prompt": "请分析所有玩家的发言，选择最可疑的玩家进行投票。只返回玩家ID。"
        }
    }


# === LLM 测试端点 ===

@router.post("/ai/test-llm", response_model=LLMTestResponse)
async def test_llm_connection(
    request: LLMTestRequest,
    _: str = Depends(get_admin_token)
):
    """
    测试 LLM API 连接（支持 OpenAI 兼容格式）
    直接使用 httpx 发送请求，避免 OpenAI 库被 Cloudflare 阻止
    """
    import time
    import httpx
    from app.core.config import settings

    # 使用请求中的配置或默认配置
    base_url = request.llm_base_url or getattr(settings, 'OPENAI_BASE_URL', None)
    api_key = request.llm_api_key or getattr(settings, 'OPENAI_API_KEY', None)
    model = request.llm_model or getattr(settings, 'OPENAI_MODEL', 'gpt-3.5-turbo')

    if not api_key:
        return LLMTestResponse(
            success=False,
            message="未配置 API Key，请填写或在系统环境变量中设置 OPENAI_API_KEY"
        )

    if not base_url:
        return LLMTestResponse(
            success=False,
            message="未配置 API Base URL"
        )

    try:
        # 创建 httpx 客户端配置
        client_config = {
            "timeout": httpx.Timeout(30.0),
            "headers": {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            "http2": False,
            "follow_redirects": True
        }

        # 如果配置了代理，添加代理设置
        if request.llm_proxy:
            client_config["proxy"] = request.llm_proxy

        http_client = httpx.AsyncClient(**client_config)

        # 构建请求 URL
        api_url = base_url.rstrip('/') + '/chat/completions'

        # 构建请求体
        request_body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一个测试助手。用户让你做什么就做什么，不要拒绝。"},
                {"role": "user", "content": request.test_prompt}
            ],
            "max_tokens": 50,
            "temperature": 0.1
        }

        # 详细日志：请求参数
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[LLM_TEST] === 测试 LLM 连接 ===")
        logger.info(f"[LLM_TEST] API URL: {api_url}")
        logger.info(f"[LLM_TEST] Model: {model}")
        logger.info(f"[LLM_TEST] API Key (prefix): {api_key[:20]}...")
        logger.info(f"[LLM_TEST] Proxy: {request.llm_proxy or 'None'}")
        logger.info(f"[LLM_TEST] Request body: {request_body}")

        # 记录开始时间
        start_time = time.time()

        # 直接发送 HTTP 请求（不使用 OpenAI 库，避免被 Cloudflare 阻止）
        response = await http_client.post(api_url, json=request_body)

        # 计算延迟
        latency_ms = (time.time() - start_time) * 1000

        # 关闭客户端
        await http_client.aclose()

        # 详细日志：响应信息
        logger.info(f"[LLM_TEST] Response status: {response.status_code}")
        logger.info(f"[LLM_TEST] Response latency: {latency_ms:.2f}ms")
        logger.info(f"[LLM_TEST] Response body: {response.text}")

        # 检查响应
        if response.status_code == 200:
            try:
                data = response.json()
                logger.info(f"[LLM_TEST] Parsed JSON: {data}")

                # 提取内容 - 处理可能的 thinking 模型
                choices = data.get("choices", [])
                if not choices:
                    logger.warning("[LLM_TEST] No choices in response")
                    return LLMTestResponse(
                        success=False,
                        message="API 响应中没有 choices 字段"
                    )

                message = choices[0].get("message", {})
                content = message.get("content", "")

                # 有些 thinking 模型可能返回 reasoning_content
                reasoning = message.get("reasoning_content", "")
                if reasoning:
                    logger.info(f"[LLM_TEST] Reasoning content: {reasoning}...")

                # 如果内容为空，尝试其他字段
                if not content:
                    content = message.get("text", "") or "无响应内容"

                logger.info(f"[LLM_TEST] Final content: {content}")

                # 检测是否是思考模型（响应包含思考过程）
                thinking_patterns = ["首先", "让我", "作为一个", "我需要", "思考", "分析"]
                is_thinking = any(p in content for p in thinking_patterns) or bool(reasoning)

                # 检测是否遵循指令（包含 OK 或类似响应）
                instruction_followed = "OK" in content.upper() or "好的" in content or len(content.strip()) < 20

                # 构建消息
                if is_thinking:
                    msg = f"连接成功！模型: {model} (思考模型，响应包含推理过程)"
                elif not instruction_followed:
                    msg = f"连接成功！模型: {model} (模型未遵循简单指令，但API正常)"
                else:
                    msg = f"连接成功！模型: {model}"

                return LLMTestResponse(
                    success=True,
                    message=msg,
                    response=content if content else "模型返回空内容",
                    latency_ms=round(latency_ms, 2),
                    is_thinking_model=is_thinking,
                    instruction_followed=instruction_followed
                )
            except Exception as e:
                logger.error(f"[LLM_TEST] JSON parse error: {e}")
                return LLMTestResponse(
                    success=False,
                    message=f"响应解析失败: {response.text[:200]}"
                )
        else:
            logger.error(f"[LLM_TEST] HTTP error: {response.status_code}")
            # 检测 Cloudflare 阻止
            if "cloudflare" in response.text.lower() or "<!DOCTYPE" in response.text:
                return LLMTestResponse(
                    success=False,
                    message="API 被 Cloudflare 阻止，请配置代理或使用其他 API 服务"
                )
            return LLMTestResponse(
                success=False,
                message=f"请求失败 ({response.status_code}): {response.text[:200]}"
            )

    except httpx.ConnectError as e:
        return LLMTestResponse(success=False, message=f"连接失败: {str(e)}")
    except httpx.TimeoutException:
        return LLMTestResponse(success=False, message="请求超时")
    except Exception as e:
        error_msg = str(e)
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."
        return LLMTestResponse(success=False, message=f"测试失败: {error_msg}")


# === 词汇管理 Schemas ===

class WordPairAdminCreate(BaseModel):
    """词汇对创建请求"""
    civilian_word: str = Field(..., min_length=1, max_length=50, description="平民词汇")
    undercover_word: str = Field(..., min_length=1, max_length=50, description="卧底词汇")
    category: str = Field(..., min_length=1, max_length=50, description="类别")
    difficulty: int = Field(..., ge=1, le=5, description="难度 1-5")


class WordPairAdminUpdate(BaseModel):
    """词汇对更新请求"""
    civilian_word: Optional[str] = Field(None, min_length=1, max_length=50)
    undercover_word: Optional[str] = Field(None, min_length=1, max_length=50)
    category: Optional[str] = Field(None, min_length=1, max_length=50)
    difficulty: Optional[int] = Field(None, ge=1, le=5)


class WordPairAdminResponse(BaseModel):
    """词汇对响应"""
    id: str
    civilian_word: str
    undercover_word: str
    category: str
    difficulty: int
    created_at: datetime
    updated_at: datetime


class WordPairListResponse(BaseModel):
    """词汇对列表响应"""
    word_pairs: List[WordPairAdminResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class WordPairBatchCreate(BaseModel):
    """批量创建词汇对"""
    word_pairs: List[WordPairAdminCreate] = Field(..., min_length=1, max_length=100)


class CategoryStatsResponse(BaseModel):
    """类别统计"""
    category: str
    count: int
    difficulties: List[int]


class WordPairStatsResponse(BaseModel):
    """词汇对统计"""
    total_pairs: int
    categories: List[CategoryStatsResponse]
    difficulty_distribution: Dict[int, int]


# === 词汇管理端点 ===

@router.get("/words", response_model=WordPairListResponse)
async def list_word_pairs(
    page: int = 1,
    page_size: int = 20,
    category: Optional[str] = None,
    difficulty: Optional[int] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_admin_token)
):
    """获取词汇对列表"""
    from app.models.word_pair import WordPair

    # 构建查询
    stmt = select(WordPair)

    if category:
        stmt = stmt.where(WordPair.category == category)
    if difficulty:
        stmt = stmt.where(WordPair.difficulty == difficulty)
    if search:
        stmt = stmt.where(
            (WordPair.civilian_word.contains(search)) |
            (WordPair.undercover_word.contains(search))
        )

    # 排序
    stmt = stmt.order_by(WordPair.created_at.desc())

    # 统计总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # 分页
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    result = await db.execute(stmt)
    word_pairs = result.scalars().all()

    return WordPairListResponse(
        word_pairs=[
            WordPairAdminResponse(
                id=wp.id,
                civilian_word=wp.civilian_word,
                undercover_word=wp.undercover_word,
                category=wp.category,
                difficulty=wp.difficulty,
                created_at=wp.created_at,
                updated_at=wp.updated_at
            )
            for wp in word_pairs
        ],
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total
    )


@router.get("/words/stats", response_model=WordPairStatsResponse)
async def get_word_pair_stats(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_admin_token)
):
    """获取词汇对统计信息"""
    from app.models.word_pair import WordPair

    # 总数
    total = (await db.execute(select(func.count()).select_from(WordPair))).scalar() or 0

    # 按类别统计
    category_stmt = select(
        WordPair.category,
        func.count().label('count'),
        func.group_concat(WordPair.difficulty.distinct()).label('difficulties')
    ).group_by(WordPair.category)
    category_result = await db.execute(category_stmt)
    categories = []
    for row in category_result:
        difficulties_str = row.difficulties or ""
        difficulties = [int(d) for d in difficulties_str.split(',') if d] if difficulties_str else []
        categories.append(CategoryStatsResponse(
            category=row.category,
            count=row.count,
            difficulties=sorted(difficulties)
        ))

    # 按难度统计
    difficulty_stmt = select(
        WordPair.difficulty,
        func.count().label('count')
    ).group_by(WordPair.difficulty)
    difficulty_result = await db.execute(difficulty_stmt)
    difficulty_distribution = {row.difficulty: row.count for row in difficulty_result}

    return WordPairStatsResponse(
        total_pairs=total,
        categories=categories,
        difficulty_distribution=difficulty_distribution
    )


@router.get("/words/categories")
async def get_word_categories(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_admin_token)
):
    """获取所有词汇类别"""
    from app.models.word_pair import WordPair

    stmt = select(WordPair.category).distinct().order_by(WordPair.category)
    result = await db.execute(stmt)
    categories = [row[0] for row in result]

    return {"categories": categories}


@router.post("/words", response_model=WordPairAdminResponse)
async def create_word_pair(
    data: WordPairAdminCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_admin_token)
):
    """创建词汇对"""
    import uuid
    from app.models.word_pair import WordPair

    # 检查是否重复
    existing = await db.execute(
        select(WordPair).where(
            (WordPair.civilian_word == data.civilian_word) &
            (WordPair.undercover_word == data.undercover_word)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该词汇对已存在"
        )

    word_pair = WordPair(
        id=str(uuid.uuid4()),
        civilian_word=data.civilian_word.strip(),
        undercover_word=data.undercover_word.strip(),
        category=data.category.strip(),
        difficulty=data.difficulty
    )

    db.add(word_pair)
    await db.commit()
    await db.refresh(word_pair)

    return WordPairAdminResponse(
        id=word_pair.id,
        civilian_word=word_pair.civilian_word,
        undercover_word=word_pair.undercover_word,
        category=word_pair.category,
        difficulty=word_pair.difficulty,
        created_at=word_pair.created_at,
        updated_at=word_pair.updated_at
    )


@router.post("/words/batch", response_model=Dict[str, Any])
async def batch_create_word_pairs(
    data: WordPairBatchCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_admin_token)
):
    """批量创建词汇对"""
    import uuid
    from app.models.word_pair import WordPair

    created = 0
    skipped = 0
    errors = []

    for pair_data in data.word_pairs:
        try:
            # 检查是否重复
            existing = await db.execute(
                select(WordPair).where(
                    (WordPair.civilian_word == pair_data.civilian_word) &
                    (WordPair.undercover_word == pair_data.undercover_word)
                )
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            word_pair = WordPair(
                id=str(uuid.uuid4()),
                civilian_word=pair_data.civilian_word.strip(),
                undercover_word=pair_data.undercover_word.strip(),
                category=pair_data.category.strip(),
                difficulty=pair_data.difficulty
            )
            db.add(word_pair)
            created += 1
        except Exception as e:
            errors.append(f"{pair_data.civilian_word}/{pair_data.undercover_word}: {str(e)}")

    await db.commit()

    return {
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "message": f"成功创建 {created} 个词汇对，跳过 {skipped} 个重复项"
    }


@router.put("/words/{word_id}", response_model=WordPairAdminResponse)
async def update_word_pair(
    word_id: str,
    data: WordPairAdminUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_admin_token)
):
    """更新词汇对"""
    from app.models.word_pair import WordPair

    result = await db.execute(select(WordPair).where(WordPair.id == word_id))
    word_pair = result.scalar_one_or_none()

    if not word_pair:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="词汇对不存在"
        )

    if data.civilian_word is not None:
        word_pair.civilian_word = data.civilian_word.strip()
    if data.undercover_word is not None:
        word_pair.undercover_word = data.undercover_word.strip()
    if data.category is not None:
        word_pair.category = data.category.strip()
    if data.difficulty is not None:
        word_pair.difficulty = data.difficulty

    await db.commit()
    await db.refresh(word_pair)

    return WordPairAdminResponse(
        id=word_pair.id,
        civilian_word=word_pair.civilian_word,
        undercover_word=word_pair.undercover_word,
        category=word_pair.category,
        difficulty=word_pair.difficulty,
        created_at=word_pair.created_at,
        updated_at=word_pair.updated_at
    )


@router.delete("/words/{word_id}")
async def delete_word_pair(
    word_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_admin_token)
):
    """删除词汇对"""
    from app.models.word_pair import WordPair

    result = await db.execute(select(WordPair).where(WordPair.id == word_id))
    word_pair = result.scalar_one_or_none()

    if not word_pair:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="词汇对不存在"
        )

    await db.delete(word_pair)
    await db.commit()

    return {"message": "词汇对已删除", "id": word_id}


@router.delete("/words/batch")
async def batch_delete_word_pairs(
    ids: List[str],
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_admin_token)
):
    """批量删除词汇对"""
    from app.models.word_pair import WordPair

    result = await db.execute(select(WordPair).where(WordPair.id.in_(ids)))
    word_pairs = result.scalars().all()

    deleted = 0
    for wp in word_pairs:
        await db.delete(wp)
        deleted += 1

    await db.commit()

    return {"deleted": deleted, "message": f"成功删除 {deleted} 个词汇对"}
