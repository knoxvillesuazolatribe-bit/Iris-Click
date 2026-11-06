"""word filter

Word filter for Voice Communication (extension): the blocked/allowed word
list, its settings row, and communication_history.was_filtered.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-06 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('filtered_words',
    sa.Column('word_id', sa.Integer(), nullable=False),
    sa.Column('word', sa.String(length=100), nullable=False),
    sa.Column('normalized_word', sa.String(length=100), nullable=False),
    sa.Column('language', sa.String(length=10), nullable=False),
    sa.Column('type', sa.String(length=10), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("language IN ('en', 'fil', 'other')", name='ck_filtered_words_language'),
    sa.CheckConstraint("type IN ('blocked', 'allowed')", name='ck_filtered_words_type'),
    sa.ForeignKeyConstraint(['created_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('word_id'),
    sa.UniqueConstraint('normalized_word')
    )
    op.create_table('word_filter_settings',
    sa.Column('setting_id', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('tts_mode', sa.String(length=10), nullable=False),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('setting_id = 1', name='ck_word_filter_settings_singleton'),
    sa.CheckConstraint("tts_mode IN ('beep', 'skip')", name='ck_word_filter_settings_tts_mode'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('setting_id')
    )
    op.add_column('communication_history',
                  sa.Column('was_filtered', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('communication_history') as batch:
        batch.drop_column('was_filtered')
    op.drop_table('word_filter_settings')
    op.drop_table('filtered_words')
