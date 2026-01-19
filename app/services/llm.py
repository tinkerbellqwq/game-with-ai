"""
LLM service for AI opponent integration
LLM服务用于AI对手集成 - 支持每个 AI 玩家独立的 API 配置
使用 httpx 直接发送请求，绕过 Cloudflare 对 OpenAI 库的拦截
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import httpx

from app.core.config import settings
from app.services.ai_strategy import ai_strategy_service
from app.models.ai_player import AIDifficulty, AIPersonality
from app.schemas.game import PlayerRole

logger = logging.getLogger(__name__)


class LLMService:
    """
    LLM service for AI opponent functionality
    每个 AI 玩家可以有独立的 API 配置
    使用 httpx 直接发送请求，避免 OpenAI 库被 Cloudflare 阻止
    支持兜底模型：当主模型失败时自动切换
    验证需求: 需求 4.1, 8.4
    """

    # 兜底模型列表（按优先级排序，响应速度快且稳定的优先）
    FALLBACK_MODELS = [
        "moonshotai/kimi-k2-instruct",   # Kimi - 最快最稳定
        "deepseek-ai/deepseek-r1-distill-llama-8b",  # 快速稳定
        "google/gemini-2.0-flash-lite-001",          # Google 轻量级
    ]

    def __init__(self):
        self.is_available = True  # 现在总是可用，因为配置在 AI 玩家级别
        self.last_error: Optional[str] = None
        self.request_count = 0
        self.cost_tracking: Dict[str, Any] = {
            "daily_requests": 0,
            "last_reset": datetime.now().date(),
            "total_tokens": 0
        }

        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds
        self.timeout = 30.0  # seconds

        # 记录模型失败次数，用于智能选择兜底模型
        self.model_failures: Dict[str, int] = {}

        logger.info("[LLM_INIT] LLM Service initialized (httpx mode, with fallback support)")

    def _reset_daily_tracking(self) -> None:
        """Reset daily request tracking if needed"""
        current_date = datetime.now().date()
        if current_date > self.cost_tracking["last_reset"]:
            self.cost_tracking["daily_requests"] = 0
            self.cost_tracking["last_reset"] = current_date

    def _check_rate_limits(self) -> bool:
        """Check if we're within rate limits"""
        self._reset_daily_tracking()

        # Daily request limit (configurable)
        daily_limit = getattr(settings, 'OPENAI_DAILY_REQUEST_LIMIT', 1000)
        if self.cost_tracking["daily_requests"] >= daily_limit:
            logger.warning("Daily OpenAI request limit reached")
            return False

        return True

    async def _make_request_with_retry(
        self,
        api_base_url: str,
        api_key: str,
        messages: List[Dict[str, str]],
        model: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        使用 httpx 直接发送请求，带重试机制
        避免使用 OpenAI 库，绕过 Cloudflare 拦截
        """
        if not self._check_rate_limits():
            return None

        last_exception = None

        # 构建请求 URL
        api_url = api_base_url.rstrip('/') + '/chat/completions'

        # 构建请求体
        request_body = {
            "model": model,
            "messages": messages,
            "max_tokens": settings.OPENAI_MAX_TOKENS,
            "temperature": settings.OPENAI_TEMPERATURE,
            **kwargs
        }

        # 详细日志：请求参数
        logger.info(f"[LLM_REQUEST] === 发起 LLM 请求 ===")
        logger.info(f"[LLM_REQUEST] API URL: {api_url}")
        logger.info(f"[LLM_REQUEST] Model: {model}")
        logger.info(f"[LLM_REQUEST] Max tokens: {settings.OPENAI_MAX_TOKENS}")
        logger.info(f"[LLM_REQUEST] Temperature: {settings.OPENAI_TEMPERATURE}")
        logger.info(f"[LLM_REQUEST] Messages count: {len(messages)}")
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            logger.info(f"[LLM_REQUEST] Message[{i}] role={msg.get('role')}, content_length={len(content)}")
            if len(content) < 500:
                logger.info(f"[LLM_REQUEST] Message[{i}] content: {content}")
            else:
                logger.info(f"[LLM_REQUEST] Message[{i}] content (first 500): {content[:500]}...")

        for attempt in range(self.max_retries):
            try:
                # 创建 httpx 客户端配置（类似测试端点的方式）
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    http2=False,
                    follow_redirects=True
                ) as client:
                    response = await client.post(api_url, json=request_body)

                # 详细日志：响应信息
                logger.info(f"[LLM_RESPONSE] === LLM 响应 ===")
                logger.info(f"[LLM_RESPONSE] Status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"[LLM_RESPONSE] Response ID: {data.get('id', 'N/A')}")
                    logger.info(f"[LLM_RESPONSE] Model: {data.get('model', 'N/A')}")

                    usage = data.get('usage', {})
                    if usage:
                        logger.info(f"[LLM_RESPONSE] Usage: prompt={usage.get('prompt_tokens')}, completion={usage.get('completion_tokens')}, total={usage.get('total_tokens')}")

                    choices = data.get('choices', [])
                    if choices:
                        for i, choice in enumerate(choices):
                            logger.info(f"[LLM_RESPONSE] Choice[{i}] finish_reason: {choice.get('finish_reason')}")
                            message = choice.get('message', {})
                            if message:
                                logger.info(f"[LLM_RESPONSE] Choice[{i}] message.role: {message.get('role')}")
                                content = message.get('content', '')
                                logger.info(f"[LLM_RESPONSE] Choice[{i}] message.content: {content[:200] if content else 'None'}...")
                                # 检查是否有 thinking/reasoning 相关字段
                                if message.get('reasoning_content'):
                                    logger.info(f"[LLM_RESPONSE] Choice[{i}] reasoning_content: {message.get('reasoning_content', '')[:200]}...")

                    # Update tracking
                    self.cost_tracking["daily_requests"] += 1
                    if usage:
                        self.cost_tracking["total_tokens"] += usage.get('total_tokens', 0)

                    self.request_count += 1
                    logger.info(f"[LLM_RESPONSE] Request successful (attempt {attempt + 1})")
                    return data
                else:
                    # 非 200 响应
                    error_text = response.text[:500] if response.text else "No response body"
                    logger.warning(f"[LLM_RESPONSE] HTTP {response.status_code}: {error_text}")

                    # 检测 Cloudflare 阻止
                    if "cloudflare" in response.text.lower() or "<!DOCTYPE" in response.text:
                        logger.error("[LLM_RESPONSE] Request blocked by Cloudflare")

                    last_exception = Exception(f"HTTP {response.status_code}: {error_text[:200]}")

            except Exception as e:
                last_exception = e
                logger.warning(f"[LLM_REQUEST] Request failed (attempt {attempt + 1}): {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff

        # All retries failed
        self.last_error = str(last_exception) if last_exception else "Unknown error"
        logger.error(f"[LLM_REQUEST] Request failed after {self.max_retries} attempts: {self.last_error}")
        return None

    async def _make_request_with_fallback(
        self,
        api_base_url: str,
        api_key: str,
        messages: List[Dict[str, str]],
        model: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        带兜底机制的请求方法
        当主模型失败时，自动尝试兜底模型
        """
        # 首先尝试主模型
        result = await self._make_request_with_retry(
            api_base_url, api_key, messages, model, **kwargs
        )

        if result is not None:
            # 主模型成功，重置失败计数
            self.model_failures[model] = 0
            return result

        # 主模型失败，记录失败次数
        self.model_failures[model] = self.model_failures.get(model, 0) + 1
        logger.warning(f"[LLM_FALLBACK] Primary model {model} failed (failures: {self.model_failures[model]}), trying fallback models...")

        # 尝试兜底模型
        for fallback_model in self.FALLBACK_MODELS:
            # 跳过失败次数过多的模型
            if self.model_failures.get(fallback_model, 0) >= 5:
                logger.debug(f"[LLM_FALLBACK] Skipping {fallback_model} (too many failures)")
                continue

            logger.info(f"[LLM_FALLBACK] Trying fallback model: {fallback_model}")

            result = await self._make_request_with_retry(
                api_base_url, api_key, messages, fallback_model, **kwargs
            )

            if result is not None:
                # 兜底模型成功
                self.model_failures[fallback_model] = 0
                logger.info(f"[LLM_FALLBACK] Fallback model {fallback_model} succeeded!")
                return result
            else:
                # 记录兜底模型失败
                self.model_failures[fallback_model] = self.model_failures.get(fallback_model, 0) + 1

        # 所有模型都失败了
        logger.error("[LLM_FALLBACK] All models failed (primary + all fallbacks)")
        return None

    async def generate_ai_speech(
        self,
        role: str,
        word: str,
        context: Dict[str, Any],
        personality: str = "normal",
        difficulty: str = "normal",
        model: Optional[str] = None,
        api_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        custom_system_prompt: Optional[str] = None,
        custom_speech_prompt: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate AI speech based on role and context
        验证需求: 需求 4.2, 4.4, 4.5
        """
        logger.info(f"[LLM] generate_ai_speech called: role={role}, word={word[:10] if word else 'N/A'}..., model={model}")
        logger.info(f"[LLM] API config: base_url={api_base_url or 'not set'}, key={'SET' if api_key else 'NOT SET'}")

        if not api_key:
            logger.error("[LLM] No API key configured for this AI player")
            self.last_error = "AI 玩家未配置 API Key"
            return None

        if not model:
            logger.error("[LLM] No model configured for this AI player")
            self.last_error = "AI 玩家未配置模型"
            return None

        if not api_base_url:
            logger.error("[LLM] No API base URL configured for this AI player")
            self.last_error = "AI 玩家未配置 API URL"
            return None

        try:
            # Convert string parameters to enums
            role_enum = PlayerRole(role)
            personality_enum = AIPersonality(personality)
            difficulty_enum = AIDifficulty(difficulty)

            # 如果有自定义提示词，使用自定义提示词；否则使用策略服务生成
            if custom_system_prompt:
                # 替换模板变量
                system_prompt = custom_system_prompt.replace("{word}", word)
                system_prompt = system_prompt.replace("{role}", role)
                system_prompt = system_prompt.replace("{round_number}", str(context.get("round_number", 1)))
                logger.info("[LLM] Using custom system prompt")
            else:
                # Build enhanced context-aware prompt using AI strategy service
                system_prompt = ai_strategy_service.build_speech_prompt(
                    role=role_enum,
                    word=word,
                    difficulty=difficulty_enum,
                    personality=personality_enum,
                    game_context=context
                )

            # 用户提示词
            user_prompt = custom_speech_prompt or "请生成你的发言内容，要简洁自然，符合角色特征。"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = await self._make_request_with_fallback(
                api_base_url=api_base_url,
                api_key=api_key,
                messages=messages,
                model=model
            )

            # 尝试从响应中提取有效内容
            speech = self._extract_speech_content(response)

            # 如果主模型返回无效内容，尝试兜底模型
            if speech is None and response is not None:
                logger.warning(f"[LLM] Primary model {model} returned unusable content, trying fallback models for speech...")
                for fallback_model in self.FALLBACK_MODELS:
                    if self.model_failures.get(fallback_model, 0) >= 5:
                        continue

                    logger.info(f"[LLM] Retrying speech with fallback model: {fallback_model}")
                    fallback_response = await self._make_request_with_retry(
                        api_base_url=api_base_url,
                        api_key=api_key,
                        messages=messages,
                        model=fallback_model
                    )

                    speech = self._extract_speech_content(fallback_response)
                    if speech:
                        logger.info(f"[LLM] Fallback model {fallback_model} succeeded for speech!")
                        logger.info(f"Generated AI speech for {role}: {speech[:100]}...")
                        return speech
                    else:
                        self.model_failures[fallback_model] = self.model_failures.get(fallback_model, 0) + 1

                logger.error("[LLM] All fallback models failed for speech")
                return None

            if speech:
                logger.info(f"Generated AI speech for {role}: {speech[:100]}...")
            return speech

        except Exception as e:
            logger.error(f"Failed to generate AI speech: {e}")
            self.last_error = str(e)
            return None

    def _extract_speech_content(self, response: Optional[Dict[str, Any]]) -> Optional[str]:
        """从 LLM 响应中提取有效的发言内容"""
        if not response or not response.get('choices'):
            return None

        choice = response['choices'][0]
        message = choice.get('message', {})
        content = message.get('content', '')

        # 检查是否被截断 (finish_reason: length)
        finish_reason = choice.get('finish_reason', '')
        if finish_reason == 'length':
            logger.warning(f"[LLM] Response was truncated (finish_reason: length), content may be incomplete")

        # 如果 content 为空但有 reasoning_content，返回 None
        if not content and message.get('reasoning_content'):
            logger.warning(f"[LLM] content is empty but reasoning_content exists, this model may not be suitable")
            return None

        if content:
            # Clean thinking tags from AI response (DeepSeek, etc.)
            import re
            # Remove <think>...</think> blocks
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
            # Remove any remaining think tags
            content = re.sub(r'</?think>', '', content)

            # Clean and validate response
            speech = content.strip()

            # 如果内容太短（可能是被截断的不完整内容），返回 None
            if len(speech) < 5:
                logger.warning(f"[LLM] Speech too short ({len(speech)} chars), may be truncated")
                return None

            return speech

        return None

    async def generate_ai_vote(
        self,
        role: str,
        game_context: Dict[str, Any],
        available_targets: List[str],
        personality: str = "normal",
        difficulty: str = "normal",
        model: Optional[str] = None,
        api_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        custom_vote_prompt: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate AI vote decision based on game context
        验证需求: 需求 4.3, 4.4, 4.5
        """
        try:
            if not available_targets:
                return None

            if not api_key or not model or not api_base_url:
                logger.warning("[LLM] No API config for AI vote, using random")
                import random
                return random.choice(available_targets)

            # Convert string parameters to enums
            role_enum = PlayerRole(role)
            personality_enum = AIPersonality(personality)
            difficulty_enum = AIDifficulty(difficulty)

            # Build enhanced voting prompt using AI strategy service
            system_prompt = ai_strategy_service.build_voting_prompt(
                role=role_enum,
                difficulty=difficulty_enum,
                personality=personality_enum,
                game_context=game_context,
                available_targets=available_targets
            )

            # 用户提示词
            user_prompt = custom_vote_prompt or "请选择你要投票的玩家ID，只返回ID，不要其他内容。"
            # 替换模板变量
            user_prompt = user_prompt.replace("{available_targets}", ", ".join(available_targets))

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = await self._make_request_with_fallback(
                api_base_url=api_base_url,
                api_key=api_key,
                messages=messages,
                model=model
            )

            if response and response.get('choices'):
                choice = response['choices'][0]
                message = choice.get('message', {})
                content = message.get('content', '')

                # 检查是否被截断
                finish_reason = choice.get('finish_reason', '')
                if finish_reason == 'length':
                    logger.warning(f"[LLM] Vote response was truncated")

                # 如果 content 为空但有 reasoning_content，使用随机投票
                if not content and message.get('reasoning_content'):
                    logger.warning(f"[LLM] Vote content is empty, using random fallback")
                    import random
                    return random.choice(available_targets)

                if content:
                    vote_target = content.strip()

                    # Validate vote target
                    if vote_target in available_targets:
                        logger.info(f"AI {role} voted for: {vote_target}")
                        return vote_target
                    else:
                        # Fallback to random choice if invalid
                        import random
                        fallback_target = random.choice(available_targets)
                        logger.warning(f"AI vote invalid '{vote_target}', using fallback: {fallback_target}")
                        return fallback_target

            # Fallback to random choice
            import random
            return random.choice(available_targets)

        except Exception as e:
            logger.error(f"Failed to generate AI vote: {e}")
            # Fallback to random choice
            import random
            return random.choice(available_targets) if available_targets else None

    async def health_check(self) -> Dict[str, Any]:
        """Check LLM service health status"""
        return {
            "is_available": self.is_available,
            "last_error": self.last_error,
            "request_count": self.request_count,
            "daily_requests": self.cost_tracking["daily_requests"],
            "total_tokens": self.cost_tracking["total_tokens"],
            "mode": "httpx_direct"  # 标识使用 httpx 直接请求模式
        }

    async def graceful_degradation(self) -> Dict[str, str]:
        """Provide fallback responses when LLM is unavailable"""
        fallback_speeches = [
            "这个词让我想到了很多东西。",
            "我觉得这个概念很有趣。",
            "从某种角度来看，这很常见。",
            "这让我联想到日常生活。",
            "我对这个有一些了解。"
        ]

        import random
        return {
            "speech": random.choice(fallback_speeches),
            "vote": "random"  # Will be handled by caller
        }


# Global LLM service instance
llm_service = LLMService()
