# 谁是卧底游戏平台 - 2C2G 服务器部署指南

## 系统要求

- Ubuntu 20.04/22.04 或 Debian 11/12
- 2 核 CPU, 2GB 内存
- 20GB+ 磁盘空间
- 开放端口: 80 (HTTP), 443 (HTTPS, 可选)

## 快速部署

### 方式一: 一键部署脚本

```bash
# 1. 上传项目到服务器
scp -r . user@your-server:/opt/game-with-ai

# 2. SSH 登录服务器
ssh user@your-server

# 3. 进入项目目录
cd /opt/game-with-ai

# 4. 运行部署脚本
sudo bash deploy.sh
```

### 方式二: 手动部署

#### 1. 安装 Docker

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装依赖
sudo apt install -y ca-certificates curl gnupg

# 添加 Docker GPG 密钥
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# 添加 Docker 仓库
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 安装 Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 启动 Docker
sudo systemctl enable docker
sudo systemctl start docker
```

#### 2. 安装 Node.js (构建前端)

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

#### 3. 上传项目文件

```bash
# 在本地执行
scp -r . user@your-server:/opt/game-with-ai
```

#### 4. 配置环境变量

```bash
cd /opt/game-with-ai

# 创建生产环境配置
cat > .env.prod << 'EOF'
# 数据库配置
DB_PASSWORD=your_db_password
DB_ROOT_PASSWORD=your_root_password

# 应用密钥 (使用 openssl rand -base64 32 生成)
SECRET_KEY=your_secret_key

# OpenAI API
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1

# OpenRouter API (用于其他模型)
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_API_BASE=https://openrouter.ai/api/v1

# 管理员密码
ADMIN_PASSWORD=your_admin_password
EOF

# 编辑配置
nano .env.prod
```

#### 5. 构建前端

```bash
cd frontend
npm install
npm run build
cd ..
```

#### 6. 启动服务

```bash
# 加载环境变量
set -a && source .env.prod && set +a

# 构建并启动
sudo docker compose -f docker-compose.prod.yml up -d --build
```

#### 7. 初始化数据库

```bash
# 等待 MySQL 启动 (约 30 秒)
sleep 30

# 运行数据库迁移
sudo docker compose -f docker-compose.prod.yml exec app alembic upgrade head

# 初始化词汇数据
sudo docker compose -f docker-compose.prod.yml exec app python -m scripts.init_word_pairs
```

## 常用命令

```bash
# 查看服务状态
sudo docker compose -f docker-compose.prod.yml ps

# 查看日志
sudo docker compose -f docker-compose.prod.yml logs -f

# 查看特定服务日志
sudo docker compose -f docker-compose.prod.yml logs -f app

# 重启服务
sudo docker compose -f docker-compose.prod.yml restart

# 停止服务
sudo docker compose -f docker-compose.prod.yml down

# 重新构建并启动
sudo docker compose -f docker-compose.prod.yml up -d --build
```

## 资源使用情况

针对 2C2G 服务器的资源分配:

| 服务 | 内存限制 | CPU 限制 |
|------|----------|----------|
| Nginx | 64MB | 0.25 核 |
| App (FastAPI) | 768MB | 0.75 核 |
| MySQL | 512MB | 0.5 核 |
| Redis | 128MB | 0.25 核 |
| **总计** | ~1.5GB | ~1.75 核 |

预留约 500MB 内存给操作系统。

## HTTPS 配置 (可选)

使用 Certbot 获取免费 SSL 证书:

```bash
# 安装 Certbot
sudo apt install -y certbot

# 停止 Nginx
sudo docker compose -f docker-compose.prod.yml stop nginx

# 获取证书
sudo certbot certonly --standalone -d your-domain.com

# 修改 nginx.conf 添加 HTTPS 配置
# 然后重启服务
sudo docker compose -f docker-compose.prod.yml up -d
```

## 备份

```bash
# 备份 MySQL 数据
sudo docker compose -f docker-compose.prod.yml exec mysql \
  mysqldump -u root -p${DB_ROOT_PASSWORD} undercover_game > backup.sql

# 恢复数据
cat backup.sql | sudo docker compose -f docker-compose.prod.yml exec -T mysql \
  mysql -u root -p${DB_ROOT_PASSWORD} undercover_game
```

## 故障排查

```bash
# 检查容器状态
sudo docker compose -f docker-compose.prod.yml ps

# 查看容器日志
sudo docker compose -f docker-compose.prod.yml logs app

# 进入容器调试
sudo docker compose -f docker-compose.prod.yml exec app bash

# 检查数据库连接
sudo docker compose -f docker-compose.prod.yml exec app python -c "
from app.core.database import init_db
import asyncio
asyncio.run(init_db())
print('Database OK')
"

# 检查 Redis 连接
sudo docker compose -f docker-compose.prod.yml exec redis redis-cli ping
```

## 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建前端
cd frontend && npm run build && cd ..

# 重新构建并启动
sudo docker compose -f docker-compose.prod.yml up -d --build

# 运行数据库迁移 (如有)
sudo docker compose -f docker-compose.prod.yml exec app alembic upgrade head
```
