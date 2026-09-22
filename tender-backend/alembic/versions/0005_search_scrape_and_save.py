"""add scrape progress and saved flag to searches

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("searches", sa.Column("current_site", sa.String(120), nullable=True))
    op.add_column(
        "searches",
        sa.Column("saved", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "searches", sa.Column("saved_at", sa.DateTime(), nullable=True)
    )
    op.execute("UPDATE searches SET saved = 1 WHERE tender_count > 0")
    op.create_index("ix_searches_saved", "searches", ["saved"])


def downgrade() -> None:
    op.drop_index("ix_searches_saved", table_name="searches")
    op.drop_column("searches", "saved_at")
    op.drop_column("searches", "saved")
    op.drop_column("searches", "current_site")
