"""sms codes

Accounts on this computer (file 07, Phase 5): sms_codes for verifying a mobile
number at sign-up and for Forgot PIN by text. Adds one table only. Codes are
stored as Argon2 hashes; the number only as an HMAC (mobile_hash).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-13 06:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('sms_codes',
    sa.Column('code_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('device_id', sa.Integer(), nullable=True),
    sa.Column('mobile_hash', sa.String(length=64), nullable=False),
    sa.Column('purpose', sa.String(length=16), nullable=False),
    sa.Column('code_hash', sa.String(length=255), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['device_id'], ['devices.device_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('code_id')
    )
    op.create_index(op.f('ix_sms_codes_user_id'), 'sms_codes', ['user_id'], unique=False)
    op.create_index(op.f('ix_sms_codes_mobile_hash'), 'sms_codes', ['mobile_hash'], unique=False)
    op.create_index(op.f('ix_sms_codes_created_at'), 'sms_codes', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema (drops only the new table)."""
    op.drop_index(op.f('ix_sms_codes_created_at'), table_name='sms_codes')
    op.drop_index(op.f('ix_sms_codes_mobile_hash'), table_name='sms_codes')
    op.drop_index(op.f('ix_sms_codes_user_id'), table_name='sms_codes')
    op.drop_table('sms_codes')
