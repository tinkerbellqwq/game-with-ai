-- 谁是卧底游戏平台数据库架构
-- Undercover Game Platform Database Schema
-- 针对2C2G服务器环境优化的MySQL数据库设计

-- 创建数据库
CREATE DATABASE IF NOT EXISTS undercover_game 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE undercover_game;

-- 用户表 (Users Table)
CREATE TABLE users (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    score INT NOT NULL DEFAULT 0,
    games_played INT NOT NULL DEFAULT 0,
    games_won INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 索引优化
    INDEX ix_users_username (username),
    INDEX ix_users_email (email),
    INDEX ix_users_score (score),  -- 排行榜查询优化
    INDEX ix_users_created_at (created_at),
    INDEX ix_users_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 词汇对表 (Word Pairs Table)
CREATE TABLE word_pairs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    civilian_word VARCHAR(50) NOT NULL,
    undercover_word VARCHAR(50) NOT NULL,
    category VARCHAR(50) NOT NULL,
    difficulty INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 索引优化
    INDEX ix_word_pairs_category (category),
    INDEX ix_word_pairs_difficulty (difficulty),
    INDEX ix_word_pairs_category_difficulty (category, difficulty)  -- 复合索引
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 房间表 (Rooms Table)
CREATE TABLE rooms (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    creator_id VARCHAR(36) NOT NULL,
    max_players INT NOT NULL DEFAULT 8,
    ai_count INT NOT NULL DEFAULT 0,
    status ENUM('waiting', 'starting', 'playing', 'finished') NOT NULL DEFAULT 'waiting',
    settings JSON NULL,
    current_players JSON NOT NULL DEFAULT ('[]'),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 外键约束
    FOREIGN KEY (creator_id) REFERENCES users(id) ON DELETE CASCADE,
    
    -- 索引优化
    INDEX ix_rooms_creator_id (creator_id),
    INDEX ix_rooms_status (status),
    INDEX ix_rooms_created_at (created_at),
    INDEX ix_rooms_status_created_at (status, created_at)  -- 房间列表查询优化
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 游戏表 (Games Table)
CREATE TABLE games (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    room_id VARCHAR(36) NOT NULL,
    word_pair_id VARCHAR(36) NOT NULL,
    current_phase ENUM('preparing', 'speaking', 'voting', 'result', 'finished') NOT NULL DEFAULT 'preparing',
    current_speaker VARCHAR(36) NULL,
    round_number INT NOT NULL DEFAULT 1,
    players JSON NOT NULL,
    eliminated_players JSON NOT NULL DEFAULT ('[]'),
    winner_role ENUM('civilian', 'undercover') NULL,
    winner_players JSON NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP NULL,
    
    -- 外键约束
    FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
    FOREIGN KEY (word_pair_id) REFERENCES word_pairs(id),
    
    -- 索引优化
    INDEX ix_games_room_id (room_id),
    INDEX ix_games_word_pair_id (word_pair_id),
    INDEX ix_games_current_phase (current_phase),
    INDEX ix_games_started_at (started_at),
    INDEX ix_games_finished_at (finished_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 发言表 (Speeches Table)
CREATE TABLE speeches (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    game_id VARCHAR(36) NOT NULL,
    player_id VARCHAR(36) NOT NULL,
    content TEXT NOT NULL,
    round_number INT NOT NULL,
    speech_order INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 外键约束
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES users(id),
    
    -- 索引优化
    INDEX ix_speeches_game_id (game_id),
    INDEX ix_speeches_player_id (player_id),
    INDEX ix_speeches_round_number (round_number),
    INDEX ix_speeches_game_round (game_id, round_number),  -- 游戏轮次查询优化
    INDEX ix_speeches_game_order (game_id, speech_order)   -- 发言顺序查询优化
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 投票表 (Votes Table)
CREATE TABLE votes (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    game_id VARCHAR(36) NOT NULL,
    voter_id VARCHAR(36) NOT NULL,
    target_id VARCHAR(36) NOT NULL,
    round_number INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 外键约束
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (voter_id) REFERENCES users(id),
    FOREIGN KEY (target_id) REFERENCES users(id),
    
    -- 索引优化
    INDEX ix_votes_game_id (game_id),
    INDEX ix_votes_voter_id (voter_id),
    INDEX ix_votes_target_id (target_id),
    INDEX ix_votes_round_number (round_number),
    INDEX ix_votes_game_round (game_id, round_number),  -- 游戏轮次投票查询优化
    
    -- 唯一约束：防止同一轮次重复投票
    UNIQUE KEY ix_votes_unique_vote (game_id, voter_id, round_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 插入示例词汇对数据
INSERT INTO word_pairs (id, civilian_word, undercover_word, category, difficulty) VALUES
('wp001', '苹果', '梨', '水果', 1),
('wp002', '猫', '狗', '动物', 1),
('wp003', '汽车', '自行车', '交通工具', 2),
('wp004', '医生', '护士', '职业', 2),
('wp005', '电影院', '剧院', '娱乐场所', 3),
('wp006', '小说', '散文', '文学体裁', 3),
('wp007', '钢琴', '古筝', '乐器', 4),
('wp008', '咖啡', '茶', '饮品', 1),
('wp009', '春天', '秋天', '季节', 2),
('wp010', '数学', '物理', '学科', 3);

-- 创建数据库用户（可选，用于生产环境）
-- CREATE USER 'undercover_user'@'localhost' IDENTIFIED BY 'secure_password';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON undercover_game.* TO 'undercover_user'@'localhost';
-- FLUSH PRIVILEGES;

-- 显示表结构信息
SHOW TABLES;