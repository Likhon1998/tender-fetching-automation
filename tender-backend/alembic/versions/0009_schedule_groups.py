"""replace per-site schedules with schedule groups

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_schedules_next_run_at", table_name="schedules")
    op.drop_table("schedules")

    op.create_table(
        "schedule_groups",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(80), nullable=True),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=True),
        sa.Column("run_at", sa.Time(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_status", sa.String(20), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "frequency IN ('daily', 'weekly', 'biweekly', 'monthly', 'custom')",
            name="ck_schedule_groups_frequency",
        ),
    )
    op.create_index("ix_schedule_groups_next_run_at", "schedule_groups", ["next_run_at"])

    op.create_table(
        "schedule_group_sites",
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("group_id", "site_id"),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["schedule_groups.id"],
            name="fk_group_sites_group",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"], ["sites.id"], name="fk_group_sites_site", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("site_id", name="uq_group_sites_site"),
    )

    op.execute(
        "UPDATE users "
        "SET capabilities = JSON_ARRAY_APPEND(capabilities, '$', 'manage_schedules') "
        "WHERE JSON_CONTAINS(capabilities, '\"manage_sites\"') "
        "AND NOT JSON_CONTAINS(capabilities, '\"manage_schedules\"')"
    )


def downgrade() -> None:
    op.drop_table("schedule_group_sites")
    op.drop_index("ix_schedule_groups_next_run_at", table_name="schedule_groups")
    op.drop_table("schedule_groups")

    op.create_table(
        "schedules",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("site_id", sa.BigInteger(), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=True),
        sa.Column("run_at", sa.Time(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_status", sa.String(20), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("site_id", name="uq_schedules_site"),
    )
    op.create_index("ix_schedules_next_run_at", "schedules", ["next_run_at"])
