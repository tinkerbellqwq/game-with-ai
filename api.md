# 谁是卧底游戏平台 - API 文档

**基础路径**: `/api/v1`

---

## 1. 用户认证 (Auth)

**前缀**: `/api/v1/auth`

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/register` | POST | 用户注册 | 否 |
| `/login` | POST | 用户登录 | 否 |
| `/logout` | POST | 用户登出 | 是 |
| `/profile` | GET | 获取个人资料 | 是 |
| `/verify` | GET | 验证令牌有效性 | 是 |
| `/refresh` | POST | 刷新会话 | 是 |
| `/security-status` | GET | 获取安全状态 | 是 |

### 1.1 用户注册
```
POST /api/v1/auth/register
```

**请求体 (UserCreate)**:
```json
{
  "username": "string (3-50字符, 支持中文/字母/数字/下划线)",
  "email": "string (有效邮箱格式)",
  "password": "string (8-128字符, 需包含字母和数字)"
}
```

**响应 (UserResponse)**:
```json
{
  "id": "string",
  "username": "string",
  "email": "string",
  "score": 0,
  "games_played": 0,
  "games_won": 0,
  "is_active": true,
  "created_at": "datetime",
  "last_login": "datetime | null"
}
```

### 1.2 用户登录
```
POST /api/v1/auth/login
```

**请求体 (UserLogin)**:
```json
{
  "username": "string (用户名或邮箱)",
  "password": "string"
}
```

**响应 (UserToken)**:
```json
{
  "access_token": "string",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": { /* UserResponse */ }
}
```

### 1.3 用户登出
```
POST /api/v1/auth/logout
Headers: Authorization: Bearer <token>
```

**响应**:
```json
{
  "message": "登出成功"
}
```

---

## 2. 房间管理 (Rooms)

**前缀**: `/api/v1/rooms`

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/` | POST | 创建房间 | 是 |
| `/` | GET | 获取房间列表 | 否 |
| `/{room_id}` | GET | 获取房间详情 | 否 |
| `/{room_id}/join` | POST | 加入房间 | 是 |
| `/{room_id}/leave` | POST | 离开房间 | 是 |
| `/{room_id}` | PUT | 更新房间设置 | 是(房主) |
| `/{room_id}/action` | POST | 房间操作 | 是 |
| `/{room_id}` | DELETE | 解散房间 | 是(房主) |
| `/my-rooms` | GET | 我创建的房间 | 是 |
| `/joined-rooms` | GET | 我加入的房间 | 是 |
| `/statistics` | GET | 房间统计信息 | 否 |
| `/cleanup` | POST | 清理空闲房间 | 是(管理员) |

### 2.1 创建房间
```
POST /api/v1/rooms
```

**请求体 (RoomCreate)**:
```json
{
  "name": "string (1-100字符)",
  "max_players": 8,          // 3-10
  "ai_count": 0,             // 0-5
  "ai_template_ids": ["id1", "id2"],  // 可选
  "settings": {
    "speech_time_limit": 60,    // 30-180秒
    "voting_time_limit": 30,    // 15-60秒
    "auto_start": false,
    "allow_spectators": true,
    "difficulty_level": 1,      // 1-5
    "category_filter": "string | null"
  }
}
```

**响应 (RoomResponse)**:
```json
{
  "id": "string",
  "name": "string",
  "creator_id": "string",
  "creator_name": "string",
  "max_players": 8,
  "current_players": 1,
  "ai_count": 0,
  "status": "waiting | starting | playing | finished",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 2.2 获取房间列表
```
GET /api/v1/rooms?status=waiting&search=关键词&page=1&page_size=20
```

**查询参数 (RoomFilters)**:
| 参数 | 类型 | 描述 |
|------|------|------|
| status | string | 房间状态过滤 |
| has_slots | bool | 是否有空位 |
| min_players | int | 最小玩家数 |
| max_players | int | 最大玩家数 |
| search | string | 搜索关键词 |
| page | int | 页码 (默认1) |
| page_size | int | 每页数量 (1-100, 默认20) |

**响应 (RoomListResponse)**:
```json
{
  "rooms": [ /* RoomResponse[] */ ],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5,
  "has_next": true
}
```

### 2.3 获取房间详情
```
GET /api/v1/rooms/{room_id}
```

**响应 (RoomDetailResponse)**:
```json
{
  /* RoomResponse 字段... */
  "players": [
    {
      "id": "string",
      "username": "string",
      "is_ai": false,
      "is_ready": false,
      "is_creator": true
    }
  ]
}
```

### 2.4 加入房间
```
POST /api/v1/rooms/{room_id}/join
```

**请求体 (RoomJoinRequest)**:
```json
{
  "password": "string | null"
}
```

**响应 (RoomJoinResponse)**:
```json
{
  "success": true,
  "message": "成功加入房间",
  "room": { /* RoomResponse */ }
}
```

### 2.5 房间操作
```
POST /api/v1/rooms/{room_id}/action
```

**请求体 (RoomAction)**:
```json
{
  "action": "start_game | kick_player | transfer_owner | ready | unready",
  "target_user_id": "string | null"  // 踢人/转移房主时需要
}
```

---

## 3. 游戏逻辑 (Games)

**前缀**: `/api/v1/games`

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/` | POST | 创建游戏 | 是 |
| `/{game_id}/start` | POST | 开始游戏 | 是 |
| `/{game_id}` | GET | 获取游戏状态 | 是 |
| `/{game_id}/ready` | POST | 设置准备状态 | 是 |
| `/{game_id}/speech` | POST | 提交发言 | 是 |
| `/{game_id}/skip-speech` | POST | 跳过发言 | 是 |
| `/{game_id}/vote` | POST | 提交投票 | 是 |
| `/{game_id}/result` | GET | 获取游戏结果 | 是 |
| `/{game_id}/summary` | GET | 获取游戏总结 | 是 |
| `/{game_id}/mvp` | GET | 获取MVP玩家 | 是 |
| `/{game_id}/speeches` | GET | 获取发言记录 | 是 |
| `/{game_id}/votes` | GET | 获取投票记录 | 是 |
| `/{game_id}/trigger-ai` | POST | 手动触发AI发言 | 是 |
| `/{game_id}/force-end` | POST | 强制结束游戏 | 是(管理员) |

### 3.1 创建游戏
```
POST /api/v1/games
```

**请求体 (GameCreate)**:
```json
{
  "room_id": "string",
  "word_pair_id": "string | null",  // 可选，不指定则随机
  "difficulty": 1,                   // 1-5
  "category": "string | null"
}
```

### 3.2 获取游戏状态
```
GET /api/v1/games/{game_id}
```

**响应 (GameResponse)**:
```json
{
  "game": {
    "id": "string",
    "room_id": "string",
    "word_pair_id": "string",
    "current_phase": "preparing | speaking | voting | result | finished",
    "current_speaker": "user_id | null",
    "current_speaker_username": "string | null",
    "current_voter": "user_id | null",
    "current_voter_username": "string | null",
    "round_number": 1,
    "players": [
      {
        "id": "string",
        "username": "string",
        "role": "civilian | undercover",
        "word": "string",
        "is_ai": false,
        "is_alive": true,
        "is_ready": true
      }
    ],
    "eliminated_players": ["user_id"],
    "winner_role": "civilian | undercover | null",
    "winner_players": ["user_id"],
    "started_at": "datetime",
    "finished_at": "datetime | null"
  },
  "current_user_role": "civilian | undercover | null",
  "current_user_word": "string | null",
  "can_speak": false,
  "can_vote": false,
  "time_remaining": 45
}
```

### 3.3 提交发言
```
POST /api/v1/games/{game_id}/speech
```

**请求体 (SpeechCreate)**:
```json
{
  "content": "string (1-500字符, 不能包含'卧底'/'平民'/'词汇')"
}
```

**响应 (SpeechResponse)**:
```json
{
  "id": "string",
  "game_id": "string",
  "player_id": "string",
  "player_username": "string",
  "content": "string",
  "round_number": 1,
  "speech_order": 1,
  "created_at": "datetime"
}
```

### 3.4 提交投票
```
POST /api/v1/games/{game_id}/vote
```

**请求体 (VoteCreate)**:
```json
{
  "target_id": "string (目标玩家ID)"
}
```

**响应 (VoteResult)**:
```json
{
  "target_id": "string",
  "target_username": "string",
  "vote_count": 3,
  "is_eliminated": true,
  "revealed_role": "undercover | null"
}
```

### 3.5 获取游戏总结
```
GET /api/v1/games/{game_id}/summary
```

**响应 (GameSummary)**:
```json
{
  "game_id": "string",
  "room_name": "string",
  "word_pair": {
    "civilian": "苹果",
    "undercover": "梨"
  },
  "players": [
    {
      "id": "string",
      "username": "string",
      "role": "civilian",
      "is_winner": true
    }
  ],
  "rounds": [
    {
      "round_number": 1,
      "speeches": [ /* SpeechResponse[] */ ],
      "votes": [ /* VoteResponse[] */ ],
      "vote_result": { /* VoteResult */ },
      "eliminated_player": { /* 被淘汰玩家信息 */ }
    }
  ],
  "winner_role": "civilian",
  "winner_players": ["username1", "username2"],
  "duration_minutes": 15,
  "mvp_player": "username"
}
```

---

## 4. AI 玩家 (AI Players)

**前缀**: `/api/v1/ai-players`

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/` | GET | 获取可用AI列表 | 否 |
| `/{ai_player_id}` | GET | 获取AI详情 | 否 |

### 4.1 获取可用AI列表
```
GET /api/v1/ai-players?active_only=true
```

---

## 5. 排行榜 (Leaderboard)

**前缀**: `/api/v1/leaderboard`

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/` | GET | 获取排行榜 | 否 |
| `/my-rank` | GET | 获取我的排名 | 是 |
| `/user/{user_id}/rank` | GET | 获取指定用户排名 | 否 |
| `/my-stats` | GET | 我的详细统计 | 是 |
| `/refresh-cache` | POST | 刷新缓存 | 是(管理员) |

### 5.1 获取排行榜
```
GET /api/v1/leaderboard?page=1&page_size=20&sort_by=score
```

**查询参数**:
| 参数 | 类型 | 描述 |
|------|------|------|
| page | int | 页码 (默认1) |
| page_size | int | 每页大小 (1-100, 默认20) |
| sort_by | string | 排序字段: score, games_won, win_rate |

**响应 (LeaderboardResponse)**:
```json
{
  "entries": [
    {
      "rank": 1,
      "user_id": "string",
      "username": "string",
      "score": 1500,
      "games_played": 100,
      "games_won": 60,
      "win_rate": 60.0,
      "last_game_at": "datetime"
    }
  ],
  "total_count": 500,
  "page": 1,
  "page_size": 20,
  "total_pages": 25,
  "has_next": true,
  "has_prev": false
}
```

### 5.2 获取我的详细统计
```
GET /api/v1/leaderboard/my-stats
```

**响应 (PersonalStats)**:
```json
{
  "user_id": "string",
  "username": "string",
  "current_rank": 15,
  "score": 1200,
  "games_played": 50,
  "games_won": 30,
  "games_lost": 20,
  "win_rate": 60.0,
  "best_rank": 10,
  "total_score_earned": 2500,
  "average_score_per_game": 50.0,
  "consecutive_wins": 3,
  "max_consecutive_wins": 8,
  "created_at": "datetime",
  "last_game_at": "datetime"
}
```

---

## 6. 结算系统 (Settlement)

**前缀**: `/api/v1/settlement`

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/games/{game_id}/settlement` | POST | 应用游戏积分结算 | 是 |
| `/games/{game_id}/settlement` | GET | 获取结算结果(不执行) | 是 |
| `/games/{game_id}/players/{player_id}/performance` | GET | 获取玩家表现分析 | 是 |
| `/games/{game_id}/mvp` | GET | 获取游戏MVP分析 | 是 |
| `/users/{user_id}/score` | GET | 获取用户实时积分 | 是 |
| `/users/{user_id}/stats` | GET | 获取用户实时统计 | 是 |
| `/users/{user_id}/stats/recalculate` | POST | 重新计算用户统计 | 是(管理员) |
| `/users/{user_id}/cache` | DELETE | 清除用户缓存 | 是(管理员) |
| `/settlement/history` | GET | 获取结算历史记录 | 是(管理员) |

### 6.1 应用游戏积分结算
```
POST /api/v1/settlement/games/{game_id}/settlement
```

**响应**:
```json
{
  "success": true,
  "game_id": "string",
  "settlement_results": { /* 结算详情 */ }
}
```

### 6.2 获取用户实时积分
```
GET /api/v1/settlement/users/{user_id}/score
```

**响应**:
```json
{
  "user_id": "string",
  "score": 1500
}
```

### 6.3 获取用户实时统计
```
GET /api/v1/settlement/users/{user_id}/stats
```

**响应**:
```json
{
  "user_id": "string",
  "stats": { /* 统计详情 */ }
}
```

---

## 7. 系统健康监控 (Health)

**前缀**: 根路径

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 基础健康检查 |
| `/health/detailed` | GET | 详细指标检查 |
| `/health/database` | GET | 数据库连接检查 |
| `/health/redis` | GET | Redis连接检查 |
| `/metrics` | GET | 获取实时系统指标 |
| `/status` | GET | 服务整体运行状态 |
| `/performance` | GET | 性能优化器状态 |
| `/maintenance/cleanup` | POST | 手动资源清理 |

### 7.1 基础健康检查
```
GET /health
```

**响应**:
```json
{
  "status": "healthy",
  "timestamp": "datetime"
}
```

### 7.2 详细指标检查
```
GET /health/detailed
```

**响应**:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "cpu_usage": 25.5,
  "memory_usage": 45.2,
  "active_connections": 15
}
```

---

## 8. WebSocket 实时通信

**前缀**: `/api/v1/ws`

### 8.1 连接端点

| 端点 | 描述 |
|------|------|
| `ws://host/api/v1/ws/{room_id}?token=<jwt>` | 房间WebSocket连接 |
| `ws://host/api/v1/ws/?token=<jwt>` | 通用WebSocket连接 |

### 8.2 消息类型

**客户端发送**:

| type | 描述 | 数据格式 |
|------|------|---------|
| `ping` | 心跳检测 | `{timestamp: number}` |
| `join_room` | 加入房间 | `{room_id: string}` |
| `leave_room` | 离开房间 | `{room_id?: string}` |
| `chat_message` | 发送聊天消息 | `{content: string}` |
| `set_game_phase` | 设置游戏阶段 | `{phase: string}` |
| `eliminate_player` | 淘汰玩家 | `{target_user_id: string}` |
| `mute_room` | 房间静音控制 | `{muted: boolean}` |
| `set_user_permission` | 设置用户权限 | `{target_user_id, permission}` |
| `get_message_history` | 获取消息历史 | `{limit?: number}` |
| `get_room_stats` | 获取房间统计 | `{}` |
| `subscribe_leaderboard` | 订阅排行榜更新 | `{}` |
| `unsubscribe_leaderboard` | 取消订阅 | `{}` |
| `get_live_rank` | 获取实时排名 | `{}` |
| `game_action` | 游戏动作 | `{action_type, action_data}` |

**服务端推送**:

| type | 描述 |
|------|------|
| `pong` | 心跳响应 |
| `join_room_response` | 加入房间响应 |
| `leave_room_response` | 离开房间响应 |
| `chat_message` | 聊天消息广播 |
| `chat_warning` | 聊天警告 |
| `chat_error` | 聊天错误 |
| `game_phase_changed` | 游戏阶段变更 |
| `player_eliminated` | 玩家被淘汰 |
| `permission_changed` | 权限变更通知 |
| `room_mute_changed` | 房间静音状态变更 |
| `message_history` | 消息历史 |
| `room_stats` | 房间统计信息 |
| `leaderboard_subscription` | 排行榜订阅状态 |
| `live_rank_update` | 实时排名更新 |
| `game_action` | 游戏动作广播 |
| `error` | 错误消息 |

### 8.3 HTTP 辅助端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/ws/connections/stats` | GET | 获取连接统计 |
| `/api/v1/ws/connections/cleanup` | POST | 清理不活跃连接 |
| `/api/v1/ws/rooms/{room_id}/users` | GET | 获取房间用户列表 |
| `/api/v1/ws/rooms/{room_id}/chat/stats` | GET | 获取房间聊天统计 |
| `/api/v1/ws/rooms/{room_id}/chat/mute` | POST | 设置房间静音 |
| `/api/v1/ws/rooms/{room_id}/chat/history` | GET | 获取聊天历史 |

### 8.4 连接统计
```
GET /api/v1/ws/connections/stats
```

**响应**:
```json
{
  "active_connections": 25,
  "active_rooms": 5,
  "max_connections": 50
}
```

### 8.5 获取房间用户列表
```
GET /api/v1/ws/rooms/{room_id}/users
```

**响应**:
```json
{
  "room_id": "string",
  "users": ["user_id_1", "user_id_2"],
  "user_count": 2
}
```

### 8.6 获取聊天历史
```
GET /api/v1/ws/rooms/{room_id}/chat/history?limit=50
```

**响应**:
```json
{
  "room_id": "string",
  "messages": [ /* 消息列表 */ ],
  "message_count": 50
}
```

---

## 错误响应格式

所有API在发生错误时返回统一格式:

```json
{
  "detail": "错误描述信息"
}
```

**常见HTTP状态码**:
| 状态码 | 描述 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未认证/Token无效 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 422 | 数据验证失败 |
| 500 | 服务器内部错误 |

---

## 认证方式

使用 **Bearer Token** 认证:

```
Authorization: Bearer <access_token>
```

Token 通过 `/api/v1/auth/login` 获取，有效期在响应的 `expires_in` 字段中指定（秒）。

---

## 枚举值参考

### 房间状态 (RoomStatus)
- `waiting` - 等待中
- `starting` - 正在开始
- `playing` - 游戏中
- `finished` - 已结束

### 游戏阶段 (GamePhase)
- `preparing` - 准备阶段
- `speaking` - 发言阶段
- `voting` - 投票阶段
- `result` - 结果阶段
- `finished` - 已结束

### 玩家角色 (PlayerRole)
- `civilian` - 平民
- `undercover` - 卧底

### 房间操作 (RoomAction)
- `start_game` - 开始游戏
- `kick_player` - 踢出玩家
- `transfer_owner` - 转移房主
- `ready` - 准备
- `unready` - 取消准备

### 游戏操作 (GameAction)
- `ready` - 准备
- `unready` - 取消准备
- `speak` - 发言
- `vote` - 投票
- `skip_speech` - 跳过发言
- `request_hint` - 请求提示
- `surrender` - 投降
