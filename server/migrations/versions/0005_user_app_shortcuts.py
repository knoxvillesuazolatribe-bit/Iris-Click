"""user app shortcuts

Per-user Apps tiles on the Home Suite (extension): the six Phase 9 apps as
defaults, plus installed apps and websites the user adds.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('user_app_shortcuts',
    sa.Column('shortcut_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('label', sa.String(length=60), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('builtin_key', sa.String(length=20), nullable=True),
    sa.Column('target', sa.String(length=2048), nullable=True),
    sa.Column('icon', sa.String(length=30), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('is_visible', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("type IN ('builtin', 'installed_app', 'website')", name='ck_user_app_shortcuts_type'),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('shortcut_id'),
    sa.UniqueConstraint('user_id', 'builtin_key', name='uq_user_app_shortcuts_builtin'),
    sa.UniqueConstraint('user_id', 'target', name='uq_user_app_shortcuts_target')
    )
    op.create_index(op.f('ix_user_app_shortcuts_user_id'), 'user_app_shortcuts', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_user_app_shortcuts_user_id'), table_name='user_app_shortcuts')
    op.drop_table('user_app_shortcuts')
