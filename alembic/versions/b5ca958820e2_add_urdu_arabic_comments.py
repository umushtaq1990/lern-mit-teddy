"""add urdu_arabic_comments table

Revision ID: b5ca958820e2
Revises: 87f9a6f9eefc
Create Date: 2026-11-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5ca958820e2'
down_revision: Union[str, Sequence[str], None] = '87f9a6f9eefc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('urdu_arabic_comments',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('lesson_id', sa.String(length=100), nullable=False),
    sa.Column('part_id', sa.String(length=100), nullable=False),
    sa.Column('comment_text', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['urdu_arabic_users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('urdu_arabic_comments')
