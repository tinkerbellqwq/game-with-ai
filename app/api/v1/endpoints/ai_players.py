"""
AI Player management API endpoints
AI 玩家管理 API 端点
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
import uuid
import httpx

from app.core.database import get_db
from app.core.config import settings
from app.models.ai_player import AIPlayer, AIDifficulty, AIPersonality

router = APIRouter()


class AIPlayerResponse(BaseModel):
    """AI 玩家响应模型"""
    id: str
    name: str
    model_name: Optional[str] = None
    difficulty: str
    personality: str
    games_played: int = 0
    games_won: int = 0
    win_rate: float = 0.0
    is_active: bool = True
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None

    class Config:
        from_attributes = True


class AIPlayerListResponse(BaseModel):
    """AI 玩家列表响应"""
    ai_players: List[AIPlayerResponse]
    total: int


class CreateAIPlayerRequest(BaseModel):
    """创建 AI 玩家请求"""
    name: str = Field(..., min_length=1, max_length=50)
    model_name: str = Field(..., min_length=1, max_length=100)
    difficulty: str = Field(default="normal")
    personality: str = Field(default="normal")
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_active: bool = True


class UpdateAIPlayerRequest(BaseModel):
    """更新 AI 玩家请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    model_name: Optional[str] = Field(None, min_length=1, max_length=100)
    difficulty: Optional[str] = None
    personality: Optional[str] = None
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = None


def _mask_api_key(key: Optional[str]) -> Optional[str]:
    """遮盖 API 密钥，只显示前4位和后4位"""
    if not key or len(key) < 12:
        return key
    return f"{key[:4]}...{key[-4:]}"


def _ai_to_response(ai: AIPlayer, mask_key: bool = True) -> AIPlayerResponse:
    """将 AI 玩家模型转换为响应模型"""
    return AIPlayerResponse(
        id=ai.id,
        name=ai.name,
        model_name=ai.model_name,
        difficulty=ai.difficulty.value if ai.difficulty else "normal",
        personality=ai.personality.value if ai.personality else "normal",
        games_played=ai.games_played,
        games_won=ai.games_won,
        win_rate=ai.win_rate,
        is_active=ai.is_active,
        api_base_url=ai.api_base_url,
        api_key=_mask_api_key(ai.api_key) if mask_key else ai.api_key
    )


class ModelInfo(BaseModel):
    """模型信息"""
    id: str
    name: str
    owned_by: Optional[str] = None


class AvailableModelsResponse(BaseModel):
    """可用模型列表响应"""
    models: List[ModelInfo]
    total: int
    source: str  # "api" 或 "config"


class FetchModelsRequest(BaseModel):
    """获取模型列表请求"""
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None
    ai_player_id: Optional[str] = None  # 如果提供，使用该 AI 玩家的配置


def _get_models_from_config() -> AvailableModelsResponse:
    """从配置文件获取模型列表"""
    models = []
    for model_name in settings.ai_models_list:
        models.append(ModelInfo(
            id=model_name,
            name=model_name,
            owned_by="config"
        ))

    return AvailableModelsResponse(
        models=models,
        total=len(models),
        source="config"
    )


@router.post("/fetch-models", response_model=AvailableModelsResponse)
async def fetch_available_models(
    request: FetchModelsRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    获取可用的 LLM 模型列表

    使用传入的 API 配置获取模型列表，如果失败则使用配置文件中的列表

    - **api_base_url**: API 基础 URL
    - **api_key**: API 密钥
    - **ai_player_id**: 可选，如果提供则使用该 AI 玩家数据库中的配置
    """
    import logging
    logger = logging.getLogger(__name__)

    base_url = request.api_base_url
    key = request.api_key

    # 如果提供了 ai_player_id，从数据库获取该 AI 的配置
    if request.ai_player_id:
        logger.info(f"Fetching API config from AI player: {request.ai_player_id}")
        stmt = select(AIPlayer).where(AIPlayer.id == request.ai_player_id)
        result = await db.execute(stmt)
        ai_player = result.scalar_one_or_none()

        if ai_player:
            # 使用数据库中的完整配置
            if ai_player.api_base_url:
                base_url = ai_player.api_base_url
            if ai_player.api_key:
                key = ai_player.api_key
            logger.info(f"Using AI player config: api_base_url={base_url}, api_key={'***' if key else None}")

    logger.info(f"fetch_available_models called with api_base_url={base_url}, api_key={'***' if key else None}")

    # 如果没有提供 API 配置，使用 .env 中的默认配置
    if not base_url:
        base_url = settings.OPENAI_BASE_URL
        logger.info(f"Using default OPENAI_BASE_URL: {base_url}")
    if not key:
        key = settings.OPENAI_API_KEY
        logger.info("Using default OPENAI_API_KEY")

    # 如果仍然没有配置，返回配置文件中的模型列表
    if not base_url or not key:
        logger.info("No API config available, using config file")
        return _get_models_from_config()

    # 尝试从 API 获取模型列表
    try:
        # 构建请求 URL
        models_url = f"{base_url.rstrip('/')}/models"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                models_url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"
                }
            )

            if response.status_code == 200:
                data = response.json()
                models_data = data.get("data", [])

                models = []
                for model in models_data:
                    model_id = model.get("id", "")
                    models.append(ModelInfo(
                        id=model_id,
                        name=model_id,
                        owned_by=model.get("owned_by")
                    ))

                # 按名称排序
                models.sort(key=lambda x: x.name.lower())

                return AvailableModelsResponse(
                    models=models,
                    total=len(models),
                    source="api"
                )
            else:
                # API 请求失败，使用配置文件
                return _get_models_from_config()

    except Exception:
        # 请求异常，使用配置文件
        return _get_models_from_config()


@router.get("/", response_model=AIPlayerListResponse)
async def list_ai_players(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    获取可用的 AI 玩家列表

    - **active_only**: 是否只返回激活的 AI（默认 False）
    """
    try:
        stmt = select(AIPlayer)

        # 只返回有 model_name 的预配置 AI
        stmt = stmt.where(AIPlayer.model_name.isnot(None))

        if active_only:
            stmt = stmt.where(AIPlayer.is_active == True)

        stmt = stmt.order_by(AIPlayer.name)

        result = await db.execute(stmt)
        ai_players = result.scalars().all()

        responses = [_ai_to_response(ai) for ai in ai_players]

        return AIPlayerListResponse(
            ai_players=responses,
            total=len(responses)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取 AI 玩家列表失败: {str(e)}"
        )


@router.get("/{ai_player_id}", response_model=AIPlayerResponse)
async def get_ai_player(
    ai_player_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定 AI 玩家详情

    - **ai_player_id**: AI 玩家 ID
    """
    try:
        stmt = select(AIPlayer).where(AIPlayer.id == ai_player_id)
        result = await db.execute(stmt)
        ai_player = result.scalar_one_or_none()

        if not ai_player:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI 玩家不存在"
            )

        return _ai_to_response(ai_player)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取 AI 玩家失败: {str(e)}"
        )


@router.post("/", response_model=AIPlayerResponse, status_code=status.HTTP_201_CREATED)
async def create_ai_player(
    request: CreateAIPlayerRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    创建新的 AI 玩家

    - **name**: AI 玩家名称
    - **model_name**: 使用的 LLM 模型名称
    - **difficulty**: 难度等级 (beginner/normal/expert)
    - **personality**: 性格类型 (cautious/normal/aggressive/random)
    """
    try:
        # 验证难度等级
        try:
            difficulty = AIDifficulty(request.difficulty)
        except ValueError:
            difficulty = AIDifficulty.NORMAL

        # 验证性格类型
        try:
            personality = AIPersonality(request.personality)
        except ValueError:
            personality = AIPersonality.NORMAL

        # 创建新 AI 玩家
        ai_player = AIPlayer(
            id=str(uuid.uuid4()),
            name=request.name,
            model_name=request.model_name,
            difficulty=difficulty,
            personality=personality,
            api_base_url=request.api_base_url,
            api_key=request.api_key,
            is_active=request.is_active,
            games_played=0,
            games_won=0,
            total_speeches=0,
            total_votes=0
        )

        db.add(ai_player)
        await db.commit()
        await db.refresh(ai_player)

        return _ai_to_response(ai_player)

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建 AI 玩家失败: {str(e)}"
        )


@router.put("/{ai_player_id}", response_model=AIPlayerResponse)
async def update_ai_player(
    ai_player_id: str,
    request: UpdateAIPlayerRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    更新 AI 玩家信息

    - **ai_player_id**: AI 玩家 ID
    """
    try:
        stmt = select(AIPlayer).where(AIPlayer.id == ai_player_id)
        result = await db.execute(stmt)
        ai_player = result.scalar_one_or_none()

        if not ai_player:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI 玩家不存在"
            )

        # 更新字段
        if request.name is not None:
            ai_player.name = request.name

        if request.model_name is not None:
            ai_player.model_name = request.model_name

        if request.difficulty is not None:
            try:
                ai_player.difficulty = AIDifficulty(request.difficulty)
            except ValueError:
                pass

        if request.personality is not None:
            try:
                ai_player.personality = AIPersonality(request.personality)
            except ValueError:
                pass

        if request.api_base_url is not None:
            ai_player.api_base_url = request.api_base_url

        # 只有当提供了新的完整 API key 时才更新（跳过遮盖值）
        if request.api_key is not None:
            # 检查是否是遮盖值（包含 "..." 的格式）
            if "..." not in request.api_key:
                ai_player.api_key = request.api_key
            # 如果是遮盖值，保持原有的 api_key 不变

        if request.is_active is not None:
            ai_player.is_active = request.is_active

        await db.commit()
        await db.refresh(ai_player)

        return _ai_to_response(ai_player)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新 AI 玩家失败: {str(e)}"
        )


@router.delete("/{ai_player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ai_player(
    ai_player_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    删除 AI 玩家

    - **ai_player_id**: AI 玩家 ID
    """
    try:
        stmt = select(AIPlayer).where(AIPlayer.id == ai_player_id)
        result = await db.execute(stmt)
        ai_player = result.scalar_one_or_none()

        if not ai_player:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI 玩家不存在"
            )

        await db.delete(ai_player)
        await db.commit()

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除 AI 玩家失败: {str(e)}"
        )


@router.post("/{ai_player_id}/toggle-status", response_model=AIPlayerResponse)
async def toggle_ai_player_status(
    ai_player_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    切换 AI 玩家的激活状态

    - **ai_player_id**: AI 玩家 ID
    """
    try:
        stmt = select(AIPlayer).where(AIPlayer.id == ai_player_id)
        result = await db.execute(stmt)
        ai_player = result.scalar_one_or_none()

        if not ai_player:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI 玩家不存在"
            )

        ai_player.is_active = not ai_player.is_active
        await db.commit()
        await db.refresh(ai_player)

        return _ai_to_response(ai_player)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"切换 AI 玩家状态失败: {str(e)}"
        )


class TestAPIResponse(BaseModel):
    """API 测试响应"""
    success: bool
    message: str
    latency_ms: Optional[float] = None
    model_response: Optional[str] = None
    # 新增：游戏场景测试结果
    game_test_success: Optional[bool] = None
    game_test_message: Optional[str] = None
    game_test_speech: Optional[str] = None
    game_test_latency_ms: Optional[float] = None


@router.post("/{ai_player_id}/test-api", response_model=TestAPIResponse)
async def test_ai_player_api(
    ai_player_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    测试 AI 玩家的 API 配置是否可用

    包含两个测试：
    1. 连通性测试：简单的 API 调用检查
    2. 游戏场景测试：模拟谁是卧底游戏中的发言场景

    - **ai_player_id**: AI 玩家 ID
    """
    import time
    import logging
    import re
    logger = logging.getLogger(__name__)

    try:
        # 从数据库获取 AI 玩家配置
        stmt = select(AIPlayer).where(AIPlayer.id == ai_player_id)
        result = await db.execute(stmt)
        ai_player = result.scalar_one_or_none()

        if not ai_player:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI 玩家不存在"
            )

        # 获取 API 配置
        base_url = ai_player.api_base_url or settings.OPENAI_BASE_URL
        api_key = ai_player.api_key or settings.OPENAI_API_KEY
        model = ai_player.model_name or "gpt-3.5-turbo"

        if not base_url:
            return TestAPIResponse(
                success=False,
                message="未配置 API Base URL"
            )

        if not api_key:
            return TestAPIResponse(
                success=False,
                message="未配置 API Key"
            )

        logger.info(f"[AI_TEST] Testing API for AI player: {ai_player.name}")
        logger.info(f"[AI_TEST] API URL: {base_url}")
        logger.info(f"[AI_TEST] Model: {model}")

        api_url = base_url.rstrip('/') + '/chat/completions'

        # ========== 测试 1: 连通性测试 ==========
        connectivity_request = {
            "model": model,
            "messages": [
                {"role": "user", "content": "Say 'API connection successful' in exactly 3 words."}
            ],
            "max_tokens": 20,
            "temperature": 0.1
        }

        start_time = time.time()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        ) as client:
            response = await client.post(api_url, json=connectivity_request)

        latency_ms = (time.time() - start_time) * 1000

        logger.info(f"[AI_TEST] Connectivity test - Status: {response.status_code}, Latency: {latency_ms:.2f}ms")

        if response.status_code != 200:
            error_text = response.text[:200]
            logger.warning(f"[AI_TEST] API error: {error_text}")
            return TestAPIResponse(
                success=False,
                message=f"API 返回错误 ({response.status_code}): {error_text}",
                latency_ms=round(latency_ms, 2)
            )

        data = response.json()
        choices = data.get("choices", [])
        content = ""
        if choices:
            content = choices[0].get("message", {}).get("content", "")

        # ========== 测试 2: 游戏场景测试 ==========
        game_test_success = False
        game_test_message = ""
        game_test_speech = None
        game_test_latency = None

        try:
            # 模拟谁是卧底游戏场景
            game_system_prompt = """你是谁是卧底游戏中的平民玩家。
你的词是"苹果"。
现在是第1轮发言，你需要描述你的词，但不能直接说出来。

要求：
1. 发言要简洁（20-50字）
2. 不要直接说出词语
3. 描述要有一定的迷惑性，让卧底难以猜到
4. 直接输出发言内容，不要有任何前缀或解释"""

            game_request = {
                "model": model,
                "messages": [
                    {"role": "system", "content": game_system_prompt},
                    {"role": "user", "content": "请生成你的发言内容。"}
                ],
                "max_tokens": 150,
                "temperature": 0.7
            }

            game_start_time = time.time()
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
            ) as client:
                game_response = await client.post(api_url, json=game_request)

            game_test_latency = (time.time() - game_start_time) * 1000

            logger.info(f"[AI_TEST] Game test - Status: {game_response.status_code}, Latency: {game_test_latency:.2f}ms")

            if game_response.status_code == 200:
                game_data = game_response.json()
                game_choices = game_data.get("choices", [])

                if game_choices:
                    game_choice = game_choices[0]
                    game_message = game_choice.get("message", {})
                    game_content = game_message.get("content", "")
                    finish_reason = game_choice.get("finish_reason", "")
                    reasoning_content = game_message.get("reasoning_content", "")

                    logger.info(f"[AI_TEST] Game test - finish_reason: {finish_reason}")
                    logger.info(f"[AI_TEST] Game test - content length: {len(game_content) if game_content else 0}")
                    logger.info(f"[AI_TEST] Game test - reasoning_content: {'exists' if reasoning_content else 'none'}")

                    # 检查各种问题情况
                    if not game_content and reasoning_content:
                        game_test_success = False
                        game_test_message = "模型返回了 reasoning_content 但没有 content，此模型可能不适合游戏场景"
                        logger.warning(f"[AI_TEST] {game_test_message}")
                    elif finish_reason == "length" and (not game_content or len(game_content.strip()) < 10):
                        game_test_success = False
                        game_test_message = "响应被截断 (finish_reason: length)，内容不完整"
                        logger.warning(f"[AI_TEST] {game_test_message}")
                    elif not game_content or len(game_content.strip()) < 5:
                        game_test_success = False
                        game_test_message = "模型返回内容为空或过短"
                        logger.warning(f"[AI_TEST] {game_test_message}")
                    else:
                        # 清理 thinking tags
                        cleaned_content = re.sub(r'<think>.*?</think>', '', game_content, flags=re.DOTALL)
                        cleaned_content = re.sub(r'</?think>', '', cleaned_content)
                        cleaned_content = cleaned_content.strip()

                        if len(cleaned_content) < 5:
                            game_test_success = False
                            game_test_message = "清理思考标签后内容过短"
                        else:
                            game_test_success = True
                            game_test_message = "游戏场景测试通过"
                            game_test_speech = cleaned_content[:200]
                            logger.info(f"[AI_TEST] Game test passed! Speech: {game_test_speech[:50]}...")
                else:
                    game_test_success = False
                    game_test_message = "响应中没有 choices"
            else:
                game_test_success = False
                game_test_message = f"游戏场景请求失败 ({game_response.status_code})"

        except httpx.TimeoutException:
            game_test_success = False
            game_test_message = "游戏场景请求超时 (30秒)"
        except Exception as e:
            game_test_success = False
            game_test_message = f"游戏场景测试异常: {str(e)}"
            logger.error(f"[AI_TEST] Game test error: {e}")

        # 返回完整测试结果
        return TestAPIResponse(
            success=True,
            message="API 连接成功",
            latency_ms=round(latency_ms, 2),
            model_response=content[:100] if content else None,
            game_test_success=game_test_success,
            game_test_message=game_test_message,
            game_test_speech=game_test_speech,
            game_test_latency_ms=round(game_test_latency, 2) if game_test_latency else None
        )

    except httpx.TimeoutException:
        return TestAPIResponse(
            success=False,
            message="API 请求超时 (15秒)"
        )
    except httpx.ConnectError as e:
        return TestAPIResponse(
            success=False,
            message=f"无法连接到 API 服务器: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AI_TEST] Unexpected error: {str(e)}")
        return TestAPIResponse(
            success=False,
            message=f"测试失败: {str(e)}"
        )
