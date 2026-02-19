"""add symbol metadata

Revision ID: f1c7fcad138b
Revises: 6402c298d289
Create Date: 2026-02-15 04:28:30.920474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1c7fcad138b'
down_revision: Union[str, Sequence[str], None] = '6402c298d289'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
