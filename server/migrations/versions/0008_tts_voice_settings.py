"""tts voice settings

Clearer text to speech: each user's neural voice (English and Filipino),
speed and pitch. Stored with the speech language, not in
accessibility_settings (a row there means "own accessibility settings").

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-07 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user_speech_settings', sa.Column('tts_voice_en', sa.String(length=60), nullable=True))
    op.add_column('user_speech_settings', sa.Column('tts_voice_fil', sa.String(length=60), nullable=True))
    op.add_column('user_speech_settings', sa.Column('tts_rate', sa.Integer(), nullable=True))
    op.add_column('user_speech_settings', sa.Column('tts_pitch', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('user_speech_settings') as batch:
        batch.drop_column('tts_pitch')
        batch.drop_column('tts_rate')
        batch.drop_column('tts_voice_fil')
        batch.drop_column('tts_voice_en')
