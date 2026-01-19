# 谁是卧底游戏平台 (Undercover Game Platform)

一个基于FastAPI的在线多人谁是卧底游戏平台，支持玩家对战和AI对手。

## 功能特性

- 🎮 实时多人游戏
- 🤖 AI智能对手
- 💬 WebSocket实时通信
- 🏆 积分系统和排行榜
- 🔐 用户认证和会话管理
- 📊 游戏统计和历史记录

## 技术栈

- **后端**: FastAPI + Python 3.11
- **数据库**: MySQL + Redis
- **AI**: OpenAI GPT-3.5-turbo
- **实时通信**: WebSocket
- **测试**: pytest + hypothesis

## 2C2G服务器优化

本项目针对2C2G服务器环境进行了特别优化：

### 资源限制
- 内存使用限制在1.5GB以内（为系统预留500MB）
- CPU使用率限制在80%以内
- 数据库连接池限制为5个连接
- Redis连接池限制为5个连接
- WebSocket并发连接限制为50个

### 性能优化
- 单进程模式运行（WORKERS=1）
- 实时资源监控和自动清理
- 优化的MySQL和Redis配置
- 游戏状态优先缓存在Redis
- 自动垃圾回收机制

### 监控功能
- 实时内存和CPU使用率监控
- 系统健康检查（数据库、Redis、应用状态）
- 资源使用告警和自动降级
- 详细的健康检查端点：`/health` 和 `/resources`

### 启动脚本
```bash
# 2C2G优化启动
python start_2c2g.py
```

## 快速开始

### 环境要求

- Python 3.11+
- MySQL 8.0+
- Redis 7.0+

### 安装依赖

```bash
pip install -r requirements.txt
```

### 环境配置

1. 复制环境配置文件：
```bash
cp .env.example .env
```

2. 修改 `.env` 文件中的配置项

### 数据库初始化

```bash
# 创建数据库迁移
alembic revision --autogenerate -m "Initial migration"

# 执行迁移
alembic upgrade head
```

### 启动服务

```bash
# 开发模式
python run.py

# 或使用uvicorn
uvicorn app.main:app --reload
```

### 使用Docker

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f app
```

## API文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 测试

```bash
# 运行所有测试
pytest

# 运行特定类型的测试
pytest -m unit
pytest -m property
pytest -m integration

# 生成覆盖率报告
pytest --cov=app
```

## 项目结构

```
app/
├── api/                # API路由
├── core/              # 核心配置
├── models/            # 数据模型
├── schemas/           # Pydantic模式
├── services/          # 业务逻辑
├── utils/             # 工具函数
└── websocket/         # WebSocket管理

tests/                 # 测试文件
alembic/              # 数据库迁移
```

## 开发指南

### 代码规范

- 使用Python类型提示
- 遵循PEP 8代码风格
- 编写单元测试和属性测试
- 添加适当的文档字符串

### 提交规范

- feat: 新功能
- fix: 修复bug
- docs: 文档更新
- test: 测试相关
- refactor: 代码重构

## 许可证

MIT License