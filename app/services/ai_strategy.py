"""
AI Strategy service for role-based prompts and decision making
AI策略服务用于基于角色的提示词和决策制定
验证需求: 需求 4.2, 4.3, 4.4, 4.5
"""

import random
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

from app.models.ai_player import AIDifficulty, AIPersonality
from app.schemas.game import PlayerRole


class StrategyType(str, Enum):
    """策略类型"""
    SPEECH = "speech"
    VOTING = "voting"
    ANALYSIS = "analysis"


class AIStrategyService:
    """
    AI策略服务
    提供基于角色、难度和个性的策略提示词
    验证需求: 需求 4.2, 4.3, 4.4, 4.5
    """
    
    def __init__(self):
        self.strategy_templates = self._initialize_strategy_templates()
        self.personality_modifiers = self._initialize_personality_modifiers()
        self.difficulty_adjustments = self._initialize_difficulty_adjustments()
    
    def build_speech_prompt(
        self,
        role: PlayerRole,
        word: str,
        difficulty: AIDifficulty,
        personality: AIPersonality,
        game_context: Dict[str, Any]
    ) -> str:
        """
        构建发言提示词
        验证需求: 需求 4.2, 4.4, 4.5
        """
        # 基础提示词模板
        base_template = self.strategy_templates[StrategyType.SPEECH][role]
        
        # 应用难度调整
        difficulty_adjustments = self.difficulty_adjustments[difficulty]
        
        # 应用个性修饰
        personality_modifier = self.personality_modifiers[personality]
        
        # 构建完整提示词
        prompt = self._build_complete_prompt(
            base_template=base_template,
            word=word,
            difficulty_adjustments=difficulty_adjustments,
            personality_modifier=personality_modifier,
            game_context=game_context,
            strategy_type=StrategyType.SPEECH
        )
        
        return prompt
    
    def build_voting_prompt(
        self,
        role: PlayerRole,
        difficulty: AIDifficulty,
        personality: AIPersonality,
        game_context: Dict[str, Any],
        available_targets: List[str]
    ) -> str:
        """
        构建投票提示词
        验证需求: 需求 4.3, 4.4, 4.5
        """
        # 基础提示词模板
        base_template = self.strategy_templates[StrategyType.VOTING][role]
        
        # 应用难度调整
        difficulty_adjustments = self.difficulty_adjustments[difficulty]
        
        # 应用个性修饰
        personality_modifier = self.personality_modifiers[personality]
        
        # 构建完整提示词
        prompt = self._build_complete_prompt(
            base_template=base_template,
            word=None,
            difficulty_adjustments=difficulty_adjustments,
            personality_modifier=personality_modifier,
            game_context=game_context,
            strategy_type=StrategyType.VOTING,
            available_targets=available_targets
        )
        
        return prompt
    
    def get_strategy_advice(
        self,
        role: PlayerRole,
        difficulty: AIDifficulty,
        personality: AIPersonality,
        game_situation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        获取策略建议
        验证需求: 需求 4.2, 4.3, 4.4, 4.5
        """
        advice = {
            "speech_style": self._get_speech_style_advice(role, personality, difficulty),
            "voting_strategy": self._get_voting_strategy_advice(role, personality, difficulty),
            "risk_assessment": self._assess_risk_level(game_situation, role),
            "behavioral_hints": self._get_behavioral_hints(personality, difficulty)
        }
        
        return advice
    
    def _initialize_strategy_templates(self) -> Dict[StrategyType, Dict[PlayerRole, str]]:
        """初始化策略模板"""
        return {
            StrategyType.SPEECH: {
                PlayerRole.CIVILIAN: """你是谁是卧底游戏中的平民玩家。

游戏规则：
- 你获得的是普通词汇，大多数玩家都有相同的词汇
- 你需要描述你的词汇特征，但不能直接说出词汇本身
- 你的目标是找出并投票淘汰所有卧底玩家

你的词汇：{word}

平民策略要点：
1. 准确描述词汇特征，让其他平民认同
2. 仔细观察其他玩家的描述，寻找不一致之处
3. 与其他平民建立信任，形成联盟
4. 识别可能的卧底，引导讨论方向
5. 避免过于模糊的描述，以免被误认为卧底

当前游戏情况：
- 轮次：第{round_number}轮
- 存活玩家数：{alive_count}人
- 已发言玩家数：{speech_count}人

{context_info}

请生成15-30字的自然发言，要体现你对词汇的准确理解，同时观察其他玩家的反应。""",

                PlayerRole.UNDERCOVER: """你是谁是卧底游戏中的卧底玩家。

游戏规则：
- 你获得的词汇与大多数玩家不同，但通常有相似性
- 你需要伪装成平民，避免被发现
- 你的目标是生存到最后，或让卧底数量达到平民数量

你的词汇：{word}

卧底策略要点：
1. 仔细听取其他玩家的描述，推测平民词汇
2. 模仿平民的描述风格和用词习惯
3. 避免过于具体或过于模糊的描述
4. 适当引导话题，但不要过于明显
5. 在投票时误导平民，保护其他卧底

当前游戏情况：
- 轮次：第{round_number}轮
- 存活玩家数：{alive_count}人
- 已发言玩家数：{speech_count}人

{context_info}

请生成15-30字的自然发言，要巧妙地伪装成平民，避免暴露你的真实词汇。"""
            },
            
            StrategyType.VOTING: {
                PlayerRole.CIVILIAN: """你是谁是卧底游戏中的平民玩家，现在需要投票淘汰一个玩家。

你的目标：找出并淘汰卧底玩家

投票策略（平民）：
1. 分析发言内容的一致性
   - 寻找与大多数人描述不符的玩家
   - 注意过于模糊或回避的发言
   - 识别可能在模仿他人的描述

2. 观察行为模式
   - 注意投票时的犹豫或异常
   - 观察是否有人试图误导讨论
   - 识别可能的联盟关系

3. 逻辑推理
   - 基于已知信息推断卧底身份
   - 考虑玩家的历史表现
   - 评估风险和收益

当前轮次：第{round_number}轮
可投票玩家：{available_targets}

{speech_analysis}

请仔细分析所有发言，选择最可疑的玩家进行投票。只返回玩家ID。""",

                PlayerRole.UNDERCOVER: """你是谁是卧底游戏中的卧底玩家，现在需要投票淘汰一个玩家。

你的目标：保护自己和其他卧底，误导平民

投票策略（卧底）：
1. 保护卧底同伴
   - 避免投票给其他卧底
   - 在不暴露的前提下为卧底辩护
   - 转移对卧底的怀疑

2. 误导平民
   - 投票给最有威胁的平民
   - 制造平民之间的怀疑
   - 跟随大多数人的投票以避免突出

3. 风险控制
   - 评估自己的暴露风险
   - 在必要时牺牲其他卧底保护自己
   - 保持低调，避免成为焦点

当前轮次：第{round_number}轮
可投票玩家：{available_targets}

{speech_analysis}

请巧妙地选择投票目标，既要保护卧底利益，又要避免暴露身份。只返回玩家ID。"""
            }
        }
    
    def _initialize_personality_modifiers(self) -> Dict[AIPersonality, Dict[str, Any]]:
        """初始化个性修饰符"""
        return {
            AIPersonality.CAUTIOUS: {
                "speech_style": "谨慎保守，措辞小心",
                "decision_pattern": "深思熟虑，避免冒险",
                "interaction_style": "观察多于表达，跟随多数",
                "risk_tolerance": 0.3,
                "speech_modifiers": [
                    "我觉得可能是...",
                    "不太确定，但是...",
                    "从我的角度来看...",
                    "也许我们应该..."
                ],
                "voting_modifiers": [
                    "基于目前的信息...",
                    "虽然不太确定，但...",
                    "综合考虑后..."
                ]
            },
            
            AIPersonality.AGGRESSIVE: {
                "speech_style": "直接果断，表达明确",
                "decision_pattern": "快速决策，敢于冒险",
                "interaction_style": "主动引导，影响他人",
                "risk_tolerance": 0.8,
                "speech_modifiers": [
                    "我确信这是...",
                    "很明显...",
                    "毫无疑问...",
                    "我们必须..."
                ],
                "voting_modifiers": [
                    "很明显应该是...",
                    "毫无疑问是...",
                    "必须淘汰..."
                ]
            },
            
            AIPersonality.NORMAL: {
                "speech_style": "平衡表达，适度参与",
                "decision_pattern": "理性分析，平衡考虑",
                "interaction_style": "正常互动，适度配合",
                "risk_tolerance": 0.5,
                "speech_modifiers": [
                    "我认为...",
                    "这让我想到...",
                    "根据我的理解...",
                    "我的看法是..."
                ],
                "voting_modifiers": [
                    "我认为应该是...",
                    "根据分析...",
                    "我的选择是..."
                ]
            },
            
            AIPersonality.RANDOM: {
                "speech_style": "变化多样，不可预测",
                "decision_pattern": "随机性强，难以预测",
                "interaction_style": "时而主动时而被动",
                "risk_tolerance": 0.6,
                "speech_modifiers": [
                    "突然想到...",
                    "有个奇怪的想法...",
                    "换个角度看...",
                    "或许..."
                ],
                "voting_modifiers": [
                    "直觉告诉我...",
                    "感觉应该是...",
                    "随便选个..."
                ]
            }
        }
    
    def _initialize_difficulty_adjustments(self) -> Dict[AIDifficulty, Dict[str, Any]]:
        """初始化难度调整"""
        return {
            AIDifficulty.BEGINNER: {
                "analysis_depth": 1,
                "mistake_probability": 0.2,
                "strategy_complexity": "简单",
                "speech_sophistication": "基础",
                "voting_accuracy": 0.6,
                "behavioral_notes": [
                    "可能会犯一些明显的错误",
                    "分析不够深入",
                    "容易被误导",
                    "发言相对简单"
                ]
            },
            
            AIDifficulty.NORMAL: {
                "analysis_depth": 2,
                "mistake_probability": 0.1,
                "strategy_complexity": "中等",
                "speech_sophistication": "标准",
                "voting_accuracy": 0.75,
                "behavioral_notes": [
                    "有一定的分析能力",
                    "偶尔会犯错误",
                    "能够进行基本推理",
                    "发言较为合理"
                ]
            },
            
            AIDifficulty.EXPERT: {
                "analysis_depth": 3,
                "mistake_probability": 0.05,
                "strategy_complexity": "复杂",
                "speech_sophistication": "高级",
                "voting_accuracy": 0.9,
                "behavioral_notes": [
                    "分析能力强",
                    "很少犯错误",
                    "能够进行复杂推理",
                    "发言精准有效"
                ]
            }
        }
    
    def _build_complete_prompt(
        self,
        base_template: str,
        word: Optional[str],
        difficulty_adjustments: Dict[str, Any],
        personality_modifier: Dict[str, Any],
        game_context: Dict[str, Any],
        strategy_type: StrategyType,
        available_targets: Optional[List[str]] = None
    ) -> str:
        """构建完整的提示词"""
        
        # 准备模板变量
        template_vars = {
            "word": word or "",
            "round_number": game_context.get("round_number", 1),
            "alive_count": len(game_context.get("alive_players", [])),
            "speech_count": len(game_context.get("speeches", [])),
            "context_info": self._build_context_info(game_context),
            "available_targets": ", ".join(available_targets) if available_targets else "",
            "speech_analysis": self._build_speech_analysis(game_context)
        }
        
        # 填充基础模板
        prompt = base_template.format(**template_vars)
        
        # 添加个性修饰
        prompt += f"\n\n个性特征：{personality_modifier['speech_style']}"
        prompt += f"\n决策模式：{personality_modifier['decision_pattern']}"
        
        # 添加难度调整
        if difficulty_adjustments["behavioral_notes"]:
            prompt += f"\n\n行为特点：\n"
            for note in difficulty_adjustments["behavioral_notes"]:
                prompt += f"- {note}\n"
        
        # 添加策略特定的修饰
        if strategy_type == StrategyType.SPEECH:
            # 添加禁词提示 - 非常重要，避免 AI 直接暴露身份
            prompt += "\n\n【重要规则】发言中绝对禁止出现以下词语：'卧底'、'平民'、'词汇'、'词语'、'我的词'、'我的角色'。发言必须是描述性的，不能直接说明自己的身份或词语。"

            modifiers = personality_modifier.get("speech_modifiers", [])
            if modifiers:
                selected_modifier = random.choice(modifiers)
                prompt += f"\n\n发言风格提示：可以使用类似'{selected_modifier}'的表达方式。"
        
        elif strategy_type == StrategyType.VOTING:
            modifiers = personality_modifier.get("voting_modifiers", [])
            if modifiers:
                selected_modifier = random.choice(modifiers)
                prompt += f"\n\n投票风格提示：可以使用类似'{selected_modifier}'的表达方式。"
        
        return prompt
    
    def _build_context_info(self, game_context: Dict[str, Any]) -> str:
        """构建上下文信息"""
        context_parts = []
        
        # 添加历史发言信息
        speeches = game_context.get("speeches", [])
        if speeches:
            context_parts.append("最近的发言：")
            for speech in speeches[-3:]:  # 最近3条发言
                player_name = speech.get("player_name", "未知玩家")
                content = speech.get("content", "")
                context_parts.append(f"- {player_name}: {content}")
        
        # 添加游戏阶段信息
        phase = game_context.get("current_phase", "unknown")
        context_parts.append(f"当前阶段：{phase}")
        
        # 添加特殊情况
        if game_context.get("is_final_round"):
            context_parts.append("⚠️ 这可能是最后一轮，请谨慎决策！")
        
        return "\n".join(context_parts)
    
    def _build_speech_analysis(self, game_context: Dict[str, Any]) -> str:
        """构建发言分析"""
        speeches = game_context.get("speeches", [])
        if not speeches:
            return "本轮暂无发言记录。"
        
        analysis_parts = ["本轮发言分析："]
        
        for speech in speeches:
            player_id = speech.get("player_id", "unknown")
            player_name = speech.get("player_name", "未知玩家")
            content = speech.get("content", "")
            
            # 简单的发言分析
            analysis = self._analyze_speech_content(content)
            analysis_parts.append(f"- {player_name}({player_id}): {content}")
            analysis_parts.append(f"  分析：{analysis}")
        
        return "\n".join(analysis_parts)
    
    def _analyze_speech_content(self, content: str) -> str:
        """分析发言内容"""
        if len(content) < 10:
            return "发言较短，信息量少"
        elif len(content) > 50:
            return "发言详细，信息丰富"
        
        # 检查模糊词汇
        vague_words = ["这个", "那个", "东西", "物品", "某种"]
        vague_count = sum(1 for word in vague_words if word in content)
        
        if vague_count > 2:
            return "发言较为模糊，可能在回避"
        elif vague_count == 0:
            return "发言具体明确"
        else:
            return "发言正常"
    
    def _get_speech_style_advice(
        self, 
        role: PlayerRole, 
        personality: AIPersonality, 
        difficulty: AIDifficulty
    ) -> Dict[str, Any]:
        """获取发言风格建议"""
        base_advice = {
            PlayerRole.CIVILIAN: {
                "tone": "自信明确",
                "content_focus": "准确描述词汇特征",
                "interaction": "积极寻找卧底"
            },
            PlayerRole.UNDERCOVER: {
                "tone": "谨慎模仿",
                "content_focus": "模糊但不过分",
                "interaction": "低调融入"
            }
        }
        
        advice = base_advice[role].copy()
        
        # 应用个性调整
        personality_mod = self.personality_modifiers[personality]
        advice["personality_style"] = personality_mod["speech_style"]
        advice["risk_level"] = personality_mod["risk_tolerance"]
        
        # 应用难度调整
        difficulty_mod = self.difficulty_adjustments[difficulty]
        advice["sophistication"] = difficulty_mod["speech_sophistication"]
        advice["mistake_rate"] = difficulty_mod["mistake_probability"]
        
        return advice
    
    def _get_voting_strategy_advice(
        self, 
        role: PlayerRole, 
        personality: AIPersonality, 
        difficulty: AIDifficulty
    ) -> Dict[str, Any]:
        """获取投票策略建议"""
        base_strategy = {
            PlayerRole.CIVILIAN: {
                "primary_goal": "淘汰卧底",
                "analysis_focus": "寻找不一致的发言",
                "decision_basis": "逻辑推理和观察"
            },
            PlayerRole.UNDERCOVER: {
                "primary_goal": "保护卧底，误导平民",
                "analysis_focus": "识别威胁，保护同伴",
                "decision_basis": "风险评估和伪装"
            }
        }
        
        strategy = base_strategy[role].copy()
        
        # 应用个性和难度调整
        personality_mod = self.personality_modifiers[personality]
        difficulty_mod = self.difficulty_adjustments[difficulty]
        
        strategy["decision_style"] = personality_mod["decision_pattern"]
        strategy["accuracy"] = difficulty_mod["voting_accuracy"]
        strategy["complexity"] = difficulty_mod["strategy_complexity"]
        
        return strategy
    
    def _assess_risk_level(self, game_situation: Dict[str, Any], role: PlayerRole) -> str:
        """评估风险等级"""
        alive_count = len(game_situation.get("alive_players", []))
        round_number = game_situation.get("round_number", 1)
        
        if role == PlayerRole.UNDERCOVER:
            # 卧底的风险评估
            if alive_count <= 4:
                return "高风险：存活人数少，容易被发现"
            elif round_number >= 3:
                return "中等风险：游戏进入中后期"
            else:
                return "低风险：游戏初期，相对安全"
        else:
            # 平民的风险评估
            if alive_count <= 3:
                return "高风险：人数过少，可能已被卧底控制"
            elif round_number >= 4:
                return "中等风险：时间紧迫，需要尽快找出卧底"
            else:
                return "低风险：有充足时间分析"
    
    def _get_behavioral_hints(
        self, 
        personality: AIPersonality, 
        difficulty: AIDifficulty
    ) -> List[str]:
        """获取行为提示"""
        personality_hints = {
            AIPersonality.CAUTIOUS: [
                "多观察，少表态",
                "跟随大多数人的判断",
                "避免成为焦点"
            ],
            AIPersonality.AGGRESSIVE: [
                "主动引导讨论",
                "明确表达观点",
                "敢于质疑他人"
            ],
            AIPersonality.NORMAL: [
                "保持理性分析",
                "适度参与讨论",
                "平衡各方观点"
            ],
            AIPersonality.RANDOM: [
                "保持不可预测性",
                "偶尔改变策略",
                "制造意外"
            ]
        }
        
        difficulty_hints = {
            AIDifficulty.BEGINNER: [
                "可能会犯一些基础错误",
                "分析相对简单"
            ],
            AIDifficulty.NORMAL: [
                "保持中等水平的表现",
                "偶尔展现洞察力"
            ],
            AIDifficulty.EXPERT: [
                "展现高级分析能力",
                "很少犯错误"
            ]
        }
        
        hints = personality_hints.get(personality, [])
        hints.extend(difficulty_hints.get(difficulty, []))
        
        return hints


# 全局AI策略服务实例
ai_strategy_service = AIStrategyService()