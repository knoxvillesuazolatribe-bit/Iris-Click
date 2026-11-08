"""approved computers

Computer lock for the website (extension): the computers a helper approved
for each assistive user. Only hashes of the approval code and the computer
key are stored.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-08 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('approved_computers',
    sa.Column('computer_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('label', sa.String(length=80), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=True),
    sa.Column('code_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('key_hash', sa.String(length=64), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('computer_id'),
    sa.UniqueConstraint('code_hash', name='uq_approved_computers_code_hash')
    )
    op.create_index(op.f('ix_approved_computers_user_id'), 'approved_computers', ['user_id'], unique=False)
    op.create_index(op.f('ix_approved_computers_key_hash'), 'approved_computers', ['key_hash'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_approved_computers_key_hash'), table_name='approved_computers')
    op.drop_index(op.f('ix_approved_computers_user_id'), table_name='approved_computers')
    op.drop_table('approved_computers')
