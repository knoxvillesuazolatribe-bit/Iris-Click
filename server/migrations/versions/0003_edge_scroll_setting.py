"""edge scroll setting

Per-user on/off for edge scroll (Phase 6 feature, Phase 7 settings page).
Existing rows get "on", the system default.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('accessibility_settings') as batch:
        batch.add_column(sa.Column('edge_scroll_enabled', sa.Boolean(), nullable=False,
                                   server_default=sa.true()))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('accessibility_settings') as batch:
        batch.drop_column('edge_scroll_enabled')
