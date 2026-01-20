#!/bin/bash

# ============================================
# 谁是卧底游戏平台 - VPS 部署脚本
# 从 GitHub 克隆/更新并部署
# ============================================

set -e

REPO_URL="https://github.com/tinkerbellqwq/game-with-ai.git"
INSTALL_DIR="/opt/game-with-ai"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}请使用 sudo 运行此脚本${NC}"
        exit 1
    fi
}

install_docker() {
    if command -v docker &> /dev/null; then
        echo -e "${GREEN}✓ Docker 已安装${NC}"
        return
    fi

    echo -e "${YELLOW}安装 Docker...${NC}"
    apt-get update
    apt-get install -y ca-certificates curl gnupg

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    systemctl enable docker
    systemctl start docker
    echo -e "${GREEN}✓ Docker 安装完成${NC}"
}

install_nodejs() {
    if command -v node &> /dev/null; then
        echo -e "${GREEN}✓ Node.js 已安装${NC}"
        return
    fi

    echo -e "${YELLOW}安装 Node.js...${NC}"
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
    echo -e "${GREEN}✓ Node.js 安装完成${NC}"
}

clone_or_pull() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        echo -e "${YELLOW}更新代码...${NC}"
        cd "$INSTALL_DIR"
        git fetch origin
        git reset --hard origin/master
    else
        echo -e "${YELLOW}克隆代码...${NC}"
        rm -rf "$INSTALL_DIR"
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
    echo -e "${GREEN}✓ 代码已就绪${NC}"
}

setup_env() {
    cd "$INSTALL_DIR"

    if [ ! -f .env.prod ]; then
        echo -e "${YELLOW}创建环境配置...${NC}"

        DB_PASSWORD=$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9')
        DB_ROOT_PASSWORD=$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9')
        SECRET_KEY=$(openssl rand -base64 32)

        cat > .env.prod << EOF
# === 数据库配置 (自动生成) ===
DB_PASSWORD=${DB_PASSWORD}
DB_ROOT_PASSWORD=${DB_ROOT_PASSWORD}

# === 应用密钥 (自动生成) ===
SECRET_KEY=${SECRET_KEY}

# === API 配置 (请手动填写) ===
# OpenAI 或兼容 API
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1

# OpenRouter (可选，用于多模型支持)
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_API_BASE=https://openrouter.ai/api/v1
EOF

        echo -e "${GREEN}✓ .env.prod 已创建${NC}"
        echo ""
        echo -e "${YELLOW}>>> 请编辑 .env.prod 填写 API 密钥:${NC}"
        echo "    nano $INSTALL_DIR/.env.prod"
        echo ""
        echo -e "${YELLOW}>>> 配置完成后，运行:${NC}"
        echo "    sudo $INSTALL_DIR/scripts/server-deploy.sh start"
        exit 0
    fi

    echo -e "${GREEN}✓ .env.prod 已存在${NC}"
}

build_frontend() {
    echo -e "${YELLOW}构建前端...${NC}"
    cd "$INSTALL_DIR/frontend"
    npm install --legacy-peer-deps
    npm run build
    echo -e "${GREEN}✓ 前端构建完成${NC}"
}

start_services() {
    echo -e "${YELLOW}启动服务...${NC}"
    cd "$INSTALL_DIR"

    # 检查 .env.prod 是否存在
    if [ ! -f .env.prod ]; then
        echo -e "${RED}✘ 错误: .env.prod 文件不存在${NC}"
        echo "请先运行 install 命令创建配置文件"
        exit 1
    fi

    docker compose -f docker-compose.prod.yml --env-file .env.prod down 2>/dev/null || true
    docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

    echo -e "${GREEN}✓ 服务已启动${NC}"
}

init_database() {
    echo -e "${YELLOW}初始化数据库 (等待 MySQL 启动...)${NC}"
    sleep 30

    cd "$INSTALL_DIR"
    docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T app alembic upgrade head
    docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T app python -m scripts.init_word_pairs 2>/dev/null || true

    echo -e "${GREEN}✓ 数据库初始化完成${NC}"
}

run_migrations() {
    echo -e "${YELLOW}运行数据库迁移...${NC}"
    cd "$INSTALL_DIR"
    docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T app alembic upgrade head
    echo -e "${GREEN}✓ 迁移完成${NC}"
}

show_status() {
    cd "$INSTALL_DIR"
    echo ""
    echo "=========================================="
    docker compose -f docker-compose.prod.yml --env-file .env.prod ps
    echo "=========================================="

    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    echo ""
    echo -e "${GREEN}访问地址: http://${SERVER_IP}${NC}"
    echo ""
    echo "常用命令:"
    echo "  查看日志:  cd $INSTALL_DIR && docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f"
    echo "  重启服务:  cd $INSTALL_DIR && docker compose -f docker-compose.prod.yml --env-file .env.prod restart"
    echo "  更新部署:  sudo $INSTALL_DIR/scripts/server-deploy.sh update"
}

# === 命令入口 ===
case "${1:-install}" in
    install)
        echo "=========================================="
        echo "  首次安装 - 谁是卧底游戏平台"
        echo "=========================================="
        check_root
        apt-get update && apt-get install -y git curl
        install_docker
        install_nodejs
        clone_or_pull
        setup_env
        ;;

    start)
        echo "=========================================="
        echo "  启动服务"
        echo "=========================================="
        check_root
        build_frontend
        start_services
        init_database
        show_status
        ;;

    update)
        echo "=========================================="
        echo "  更新部署"
        echo "=========================================="
        check_root
        clone_or_pull
        build_frontend
        start_services
        run_migrations
        show_status
        ;;

    status)
        show_status
        ;;

    *)
        echo "用法: $0 {install|start|update|status}"
        echo ""
        echo "  install - 首次安装 (安装依赖 + 克隆代码)"
        echo "  start   - 配置 .env.prod 后启动服务"
        echo "  update  - 从 GitHub 更新并重新部署"
        echo "  status  - 查看服务状态"
        ;;
esac
