"""
Word Pair Pydantic schemas
词汇对数据验证和序列化模型
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime


class WordPairBase(BaseModel):
    """词汇对基础模型"""
    civilian_word: str = Field(..., min_length=1, max_length=50, description="平民词汇")
    undercover_word: str = Field(..., min_length=1, max_length=50, description="卧底词汇")
    category: str = Field(..., min_length=1, max_length=50, description="词汇类别")
    difficulty: int = Field(..., ge=1, le=5, description="难度等级(1-5)")
    
    @validator('civilian_word', 'undercover_word')
    def validate_words(cls, v):
        """验证词汇格式"""
        v = v.strip()
        if not v:
            raise ValueError('词汇不能为空')
        
        # 检查是否包含特殊字符
        import re
        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9\s]+$', v):
            raise ValueError('词汇只能包含中文、英文、数字和空格')
        
        return v
    
    @validator('category')
    def validate_category(cls, v):
        """验证类别格式"""
        v = v.strip()
        if not v:
            raise ValueError('类别不能为空')
        return v


class WordPairCreate(WordPairBase):
    """创建词汇对请求"""
    
    @validator('civilian_word', 'undercover_word')
    def validate_word_similarity(cls, v, values):
        """验证词汇相似性"""
        if 'civilian_word' in values and 'undercover_word' in values:
            civilian = values.get('civilian_word', '')
            undercover = values.get('undercover_word', v if 'undercover_word' not in values else values['undercover_word'])
            
            # 词汇不能完全相同
            if civilian == undercover:
                raise ValueError('平民词汇和卧底词汇不能相同')
            
            # 词汇不能包含对方
            if civilian in undercover or undercover in civilian:
                raise ValueError('词汇之间不能存在包含关系')
        
        return v


class WordPairUpdate(BaseModel):
    """更新词汇对请求"""
    civilian_word: Optional[str] = Field(None, min_length=1, max_length=50)
    undercover_word: Optional[str] = Field(None, min_length=1, max_length=50)
    category: Optional[str] = Field(None, min_length=1, max_length=50)
    difficulty: Optional[int] = Field(None, ge=1, le=5)


class WordPairResponse(WordPairBase):
    """词汇对响应"""
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class WordPairListResponse(BaseModel):
    """词汇对列表响应"""
    word_pairs: List[WordPairResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class WordPairFilters(BaseModel):
    """词汇对过滤条件"""
    category: Optional[str] = None
    difficulty: Optional[int] = Field(None, ge=1, le=5)
    search: Optional[str] = Field(None, max_length=100, description="搜索关键词")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


class WordPairForGame(BaseModel):
    """游戏中使用的词汇对"""
    id: str
    category: str
    difficulty: int
    
    def get_word_for_role(self, role: str) -> str:
        """根据角色获取对应词汇"""
        # 注意：在实际游戏中，这个方法应该在服务端调用
        # 客户端不应该知道完整的词汇对信息
        raise NotImplementedError("此方法应在服务端实现")


class CategoryStats(BaseModel):
    """类别统计"""
    category: str
    count: int
    difficulties: List[int]


class WordPairStats(BaseModel):
    """词汇对统计信息"""
    total_pairs: int
    categories: List[CategoryStats]
    difficulty_distribution: dict  # {1: 10, 2: 15, ...}
    most_used_pairs: List[WordPairResponse]
    recently_added: List[WordPairResponse]


class WordPairBatch(BaseModel):
    """批量词汇对操作"""
    word_pairs: List[WordPairCreate] = Field(..., min_items=1, max_items=100)
    
    @validator('word_pairs')
    def validate_batch_uniqueness(cls, v):
        """验证批量词汇对的唯一性"""
        seen_pairs = set()
        for pair in v:
            pair_key = (pair.civilian_word, pair.undercover_word, pair.category)
            if pair_key in seen_pairs:
                raise ValueError(f'批量数据中存在重复的词汇对: {pair.civilian_word} vs {pair.undercover_word}')
            seen_pairs.add(pair_key)
        return v


class WordPairImport(BaseModel):
    """词汇对导入"""
    source: str = Field(..., description="导入来源")
    data: List[dict] = Field(..., min_items=1, description="导入数据")
    overwrite_existing: bool = Field(default=False, description="是否覆盖已存在的词汇对")


class WordPairExport(BaseModel):
    """词汇对导出"""
    format: str = Field(default="json", description="导出格式: json, csv, xlsx")
    filters: Optional[WordPairFilters] = None
    include_stats: bool = Field(default=False, description="是否包含统计信息")