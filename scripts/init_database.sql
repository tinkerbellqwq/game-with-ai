-- ============================================
-- 谁是卧底游戏平台 - 数据库初始化 SQL
-- ============================================

-- 创建数据库
CREATE DATABASE IF NOT EXISTS `undercover_game`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE `undercover_game`;

-- ============================================
-- 用户表
-- ============================================
CREATE TABLE IF NOT EXISTS `users` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `username` VARCHAR(50) NOT NULL,
    `email` VARCHAR(100) NOT NULL,
    `hashed_password` VARCHAR(255) NOT NULL,
    `score` INT DEFAULT 0,
    `games_played` INT DEFAULT 0,
    `games_won` INT DEFAULT 0,
    `is_active` BOOLEAN DEFAULT TRUE,
    `is_superuser` BOOLEAN DEFAULT FALSE,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `ix_users_username` (`username`),
    UNIQUE KEY `ix_users_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 房间表
-- ============================================
CREATE TABLE IF NOT EXISTS `rooms` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL,
    `creator_id` INT NOT NULL,
    `max_players` INT DEFAULT 6,
    `current_players` INT DEFAULT 0,
    `ai_count` INT DEFAULT 0,
    `status` VARCHAR(20) DEFAULT 'waiting',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_rooms_creator_id` (`creator_id`),
    KEY `ix_rooms_status` (`status`),
    CONSTRAINT `fk_rooms_creator` FOREIGN KEY (`creator_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 房间玩家关联表
-- ============================================
CREATE TABLE IF NOT EXISTS `room_players` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `room_id` INT NOT NULL,
    `user_id` INT,
    `ai_player_id` INT,
    `is_ready` BOOLEAN DEFAULT FALSE,
    `joined_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_room_players_room_id` (`room_id`),
    KEY `ix_room_players_user_id` (`user_id`),
    CONSTRAINT `fk_room_players_room` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_room_players_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 词汇对表
-- ============================================
CREATE TABLE IF NOT EXISTS `word_pairs` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `civilian_word` VARCHAR(50) NOT NULL,
    `undercover_word` VARCHAR(50) NOT NULL,
    `category` VARCHAR(50),
    `difficulty` INT DEFAULT 1,
    `is_active` BOOLEAN DEFAULT TRUE,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- AI 玩家表
-- ============================================
CREATE TABLE IF NOT EXISTS `ai_players` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(50) NOT NULL,
    `difficulty` VARCHAR(20) DEFAULT 'normal',
    `personality` VARCHAR(20) DEFAULT 'normal',
    `avatar` VARCHAR(255),
    `is_active` BOOLEAN DEFAULT TRUE,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 游戏表
-- ============================================
CREATE TABLE IF NOT EXISTS `games` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `room_id` INT NOT NULL,
    `word_pair_id` INT,
    `current_phase` VARCHAR(20) DEFAULT 'preparing',
    `round_number` INT DEFAULT 1,
    `current_speaker` INT,
    `winner_role` VARCHAR(20),
    `status` VARCHAR(20) DEFAULT 'active',
    `started_at` DATETIME,
    `ended_at` DATETIME,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_games_room_id` (`room_id`),
    KEY `ix_games_status` (`status`),
    CONSTRAINT `fk_games_room` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_games_word_pair` FOREIGN KEY (`word_pair_id`) REFERENCES `word_pairs` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 游戏玩家表
-- ============================================
CREATE TABLE IF NOT EXISTS `game_players` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `game_id` INT NOT NULL,
    `user_id` INT,
    `ai_player_id` INT,
    `role` VARCHAR(20) NOT NULL,
    `word` VARCHAR(50) NOT NULL,
    `is_alive` BOOLEAN DEFAULT TRUE,
    `speech_order` INT,
    `score_earned` INT DEFAULT 0,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_game_players_game_id` (`game_id`),
    KEY `ix_game_players_user_id` (`user_id`),
    CONSTRAINT `fk_game_players_game` FOREIGN KEY (`game_id`) REFERENCES `games` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_game_players_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_game_players_ai` FOREIGN KEY (`ai_player_id`) REFERENCES `ai_players` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 发言记录表
-- ============================================
CREATE TABLE IF NOT EXISTS `speeches` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `game_id` INT NOT NULL,
    `player_id` INT NOT NULL,
    `round_number` INT NOT NULL,
    `content` TEXT NOT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_speeches_game_id` (`game_id`),
    CONSTRAINT `fk_speeches_game` FOREIGN KEY (`game_id`) REFERENCES `games` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 投票记录表
-- ============================================
CREATE TABLE IF NOT EXISTS `votes` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `game_id` INT NOT NULL,
    `voter_id` INT NOT NULL,
    `target_id` INT NOT NULL,
    `round_number` INT NOT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_votes_game_id` (`game_id`),
    CONSTRAINT `fk_votes_game` FOREIGN KEY (`game_id`) REFERENCES `games` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 初始词汇对数据
-- ============================================
INSERT INTO `word_pairs` (`civilian_word`, `undercover_word`, `category`, `difficulty`, `is_active`) VALUES
('苹果', '梨子', '水果', 1, TRUE),
('西瓜', '哈密瓜', '水果', 1, TRUE),
('香蕉', '芭蕉', '水果', 2, TRUE),
('草莓', '蓝莓', '水果', 1, TRUE),
('老虎', '狮子', '动物', 1, TRUE),
('熊猫', '北极熊', '动物', 2, TRUE),
('大象', '犀牛', '动物', 2, TRUE),
('狗', '狼', '动物', 1, TRUE),
('猫', '豹', '动物', 2, TRUE),
('篮球', '足球', '运动', 1, TRUE),
('乒乓球', '网球', '运动', 1, TRUE),
('游泳', '潜水', '运动', 2, TRUE),
('钢琴', '吉他', '乐器', 1, TRUE),
('小提琴', '大提琴', '乐器', 2, TRUE),
('医生', '护士', '职业', 1, TRUE),
('警察', '保安', '职业', 1, TRUE),
('老师', '教授', '职业', 2, TRUE),
('飞机', '直升机', '交通', 2, TRUE),
('火车', '地铁', '交通', 1, TRUE),
('汽车', '摩托车', '交通', 1, TRUE),
('咖啡', '奶茶', '饮品', 1, TRUE),
('可乐', '雪碧', '饮品', 1, TRUE),
('蛋糕', '面包', '食物', 1, TRUE),
('饺子', '馄饨', '食物', 2, TRUE),
('电脑', '平板', '电子', 1, TRUE),
('手机', '电话', '电子', 1, TRUE),
('眼镜', '墨镜', '配饰', 1, TRUE),
('手表', '手链', '配饰', 2, TRUE),
('沙发', '椅子', '家具', 1, TRUE),
('床', '沙发床', '家具', 2, TRUE),
('雨伞', '阳伞', '日用', 2, TRUE),
('玫瑰', '牡丹', '植物', 2, TRUE),
('向日葵', '菊花', '植物', 2, TRUE),
('大海', '湖泊', '自然', 1, TRUE),
('高山', '丘陵', '自然', 2, TRUE),
('月亮', '太阳', '天体', 1, TRUE),
('春节', '元宵节', '节日', 2, TRUE),
('圣诞节', '元旦', '节日', 2, TRUE),
('北京', '上海', '城市', 1, TRUE),
('长城', '故宫', '景点', 2, TRUE);

-- ============================================
-- 初始 AI 玩家
-- ============================================
INSERT INTO `ai_players` (`name`, `difficulty`, `personality`, `is_active`) VALUES
('小智', 'normal', 'normal', TRUE),
('小慧', 'normal', 'cautious', TRUE),
('阿强', 'normal', 'aggressive', TRUE),
('小萌', 'beginner', 'normal', TRUE),
('大师', 'expert', 'normal', TRUE);

SELECT '数据库初始化完成！' AS message;
