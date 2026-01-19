"""
User Pydantic schemas
用户数据验证和序列化模型
"""

from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
import re


class UserBase(BaseModel):
    """Base user schema with common fields"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱地址")
    
    @validator('username')
    def validate_username(cls, v):
        """验证用户名格式"""
        if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fa5]+$', v):
            raise ValueError('用户名只能包含字母、数字、下划线和中文字符')
        return v
    
    @validator('email')
    def validate_email(cls, v):
        """验证邮箱格式"""
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError('邮箱格式不正确')
        return v


class UserCreate(UserBase):
    """User creation schema"""
    password: str = Field(..., min_length=8, max_length=128, description="密码")
    
    @validator('password')
    def validate_password(cls, v):
        """验证密码强度"""
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('密码必须包含至少一个字母')
        if not re.search(r'\d', v):
            raise ValueError('密码必须包含至少一个数字')
        return v


class UserUpdate(BaseModel):
    """User update schema"""
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    
    @validator('username')
    def validate_username(cls, v):
        if v is not None and not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fa5]+$', v):
            raise ValueError('用户名只能包含字母、数字、下划线和中文字符')
        return v
    
    @validator('email')
    def validate_email(cls, v):
        if v is not None:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, v):
                raise ValueError('邮箱格式不正确')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        if v is not None:
            if not re.search(r'[A-Za-z]', v):
                raise ValueError('密码必须包含至少一个字母')
            if not re.search(r'\d', v):
                raise ValueError('密码必须包含至少一个数字')
        return v


class UserResponse(UserBase):
    """User response schema"""
    id: str
    score: int = Field(default=0, description="积分")
    games_played: int = Field(default=0, description="游戏总数")
    games_won: int = Field(default=0, description="获胜次数")
    is_active: bool = Field(default=True, description="账号状态")
    created_at: datetime
    last_login: Optional[datetime] = None
    
    @property
    def win_rate(self) -> float:
        """计算胜率"""
        if self.games_played == 0:
            return 0.0
        return round((self.games_won / self.games_played) * 100, 2)
    
    class Config:
        from_attributes = True


class UserStats(BaseModel):
    """User statistics schema"""
    id: str
    username: str
    score: int
    games_played: int
    games_won: int
    win_rate: float
    rank: Optional[int] = None
    
    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """User login schema"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class UserToken(BaseModel):
    """User token response schema"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class PasswordChange(BaseModel):
    """Password change schema"""
    current_password: str = Field(..., description="当前密码")
    new_password: str = Field(..., min_length=8, max_length=128, description="新密码")
    
    @validator('new_password')
    def validate_new_password(cls, v):
        """验证新密码强度"""
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('密码必须包含至少一个字母')
        if not re.search(r'\d', v):
            raise ValueError('密码必须包含至少一个数字')
        return v