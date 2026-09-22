"""replace user roles with capabilities

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

ADMIN_CAPABILITIES = (
    '["search_tenders","save_lists","triage_tenders","manage_sites",'
    '"manage_categories","manage_users","run_admin_tasks"]'
)
USER_CAPABILITIES = '["search_tenders","save_lists","triage_tenders"]'


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("capabilities", sa.JSON(), nullable=True),
    )
    # MariaDB accepts a JSON string literal directly (no CAST(... AS JSON)).
    op.execute(
        f"UPDATE users SET capabilities = '{ADMIN_CAPABILITIES}' WHERE role = 'admin'"
    )
    op.execute(
        f"UPDATE users SET capabilities = '{USER_CAPABILITIES}' WHERE role = 'user'"
    )
    op.execute(
        f"UPDATE users SET capabilities = '{USER_CAPABILITIES}' "
        "WHERE capabilities IS NULL"
    )
    op.alter_column("users", "capabilities", existing_type=sa.JSON(), nullable=False)
    op.drop_column("users", "role")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
    )
    op.execute(
        "UPDATE users SET role = 'admin' "
        "WHERE JSON_CONTAINS(capabilities, '\"manage_users\"')"
    )
    op.drop_column("users", "capabilities")
