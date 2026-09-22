"""create per-site scrape schedules

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("site_id", sa.BigInteger(), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=True),
        sa.Column("run_at", sa.Time(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(20), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"],
                                name="fk_schedules_site", ondelete="CASCADE"),
        # One schedule per site: two schedules for the same site would race
        # each other and scrape it twice.
        sa.UniqueConstraint("site_id", name="uq_schedules_site"),
        sa.CheckConstraint(
            "frequency IN ('daily', 'weekly', 'biweekly', 'monthly', 'custom')",
            name="ck_schedules_frequency",
        ),
    )
    op.create_index("ix_schedules_next_run_at", "schedules", ["next_run_at"])


def downgrade() -> None:
    op.drop_index("ix_schedules_next_run_at", table_name="schedules")
    op.drop_table("schedules")
