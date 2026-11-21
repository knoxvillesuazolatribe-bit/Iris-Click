"""user city

Emergency SOS sends "address, barangay, city". The city was always
"Lapu-Lapu City"; people in Mandaue, Cebu City or Cordova got the wrong city.
Adds one nullable column: users.city (NULL = Lapu-Lapu City, the default).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-21 19:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('city', sa.String(length=60), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users') as batch:
        batch.drop_column('city')
