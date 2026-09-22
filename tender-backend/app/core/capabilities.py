"""What a user is allowed to do.

Permissions are a set of capabilities held per account rather than a single
role, so an account can be given exactly what it needs: search only, search
and save, manage the site list, manage users, or any combination.

There is no self-registration. The first admin is created by
`scripts/seed_admin.py` when the application is first set up, and every other
account is created by someone holding MANAGE_USERS.
"""

SEARCH_TENDERS = "search_tenders"
SAVE_LISTS = "save_lists"
TRIAGE_TENDERS = "triage_tenders"
MANAGE_SITES = "manage_sites"
MANAGE_CATEGORIES = "manage_categories"
MANAGE_SCHEDULES = "manage_schedules"
MANAGE_USERS = "manage_users"
RUN_ADMIN_TASKS = "run_admin_tasks"

# Order matters: this is the order the capabilities are shown in the UI.
ALL_CAPABILITIES: tuple[str, ...] = (
    SEARCH_TENDERS,
    SAVE_LISTS,
    TRIAGE_TENDERS,
    MANAGE_SITES,
    MANAGE_CATEGORIES,
    MANAGE_SCHEDULES,
    MANAGE_USERS,
    RUN_ADMIN_TASKS,
)

# Shown next to each toggle when an admin creates or edits a user.
DESCRIPTIONS: dict[str, str] = {
    SEARCH_TENDERS: "Run searches across the tender sites",
    SAVE_LISTS: "Save search results as a list",
    TRIAGE_TENDERS: "Mark tenders as not interested, and restore them",
    MANAGE_SITES: "Add, edit and pause the sites that get scraped",
    MANAGE_CATEGORIES: "Add and edit categories and their keywords",
    MANAGE_SCHEDULES: "Create and change scheduled scrapes",
    MANAGE_USERS: "Create user accounts and set what they can do",
    RUN_ADMIN_TASKS: "Re-run classification and start scrapes manually",
}


def clean(values) -> list[str]:
    """Keep only recognised capabilities, de-duplicated and in a fixed order.

    Anything unknown is dropped rather than rejected, so a capability removed
    in a later version does not break existing accounts.
    """
    held = set(values or [])
    return [c for c in ALL_CAPABILITIES if c in held]


def is_admin(user) -> bool:
    """True for accounts that can manage other users."""
    return MANAGE_USERS in (user.capabilities or [])
