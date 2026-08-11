from backend.models.role import Role


DEFAULT_ROLES = Role.DEFAULT_ROLES


def seed_roles(db=None):
    Role.ensure_defaults()
