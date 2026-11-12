"""device accounts

Accounts on this computer (file 07): user_accounts, devices, device_accounts,
pin_attempts, setup_codes. Adds tables only; existing users get no rows.
Only hashes of the computer ID, PINs and setup codes are stored.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-12 02:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('user_accounts',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=20), nullable=False),
    sa.Column('username_key', sa.String(length=20), nullable=False),
    sa.Column('mobile_number', sa.String(length=16), nullable=True),
    sa.Column('mobile_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('pin_hash', sa.String(length=255), nullable=True),
    sa.Column('pin_set_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('must_reset_pin', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('signup_source', sa.String(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id'),
    sa.UniqueConstraint('username_key', name='uq_user_accounts_username_key')
    )
    op.create_table('devices',
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('device_key_hash', sa.String(length=64), nullable=False),
    sa.Column('is_shared', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('device_id'),
    sa.UniqueConstraint('device_key_hash', name='uq_devices_device_key_hash')
    )
    op.create_table('device_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('remembered', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('remembered_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['device_id'], ['devices.device_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('device_id', 'user_id', name='uq_device_accounts_device_user')
    )
    op.create_index(op.f('ix_device_accounts_device_id'), 'device_accounts', ['device_id'], unique=False)
    op.create_index(op.f('ix_device_accounts_user_id'), 'device_accounts', ['user_id'], unique=False)
    op.create_table('pin_attempts',
    sa.Column('attempt_id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('address_hash', sa.String(length=64), nullable=True),
    sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['device_id'], ['devices.device_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('attempt_id')
    )
    op.create_index(op.f('ix_pin_attempts_device_id'), 'pin_attempts', ['device_id'], unique=False)
    op.create_index(op.f('ix_pin_attempts_user_id'), 'pin_attempts', ['user_id'], unique=False)
    op.create_index(op.f('ix_pin_attempts_attempted_at'), 'pin_attempts', ['attempted_at'], unique=False)
    op.create_table('setup_codes',
    sa.Column('code_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('code_hash', sa.String(length=255), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.user_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('code_id')
    )
    op.create_index(op.f('ix_setup_codes_user_id'), 'setup_codes', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema (drops only the five new tables)."""
    op.drop_index(op.f('ix_setup_codes_user_id'), table_name='setup_codes')
    op.drop_table('setup_codes')
    op.drop_index(op.f('ix_pin_attempts_attempted_at'), table_name='pin_attempts')
    op.drop_index(op.f('ix_pin_attempts_user_id'), table_name='pin_attempts')
    op.drop_index(op.f('ix_pin_attempts_device_id'), table_name='pin_attempts')
    op.drop_table('pin_attempts')
    op.drop_index(op.f('ix_device_accounts_user_id'), table_name='device_accounts')
    op.drop_index(op.f('ix_device_accounts_device_id'), table_name='device_accounts')
    op.drop_table('device_accounts')
    op.drop_table('devices')
    op.drop_table('user_accounts')
