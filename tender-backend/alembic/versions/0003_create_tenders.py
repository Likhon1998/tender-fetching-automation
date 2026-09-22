"""create tenders table

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("date_raw", sa.Text(), nullable=True),
        sa.Column("pdf_link", sa.Text(), nullable=True),
        sa.Column("site_id", sa.BigInteger(), nullable=True),
        sa.Column("source_name", sa.String(120), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("category_id", sa.BigInteger(), nullable=True),
        sa.Column("category", sa.String(120), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="new"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["site_id"], ["sites.id"], name="fk_tenders_site", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"],
            name="fk_tenders_category", ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'not_interested')", name="ck_tenders_status"
        ),
        sa.UniqueConstraint("title", name="uq_tenders_title"),
    )

    op.create_index("ix_tenders_site_id", "tenders", ["site_id"])
    op.create_index("ix_tenders_category_id", "tenders", ["category_id"])
    op.create_index("ix_tenders_status", "tenders", ["status"])
    op.create_index("ix_tenders_date", "tenders", ["date"])


def downgrade() -> None:
    op.drop_index("ix_tenders_date", table_name="tenders")
    op.drop_index("ix_tenders_status", table_name="tenders")
    op.drop_index("ix_tenders_category_id", table_name="tenders")
    op.drop_index("ix_tenders_site_id", table_name="tenders")
    op.drop_table("tenders")
