"""speech language

English/Filipino speech (extension): each user's speech language, and the
language of each Voice Communication message.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-06 19:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('user_speech_settings',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('language', sa.String(length=5), nullable=False),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("language IN ('en', 'fil')", name='ck_user_speech_settings_language'),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.add_column('communication_history', sa.Column('language', sa.String(length=5), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('communication_history') as batch:
        batch.drop_column('language')
    op.drop_table('user_speech_settings')
