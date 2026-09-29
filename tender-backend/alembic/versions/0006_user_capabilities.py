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
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="[]"),
    )
    # Carry existing accounts over: admins keep everything, everyone else gets
    # the day-to-day permissions they already had in practice.
    op.execute(f"UPDATE users SET capabilities = '{ADMIN_CAPABILITIES}' WHERE role = 'admin'")
    op.execute(f"UPDATE users SET capabilities = '{USER_CAPABILITIES}' WHERE role = 'user'")

    op.drop_column("users", "role")
    op.execute("DROP TYPE IF EXISTS user_role")


def downgrade() -> None:
    user_role = sa.Enum("admin", "user", name="user_role")
    user_role.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column("role", user_role, nullable=False, server_default="user"),
    )
    op.execute(
        "UPDATE users SET role = 'admin' "
        "WHERE capabilities::text LIKE '%manage_users%'"
    )
    op.drop_column("users", "capabilities")
