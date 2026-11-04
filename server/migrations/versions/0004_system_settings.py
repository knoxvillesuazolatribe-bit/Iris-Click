"""system settings

One row of computer-wide settings edited by the admin (Phase 8): app name and
global accessibility defaults. NULL means "use server/.env".

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-05 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('system_settings',
    sa.Column('setting_id', sa.Integer(), nullable=False),
    sa.Column('app_name', sa.String(length=60), nullable=True),
    sa.Column('dwell_enabled', sa.Boolean(), nullable=True),
    sa.Column('dwell_ms', sa.Integer(), nullable=True),
    sa.Column('cursor_smoothing', sa.Float(), nullable=True),
    sa.Column('blink_to_click', sa.Boolean(), nullable=True),
    sa.Column('blink_sensitivity', sa.Float(), nullable=True),
    sa.Column('edge_scroll_enabled', sa.Boolean(), nullable=True),
    sa.Column('voice_volume', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('setting_id = 1', name='ck_system_settings_singleton'),
    sa.CheckConstraint('dwell_ms IS NULL OR dwell_ms BETWEEN 400 AND 1500', name='ck_system_settings_dwell_ms'),
    sa.CheckConstraint('voice_volume IS NULL OR voice_volume BETWEEN 0 AND 100', name='ck_system_settings_voice_volume'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('setting_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('system_settings')
