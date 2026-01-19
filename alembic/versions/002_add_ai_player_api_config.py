"""Add API configuration fields to ai_players table

Revision ID: 002
Revises: 001
Create Date: 2026-01-15

This migration adds per-AI API configuration fields:
- api_base_url: Custom API endpoint URL
- api_key: API authentication key
"""
from alembic import op
import sqlalchemy as sa
import os

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add api_base_url and api_key columns to ai_players table"""

    # Add api_base_url column
    op.add_column('ai_players',
        sa.Column('api_base_url', sa.String(500), nullable=True)
    )

    # Add api_key column
    op.add_column('ai_players',
        sa.Column('api_key', sa.String(500), nullable=True)
    )

    # Apply current global config to all existing AI players
    # Get values from environment variables
    openai_api_key = os.environ.get('OPENAI_API_KEY', '')
    openai_base_url = os.environ.get('OPENAI_BASE_URL', '')

    if openai_api_key:
        # Update all existing AI players with the global config
        op.execute(
            f"""
            UPDATE ai_players
            SET api_key = '{openai_api_key}',
                api_base_url = '{openai_base_url}'
            WHERE api_key IS NULL
            """
        )


def downgrade() -> None:
    """Remove api_base_url and api_key columns from ai_players table"""
    op.drop_column('ai_players', 'api_key')
    op.drop_column('ai_players', 'api_base_url')
