"""label tender dates and record submission deadlines

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenders",
        sa.Column("date_type", sa.String(20), nullable=False, server_default="publish"),
    )
    op.add_column("tenders", sa.Column("submission_date", sa.Date(), nullable=True))
    op.add_column(
        "tenders", sa.Column("submission_date_raw", sa.Text(), nullable=True)
    )
    op.create_index("ix_tenders_submission_date", "tenders", ["submission_date"])
    op.create_check_constraint(
        "ck_tenders_date_type", "tenders", "date_type IN ('publish', 'submission')"
    )

    op.execute(
        "UPDATE tenders SET date_type = 'submission', submission_date = date "
        "WHERE source_name = 'CityBank' AND date IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_constraint("ck_tenders_date_type", "tenders", type_="check")
    op.drop_index("ix_tenders_submission_date", table_name="tenders")
    op.drop_column("tenders", "submission_date_raw")
    op.drop_column("tenders", "submission_date")
    op.drop_column("tenders", "date_type")
