"""create searches and search_tenders

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "searches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_by_username", sa.String(50), nullable=True),
        sa.Column("site_ids", sa.JSON(), nullable=False),
        sa.Column("site_names", sa.JSON(), nullable=False),
        sa.Column("category_ids", sa.JSON(), nullable=False),
        sa.Column("category_names", sa.JSON(), nullable=False),
        sa.Column(
            "include_uncategorised",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("sites_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sites_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tender_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_searches_user",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_searches_status",
        ),
    )
    op.create_index("ix_searches_created_at", "searches", ["created_at"])

    op.create_table(
        "search_tenders",
        sa.Column("search_id", sa.BigInteger(), nullable=False),
        sa.Column("tender_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("search_id", "tender_id"),
        sa.ForeignKeyConstraint(
            ["search_id"],
            ["searches.id"],
            name="fk_search_tenders_search",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            name="fk_search_tenders_tender",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_search_tenders_tender", "search_tenders", ["tender_id"])


def downgrade() -> None:
    op.drop_index("ix_search_tenders_tender", table_name="search_tenders")
    op.drop_table("search_tenders")
    op.drop_index("ix_searches_created_at", table_name="searches")
    op.drop_table("searches")
