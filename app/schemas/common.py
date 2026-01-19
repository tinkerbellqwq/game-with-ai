"""
Common Pydantic schemas
通用数据验证和序列化模型
"""

from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List
from datetime import datetime
from enum import Enum


class ResponseStatus(str, Enum):
    """响应状态枚举"""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"


class BaseResponse(BaseModel):
    """基础响应模型"""
    status: ResponseStatus = ResponseStatus.SUCCESS
    message: str = ""
    data: Optional[Any] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ErrorResponse(BaseResponse):
    """错误响应模型"""
    status: ResponseStatus = ResponseStatus.ERROR
    error_code: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None


class SuccessResponse(BaseResponse):
    """成功响应模型"""
    status: ResponseStatus = ResponseStatus.SUCCESS


class PaginationMeta(BaseModel):
    """分页元数据"""
    page: int = Field(..., ge=1, description="当前页码")
    page_size: int = Field(..., ge=1, le=100, description="每页数量")
    total: int = Field(..., ge=0, description="总记录数")
    total_pages: int = Field(..., ge=0, description="总页数")
    has_next: bool = Field(..., description="是否有下一页")
    has_prev: bool = Field(..., description="是否有上一页")


class PaginatedResponse(BaseModel):
    """分页响应模型"""
    items: List[Any] = Field(default_factory=list, description="数据项")
    meta: PaginationMeta = Field(..., description="分页信息")


class WebSocketMessage(BaseModel):
    """WebSocket消息模型"""
    type: str = Field(..., description="消息类型")
    data: Optional[Dict[str, Any]] = Field(None, description="消息数据")
    timestamp: datetime = Field(default_factory=datetime.now)
    sender_id: Optional[str] = Field(None, description="发送者ID")
    room_id: Optional[str] = Field(None, description="房间ID")


class NotificationMessage(BaseModel):
    """通知消息模型"""
    id: str
    type: str = Field(..., description="通知类型")
    title: str = Field(..., description="通知标题")
    content: str = Field(..., description="通知内容")
    priority: str = Field(default="normal", description="优先级: low, normal, high")
    read: bool = Field(default=False, description="是否已读")
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = Field(None, description="过期时间")


class SystemHealth(BaseModel):
    """系统健康状态"""
    status: str = Field(..., description="系统状态: healthy, warning, error")
    timestamp: datetime = Field(default_factory=datetime.now)
    services: Dict[str, str] = Field(default_factory=dict, description="服务状态")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="系统指标")


class RateLimitInfo(BaseModel):
    """速率限制信息"""
    limit: int = Field(..., description="限制次数")
    remaining: int = Field(..., description="剩余次数")
    reset_time: datetime = Field(..., description="重置时间")
    retry_after: Optional[int] = Field(None, description="重试等待时间(秒)")


class ValidationError(BaseModel):
    """验证错误详情"""
    field: str = Field(..., description="字段名")
    message: str = Field(..., description="错误信息")
    value: Optional[Any] = Field(None, description="错误值")


class BatchOperation(BaseModel):
    """批量操作请求"""
    operation: str = Field(..., description="操作类型")
    items: List[str] = Field(..., min_items=1, max_items=100, description="操作项ID列表")
    parameters: Optional[Dict[str, Any]] = Field(None, description="操作参数")


class BatchOperationResult(BaseModel):
    """批量操作结果"""
    total: int = Field(..., description="总数")
    success: int = Field(..., description="成功数")
    failed: int = Field(..., description="失败数")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="错误详情")


class FileUpload(BaseModel):
    """文件上传信息"""
    filename: str = Field(..., description="文件名")
    content_type: str = Field(..., description="文件类型")
    size: int = Field(..., ge=0, description="文件大小(字节)")
    url: Optional[str] = Field(None, description="文件URL")
    upload_time: datetime = Field(default_factory=datetime.now)


class SearchQuery(BaseModel):
    """搜索查询"""
    query: str = Field(..., min_length=1, max_length=100, description="搜索关键词")
    filters: Optional[Dict[str, Any]] = Field(None, description="过滤条件")
    sort_by: Optional[str] = Field(None, description="排序字段")
    sort_order: str = Field(default="desc", description="排序方向: asc, desc")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


class SearchResult(BaseModel):
    """搜索结果"""
    query: str = Field(..., description="搜索关键词")
    results: List[Any] = Field(default_factory=list, description="搜索结果")
    total: int = Field(..., ge=0, description="总结果数")
    took_ms: int = Field(..., ge=0, description="搜索耗时(毫秒)")
    suggestions: List[str] = Field(default_factory=list, description="搜索建议")


class CacheInfo(BaseModel):
    """缓存信息"""
    key: str = Field(..., description="缓存键")
    ttl: Optional[int] = Field(None, description="生存时间(秒)")
    size: Optional[int] = Field(None, description="缓存大小(字节)")
    hit_count: int = Field(default=0, description="命中次数")
    miss_count: int = Field(default=0, description="未命中次数")


class LogEntry(BaseModel):
    """日志条目"""
    level: str = Field(..., description="日志级别")
    message: str = Field(..., description="日志消息")
    timestamp: datetime = Field(default_factory=datetime.now)
    source: Optional[str] = Field(None, description="日志来源")
    user_id: Optional[str] = Field(None, description="用户ID")
    request_id: Optional[str] = Field(None, description="请求ID")
    extra: Optional[Dict[str, Any]] = Field(None, description="额外信息")


class MessageResponse(BaseModel):
    """简单消息响应"""
    message: str = Field(..., description="响应消息")
    success: bool = Field(default=True, description="操作是否成功")