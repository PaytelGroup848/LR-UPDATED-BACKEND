from backend.extensions import db
from backend.models.role import Role
from backend.models.user import User


ADMIN_ROLE_KEYS = {
    "ADMIN",
    "SUPER_ADMIN",
    "SUPERADMIN",
}


def canonical_user_role(value):
    key = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    return "Admin" if key in ADMIN_ROLE_KEYS else "User"


def migrate_two_roles(database=None):
    if database is None:
        database = db
    users = database["users"]
    roles = database["roles"]

    roles.delete_many({})
    roles.insert_many([dict(role) for role in Role.DEFAULT_ROLES])

    updated_admins = 0
    updated_users = 0
    for user in users.find({}, {"role": 1}):
        canonical_role = canonical_user_role(user.get("role"))
        role_id = 1 if canonical_role == "Admin" else 4
        users.update_one(
            {"_id": user["_id"]},
            {"$set": {"role": canonical_role, "role_id": role_id}},
        )
        if canonical_role == "Admin":
            updated_admins += 1
        else:
            updated_users += 1

    return {
        "roles": [role["name"] for role in Role.DEFAULT_ROLES],
        "admins": updated_admins,
        "users": updated_users,
    }


if __name__ == "__main__":
    print(migrate_two_roles())
