# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

谁是卧底游戏平台 - 基于 FastAPI 的在线多人"谁是卧底"游戏，支持玩家对战和 AI 对手。系统针对 2C2G (2核2GB) 服务器环境进行了特别优化。

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 修改后
修改后不用进行任何操作，前端和后端均有热重载功能

# 后端日志位置，每次看后100行左右即可
logs/app.log

#日志查看常用命令
powershell -Command "Get-Content 'D:\dev\game-with-ai\logs\app.log' -Tail 500"

# Docker 启动
docker-compose up -d

# 数据库迁移
alembic revision --autogenerate -m "描述"
alembic upgrade head

# 运行所有测试
pytest

# 运行特定类型测试
pytest -m unit          # 单元测试
pytest -m property      # 属性测试 (hypothesis)
pytest -m integration   # 集成测试

# 运行单个测试文件
pytest tests/test_auth.py -v

# 生成覆盖率报告
pytest --cov=app
```

## 技术架构

### 技术栈
- **后端**: FastAPI + Python 3.11 + uvicorn
- **数据库**: MySQL 8.0 (SQLAlchemy ORM) + Redis 7.0 (缓存/会话/消息队列)
- **AI**: OpenAI GPT-3.5-turbo
- **实时通信**: WebSocket
- **测试**: pytest + hypothesis (属性测试)

### 核心模块

```
app/
├── main.py              # 应用入口，lifespan 管理
├── core/
│   ├── config.py        # 配置管理 (pydantic-settings)
│   ├── database.py      # MySQL 连接池管理
│   └── redis_client.py  # Redis 连接管理
├── api/v1/
│   ├── api.py           # 路由汇总
│   └── endpoints/       # 各 API 端点 (auth, rooms, games, websocket, leaderboard, settlement, health)
├── services/            # 业务逻辑层
│   ├── auth.py          # 认证服务
│   ├── room.py          # 房间管理
│   ├── game.py          # 游戏核心逻辑
│   ├── game_orchestrator.py  # 游戏流程编排
│   ├── ai_player.py     # AI 玩家服务
│   ├── llm.py           # OpenAI API 集成
│   ├── leaderboard.py   # 排行榜服务
│   ├── settlement.py    # 结算系统
│   └── game_recovery.py # 游戏状态恢复
├── models/              # SQLAlchemy 数据模型 (user, room, game, word_pair, ai_player)
├── schemas/             # Pydantic 数据模式
├── websocket/           # WebSocket 连接管理
│   ├── connection_manager.py
│   └── chat_manager.py
├── middleware/
│   └── security.py      # 安全中间件 (速率限制、日志)
└── utils/
    ├── security.py      # 安全工具 (JWT, 密码哈希)
    ├── session.py       # 会话管理
    ├── resource_monitor.py   # 资源监控
    └── performance_optimizer.py  # 性能优化
```

### API 路由结构

- `/api/v1/auth/*` - 用户认证 (注册、登录、登出)
- `/api/v1/rooms/*` - 房间管理
- `/api/v1/games/*` - 游戏逻辑
- `/api/v1/ws/*` - WebSocket 连接
- `/api/v1/leaderboard/*` - 排行榜
- `/api/v1/settlement/*` - 结算系统
- `/health` - 健康检查
- `/resources` - 资源监控

### 游戏流程

1. **准备阶段** - 创建房间、玩家加入、分配角色(卧底/平民)和词汇
2. **发言阶段** - 玩家轮流描述自己的词汇
3. **投票阶段** - 投票淘汰可疑玩家
4. **结果阶段** - 判断胜负、积分结算

### 2C2G 优化要点

- 单进程模式 (WORKERS=1)
- 数据库连接池: 5 个连接
- Redis 连接池: 5 个连接
- WebSocket 并发限制: 50 个
- 最大内存: 1500MB (为系统预留 500MB)
- 最大并发房间: 10 个
- 最大并发游戏: 5 个

## 测试规范

项目使用双重测试策略:
- **单元测试**: 验证具体业务场景
- **属性测试 (hypothesis)**: 验证通用属性，每个属性至少 100 次迭代

属性测试标签格式:
```python
"""
Feature: undercover-game-platform, Property {number}: {property_text}
验证需求: 需求 X.X
"""
```

## 环境配置

复制 `.env.example` 为 `.env` 并配置:
- `DATABASE_URL` - MySQL 连接字符串
- `REDIS_URL` - Redis 连接字符串
- `SECRET_KEY` - JWT 密钥
- `OPENAI_API_KEY` - OpenAI API 密钥

---

## 前端技术栈与 UI 规范

### 前端技术栈

```
frontend/
├── Vue 3 (Composition API)
├── Tailwind CSS v3.x
├── @vueuse/motion (动画)
├── lucide-vue-next (图标)
├── vue-router
├── pinia (状态管理)
└── axios
```

### UI 设计规范 (macOS Style)

前端 UI 遵循 Apple Human Interface Guidelines 风格，详见 `UI.md`。

**核心设计原则**:
1. **毛玻璃效果**: 使用 `backdrop-blur` + `saturate` + 半透明背景
2. **0.5px 边框**: 使用 `border-[0.5px]` 或 `box-shadow` 模拟细边框
3. **顶部高光**: 浮动容器使用 `shadow-[inset_0_1px_0_0_rgba(255,255,255,0.4)]`
4. **暗色模式优先**: 所有颜色必须有 `dark:` 变体
5. **弹簧动画**: 使用 `@vueuse/motion` 或 CSS transition

**常用 Tailwind 类**:
```
// 毛玻璃卡片
bg-white/80 dark:bg-[#282828]/70 backdrop-blur-3xl rounded-2xl

// 主按钮
bg-gradient-to-b from-blue-500 to-blue-600 text-white rounded-lg active:scale-[0.98]

// 输入框
bg-white dark:bg-white/5 rounded-lg border-[0.5px] border-black/10 dark:border-white/10
```

### 前端命令

```bash
cd frontend

# 安装依赖
npm install

# 开发服务器 (热重载)
npm run dev

# 构建生产版本
npm run build
```
