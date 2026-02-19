"""recreate bars table

Revision ID: 6402c298d289
Revises: 414ac7be9652
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "6402c298d289"
down_revision = "414ac7be9652"
branch_labels = None
depends_on = None


def upgrade():
    # 414ac7be9652 already created "bars".
    # This migration is meant to recreate it, so drop it first.
    op.execute("DROP TABLE IF EXISTS bars CASCADE;")

    op.create_table(
        "bars",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("symbol_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),

        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),

        sa.Column("volume", sa.BigInteger(), nullable=True),

        sa.Column(
            "provider",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'massive'"),
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("symbol_id", "timeframe", "ts", name="uq_bars_symbol_tf_ts"),
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS bars CASCADE;")
