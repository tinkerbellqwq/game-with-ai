#!/usr/bin/env python3
"""
数据库初始化脚本
用于创建 MySQL 数据库和初始化表结构
"""

import os
import sys
import pymysql
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 默认配置
DEFAULT_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "database": "undercover_game",
    "charset": "utf8mb4",
}


def get_config():
    """从环境变量或 .env 文件获取配置"""
    config = DEFAULT_CONFIG.copy()

    # 尝试加载 .env 文件
    env_file = project_root / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

    # 从 DATABASE_URL 解析配置
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        # 格式: mysql+pymysql://user:password@host:port/database
        try:
            url = database_url.replace("mysql+pymysql://", "").replace("mysql+aiomysql://", "")
            user_pass, host_db = url.split("@")
            if ":" in user_pass:
                config["user"], config["password"] = user_pass.split(":", 1)
            else:
                config["user"] = user_pass

            host_port, config["database"] = host_db.split("/")
            if ":" in host_port:
                config["host"], port_str = host_port.split(":")
                config["port"] = int(port_str)
            else:
                config["host"] = host_port
        except Exception as e:
            print(f"解析 DATABASE_URL 失败: {e}")
            print("使用默认配置...")

    return config


def create_database(config):
    """创建数据库"""
    db_name = config["database"]

    # 连接 MySQL（不指定数据库）
    conn_config = {k: v for k, v in config.items() if k != "database"}

    print(f"连接 MySQL 服务器: {config['host']}:{config['port']}")
    print(f"用户: {config['user']}")

    try:
        conn = pymysql.connect(**conn_config)
        cursor = conn.cursor()

        # 检查数据库是否存在
        cursor.execute("SHOW DATABASES LIKE %s", (db_name,))
        exists = cursor.fetchone()

        if exists:
            print(f"数据库 '{db_name}' 已存在")
            response = input("是否删除并重新创建？(y/N): ").strip().lower()
            if response == "y":
                cursor.execute(f"DROP DATABASE `{db_name}`")
                print(f"已删除数据库 '{db_name}'")
            else:
                print("保留现有数据库")
                cursor.close()
                conn.close()
                return True

        # 创建数据库
        cursor.execute(f"""
            CREATE DATABASE `{db_name}`
            CHARACTER SET utf8mb4
            COLLATE utf8mb4_unicode_ci
        """)
        print(f"数据库 '{db_name}' 创建成功！")

        cursor.close()
        conn.close()
        return True

    except pymysql.err.OperationalError as e:
        error_code = e.args[0]
        if error_code == 1045:
            print(f"错误: MySQL 认证失败，请检查用户名和密码")
        elif error_code == 2003:
            print(f"错误: 无法连接到 MySQL 服务器 {config['host']}:{config['port']}")
            print("请确保 MySQL 服务已启动")
        else:
            print(f"MySQL 错误: {e}")
        return False
    except Exception as e:
        print(f"创建数据库失败: {e}")
        return False


def init_tables(config):
    """初始化表结构（通过运行 SQLAlchemy 模型）"""
    print("\n初始化表结构...")

    try:
        # 设置环境变量
        os.environ["DATABASE_URL"] = (
            f"mysql+pymysql://{config['user']}:{config['password']}@"
            f"{config['host']}:{config['port']}/{config['database']}"
        )

        # 导入并创建表
        from sqlalchemy import create_engine
        from app.core.database import Base
        from app.models import user, room, game, word_pair, ai_player  # noqa

        engine = create_engine(
            os.environ["DATABASE_URL"],
            echo=False
        )

        Base.metadata.create_all(engine)
        print("表结构创建成功！")

        engine.dispose()
        return True

    except Exception as e:
        print(f"初始化表结构失败: {e}")
        return False


def init_word_pairs(config):
    """初始化词汇对数据"""
    print("\n初始化词汇对数据...")
    import uuid

    # 默认词汇对: (平民词, 卧底词, 分类, 难度)
    word_pairs = [
        ("苹果", "梨子", "水果", 1),
        ("西瓜", "哈密瓜", "水果", 1),
        ("香蕉", "芭蕉", "水果", 2),
        ("草莓", "蓝莓", "水果", 1),
        ("老虎", "狮子", "动物", 1),
        ("熊猫", "北极熊", "动物", 2),
        ("大象", "犀牛", "动物", 2),
        ("狗", "狼", "动物", 1),
        ("篮球", "足球", "运动", 1),
        ("乒乓球", "网球", "运动", 1),
        ("钢琴", "吉他", "乐器", 1),
        ("小提琴", "大提琴", "乐器", 2),
        ("医生", "护士", "职业", 1),
        ("警察", "保安", "职业", 1),
        ("老师", "教授", "职业", 2),
        ("飞机", "直升机", "交通", 2),
        ("火车", "地铁", "交通", 1),
        ("汽车", "摩托车", "交通", 1),
        ("咖啡", "奶茶", "饮品", 1),
        ("可乐", "雪碧", "饮品", 1),
        ("蛋糕", "面包", "食物", 1),
        ("饺子", "馄饨", "食物", 2),
        ("电脑", "平板", "电子", 1),
        ("手机", "电话", "电子", 1),
        ("眼镜", "墨镜", "配饰", 1),
        ("沙发", "椅子", "家具", 1),
        ("雨伞", "阳伞", "日用", 2),
        ("玫瑰", "牡丹", "植物", 2),
        ("大海", "湖泊", "自然", 1),
        ("高山", "丘陵", "自然", 2),
    ]

    try:
        conn = pymysql.connect(**config)
        cursor = conn.cursor()

        # 检查是否已有数据
        cursor.execute("SELECT COUNT(*) FROM word_pairs")
        count = cursor.fetchone()[0]

        if count > 0:
            print(f"词汇对表已有 {count} 条数据")
            response = input("是否清空并重新导入？(y/N): ").strip().lower()
            if response != "y":
                print("保留现有数据")
                cursor.close()
                conn.close()
                return True
            cursor.execute("DELETE FROM word_pairs")

        # 插入词汇对
        for civilian_word, undercover_word, category, difficulty in word_pairs:
            pair_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO word_pairs (id, civilian_word, undercover_word, category, difficulty) VALUES (%s, %s, %s, %s, %s)",
                (pair_id, civilian_word, undercover_word, category, difficulty)
            )

        conn.commit()
        print(f"成功导入 {len(word_pairs)} 组词汇对！")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"初始化词汇对失败: {e}")
        return False


def check_redis():
    """检查 Redis 连接"""
    print("\n检查 Redis 连接...")

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    try:
        import redis

        # 解析 Redis URL
        if redis_url.startswith("redis://"):
            redis_url = redis_url[8:]

        host_port, db = redis_url.split("/") if "/" in redis_url else (redis_url, "0")
        host, port = host_port.split(":") if ":" in host_port else (host_port, "6379")

        r = redis.Redis(host=host, port=int(port), db=int(db))
        r.ping()
        print(f"Redis 连接成功: {host}:{port}")
        return True

    except ImportError:
        print("警告: redis 库未安装，跳过 Redis 检查")
        return True
    except Exception as e:
        print(f"Redis 连接失败: {e}")
        print("请确保 Redis 服务已启动")
        return False


def main():
    print("=" * 50)
    print("  谁是卧底游戏平台 - 数据库初始化脚本")
    print("=" * 50)
    print()

    # 获取配置
    config = get_config()
    print(f"数据库: {config['database']}")
    print(f"服务器: {config['host']}:{config['port']}")
    print()

    # 创建数据库
    if not create_database(config):
        print("\n数据库创建失败，退出")
        sys.exit(1)

    # 初始化表结构
    if not init_tables(config):
        print("\n表结构初始化失败，退出")
        sys.exit(1)

    # 初始化词汇对
    if not init_word_pairs(config):
        print("\n词汇对初始化失败")

    # 检查 Redis
    check_redis()

    print("\n" + "=" * 50)
    print("  数据库初始化完成！")
    print("=" * 50)
    print("\n现在可以启动后端服务：")
    print("  python run.py")
    print()


if __name__ == "__main__":
    main()
