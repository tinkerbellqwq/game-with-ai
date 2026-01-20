"""Initial database schema with optimized indexes

Revision ID: 001
Revises:
Create Date: 2024-01-13 10:00:00.000000

This migration creates all initial tables for the undercover game platform:
- users: Player accounts and statistics
- word_pairs: Game word pairs with categories
- rooms: Game room management
- games: Game session records
- ai_players: AI player configurations
- participants: Unified player/AI participant records per game
- speeches: Player speech records
- votes: Player voting records
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all tables with optimized indexes and constraints"""

    # Create users table
    op.create_table('users',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('email', sa.String(100), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('games_played', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('games_won', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        # Advanced leaderboard fields
        sa.Column('best_rank', sa.Integer(), nullable=True),
        sa.Column('total_score_earned', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('consecutive_wins', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_consecutive_wins', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_game_at', sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )

    # Create indexes for users table
    op.create_index('ix_users_id', 'users', ['id'])
    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_score', 'users', ['score'])  # For leaderboard queries
    op.create_index('ix_users_created_at', 'users', ['created_at'])
    op.create_index('ix_users_is_active', 'users', ['is_active'])
    op.create_index('ix_users_best_rank', 'users', ['best_rank'])
    op.create_index('ix_users_consecutive_wins', 'users', ['consecutive_wins'])
    op.create_index('ix_users_last_game_at', 'users', ['last_game_at'])

    # Create word_pairs table
    op.create_table('word_pairs',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('civilian_word', sa.String(50), nullable=False),
        sa.Column('undercover_word', sa.String(50), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('difficulty', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )

    # Create indexes for word_pairs table
    op.create_index('ix_word_pairs_id', 'word_pairs', ['id'])
    op.create_index('ix_word_pairs_category', 'word_pairs', ['category'])
    op.create_index('ix_word_pairs_difficulty', 'word_pairs', ['difficulty'])
    op.create_index('ix_word_pairs_category_difficulty', 'word_pairs', ['category', 'difficulty'])

    # Create rooms table
    op.create_table('rooms',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('creator_id', sa.String(36), nullable=False),
        sa.Column('max_players', sa.Integer(), nullable=False, server_default='8'),
        sa.Column('ai_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.Enum('waiting', 'starting', 'playing', 'finished', name='roomstatus'),
                 nullable=False, server_default='waiting'),
        sa.Column('settings', sa.JSON(), nullable=True),
        sa.Column('current_players', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['creator_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )

    # Create indexes for rooms table
    op.create_index('ix_rooms_id', 'rooms', ['id'])
    op.create_index('ix_rooms_creator_id', 'rooms', ['creator_id'])
    op.create_index('ix_rooms_status', 'rooms', ['status'])
    op.create_index('ix_rooms_created_at', 'rooms', ['created_at'])
    op.create_index('ix_rooms_status_created_at', 'rooms', ['status', 'created_at'])  # For room listing

    # Create games table
    op.create_table('games',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('room_id', sa.String(36), nullable=False),
        sa.Column('word_pair_id', sa.String(36), nullable=False),
        sa.Column('current_phase', sa.Enum('preparing', 'speaking', 'voting', 'result', 'finished', name='gamephase'),
                 nullable=False, server_default='preparing'),
        sa.Column('current_speaker', sa.String(36), nullable=True),
        sa.Column('round_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('players', sa.JSON(), nullable=True),
        sa.Column('eliminated_players', sa.JSON(), nullable=True),
        sa.Column('winner_role', sa.Enum('civilian', 'undercover', name='playerrole'), nullable=True),
        sa.Column('winner_players', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['word_pair_id'], ['word_pairs.id']),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )

    # Create indexes for games table
    op.create_index('ix_games_id', 'games', ['id'])
    op.create_index('ix_games_room_id', 'games', ['room_id'])
    op.create_index('ix_games_word_pair_id', 'games', ['word_pair_id'])
    op.create_index('ix_games_current_phase', 'games', ['current_phase'])
    op.create_index('ix_games_started_at', 'games', ['started_at'])
    op.create_index('ix_games_finished_at', 'games', ['finished_at'])

    # Create ai_players table
    op.create_table('ai_players',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('difficulty', sa.Enum('BEGINNER', 'NORMAL', 'EXPERT', name='aidifficulty'),
                 nullable=False, server_default='NORMAL'),
        sa.Column('personality', sa.Enum('CAUTIOUS', 'AGGRESSIVE', 'NORMAL', 'RANDOM', name='aipersonality'),
                 nullable=False, server_default='NORMAL'),
        sa.Column('model_name', sa.String(100), nullable=True),
        sa.Column('config', sa.Text(), nullable=True),
        sa.Column('games_played', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('games_won', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_speeches', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_votes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )

    op.create_index('ix_ai_players_id', 'ai_players', ['id'])
    op.create_index('ix_ai_players_name', 'ai_players', ['name'])
    op.create_index('ix_ai_players_difficulty', 'ai_players', ['difficulty'])
    op.create_index('ix_ai_players_is_active', 'ai_players', ['is_active'])

    # Create participants table (unified for human players and AI)
    op.create_table('participants',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('game_id', sa.String(36), nullable=False),
        sa.Column('player_id', sa.String(36), nullable=False),  # user.id or ai_player.id
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('is_ai', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('role', sa.Enum('civilian', 'undercover', name='playerrole'), nullable=False),
        sa.Column('word', sa.String(100), nullable=False),
        sa.Column('is_alive', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('is_ready', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )

    op.create_index('ix_participants_id', 'participants', ['id'])
    op.create_index('ix_participants_game_id', 'participants', ['game_id'])
    op.create_index('ix_participants_player_id', 'participants', ['player_id'])
    op.create_index('ix_participants_game_player', 'participants', ['game_id', 'player_id'])

    # Create speeches table (references participants)
    op.create_table('speeches',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('game_id', sa.String(36), nullable=False),
        sa.Column('participant_id', sa.String(36), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('speech_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['participant_id'], ['participants.id']),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )

    # Create indexes for speeches table
    op.create_index('ix_speeches_id', 'speeches', ['id'])
    op.create_index('ix_speeches_game_id', 'speeches', ['game_id'])
    op.create_index('ix_speeches_participant_id', 'speeches', ['participant_id'])
    op.create_index('ix_speeches_round_number', 'speeches', ['round_number'])
    op.create_index('ix_speeches_game_round', 'speeches', ['game_id', 'round_number'])
    op.create_index('ix_speeches_game_order', 'speeches', ['game_id', 'speech_order'])

    # Create votes table (references participants)
    op.create_table('votes',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('game_id', sa.String(36), nullable=False),
        sa.Column('voter_id', sa.String(36), nullable=False),
        sa.Column('target_id', sa.String(36), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['voter_id'], ['participants.id']),
        sa.ForeignKeyConstraint(['target_id'], ['participants.id']),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )

    # Create indexes for votes table
    op.create_index('ix_votes_id', 'votes', ['id'])
    op.create_index('ix_votes_game_id', 'votes', ['game_id'])
    op.create_index('ix_votes_voter_id', 'votes', ['voter_id'])
    op.create_index('ix_votes_target_id', 'votes', ['target_id'])
    op.create_index('ix_votes_round_number', 'votes', ['round_number'])
    op.create_index('ix_votes_game_round', 'votes', ['game_id', 'round_number'])

    # Create unique constraint to prevent duplicate votes in same round
    op.create_index('ix_votes_unique_vote', 'votes', ['game_id', 'voter_id', 'round_number'], unique=True)


def downgrade() -> None:
    """Drop all tables"""
    op.drop_table('votes')
    op.drop_table('speeches')
    op.drop_table('participants')
    op.drop_table('ai_players')
    op.drop_table('games')
    op.drop_table('rooms')
    op.drop_table('word_pairs')
    op.drop_table('users')
