from backend.models.role import Role


class RoleRepository:
    def __init__(self, db):
        self.db = db
        Role.ensure_defaults()

    def get_by_name(self, name: str):
        return Role.get_by_name(name)

    def get_by_id(self, role_id: int):
        return Role.get_by_id(role_id)

    def get_all(self):
        return Role.get_all()
