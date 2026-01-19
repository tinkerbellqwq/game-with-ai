"""add_password_to_room

Revision ID: 2cf787761c1d
Revises: 002
Create Date: 2026-01-19 12:35:03.363394

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2cf787761c1d'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 添加房间密码字段
    op.add_column('rooms', sa.Column('password', sa.String(length=50), nullable=True))


def downgrade() -> None:
    # 移除房间密码字段
    op.drop_column('rooms', 'password')
