#!/bin/bash

# ============================================
# 谁是卧底游戏平台 - 2C2G 服务器部署脚本
# ============================================

set -e

echo "=========================================="
echo "  谁是卧底游戏平台 - 部署脚本"
echo "  适用于: Ubuntu/Debian + 2C2G 服务器"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查是否为 root 用户
check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}请使用 root 用户或 sudo 运行此脚本${NC}"
        exit 1
    fi
}

# 第一步: 安装 Docker
install_docker() {
    echo -e "\n${YELLOW}[1/6] 安装 Docker...${NC}"

    if command -v docker &> /dev/null; then
        echo -e "${GREEN}Docker 已安装${NC}"
        docker --version
    else
        apt-get update
        apt-get install -y ca-certificates curl gnupg

        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg

        echo \
          "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
          $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
          tee /etc/apt/sources.list.d/docker.list > /dev/null

        apt-get update
        apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

        systemctl enable docker
        systemctl start docker

        echo -e "${GREEN}Docker 安装完成${NC}"
    fi
}

# 第二步: 安装 Node.js (用于构建前端)
install_nodejs() {
    echo -e "\n${YELLOW}[2/6] 安装 Node.js...${NC}"

    if command -v node &> /dev/null; then
        echo -e "${GREEN}Node.js 已安装${NC}"
        node --version
    else
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
        apt-get install -y nodejs
        echo -e "${GREEN}Node.js 安装完成${NC}"
    fi
}

# 第三步: 配置环境变量
setup_env() {
    echo -e "\n${YELLOW}[3/6] 配置环境变量...${NC}"

    if [ ! -f .env.prod ]; then
        # 生成随机密码和密钥
        DB_PASSWORD=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 16)
        DB_ROOT_PASSWORD=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 16)
        SECRET_KEY=$(openssl rand -base64 32)

        cat > .env.prod << EOF
# 数据库配置 (自动生成的密码)
DB_PASSWORD=${DB_PASSWORD}
DB_ROOT_PASSWORD=${DB_ROOT_PASSWORD}

# 应用密钥 (自动生成)
SECRET_KEY=${SECRET_KEY}

# OpenAI API (请手动填写)
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1

# OpenRouter API (请手动填写)
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_API_BASE=https://openrouter.ai/api/v1

# 管理员密码
ADMIN_PASSWORD=admin123
EOF

        echo -e "${GREEN}.env.prod 文件已创建${NC}"
        echo -e "${YELLOW}请编辑 .env.prod 文件，填写 API 密钥:${NC}"
        echo "  nano .env.prod"
    else
        echo -e "${GREEN}.env.prod 已存在${NC}"
    fi
}

# 第四步: 构建前端
build_frontend() {
    echo -e "\n${YELLOW}[4/6] 构建前端...${NC}"

    cd frontend

    # 安装依赖
    if [ ! -d "node_modules" ]; then
        npm install
    fi

    # 构建生产版本
    npm run build

    cd ..

    echo -e "${GREEN}前端构建完成${NC}"
}

# 第五步: 启动服务
start_services() {
    echo -e "\n${YELLOW}[5/6] 启动 Docker 服务...${NC}"

    # 加载环境变量
    set -a
    source .env.prod
    set +a

    # 构建并启动
    docker compose -f docker-compose.prod.yml up -d --build

    echo -e "${GREEN}服务启动中...${NC}"

    # 等待服务启动
    echo "等待服务启动..."
    sleep 10
}

# 第六步: 初始化数据库
init_database() {
    echo -e "\n${YELLOW}[6/6] 初始化数据库...${NC}"

    # 等待 MySQL 完全启动
    echo "等待 MySQL 启动..."
    sleep 20

    # 运行数据库迁移
    docker compose -f docker-compose.prod.yml exec -T app alembic upgrade head

    # 初始化词汇数据
    docker compose -f docker-compose.prod.yml exec -T app python -m scripts.init_word_pairs

    echo -e "${GREEN}数据库初始化完成${NC}"
}

# 显示部署结果
show_result() {
    echo ""
    echo "=========================================="
    echo -e "${GREEN}  部署完成!${NC}"
    echo "=========================================="
    echo ""
    echo "访问地址: http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_SERVER_IP')"
    echo ""
    echo "常用命令:"
    echo "  查看日志:     docker compose -f docker-compose.prod.yml logs -f"
    echo "  重启服务:     docker compose -f docker-compose.prod.yml restart"
    echo "  停止服务:     docker compose -f docker-compose.prod.yml down"
    echo "  查看状态:     docker compose -f docker-compose.prod.yml ps"
    echo ""
    echo "注意事项:"
    echo "  1. 请确保 .env.prod 中的 API 密钥已正确配置"
    echo "  2. 建议配置 HTTPS (使用 Let's Encrypt)"
    echo "  3. 定期备份 MySQL 数据"
    echo ""
}

# 主流程
main() {
    check_root
    install_docker
    install_nodejs
    setup_env

    echo ""
    read -p "是否继续部署? (已配置好 .env.prod 中的 API 密钥) [y/N] " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        build_frontend
        start_services
        init_database
        show_result
    else
        echo ""
        echo "请先编辑 .env.prod 文件配置 API 密钥，然后重新运行此脚本"
        echo "  nano .env.prod"
    fi
}

# 运行
main "$@"
