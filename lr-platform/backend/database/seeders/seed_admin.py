import os

from backend.extensions import db
from backend.repositories.role_repository import RoleRepository
from backend.repositories.user_repository import UserRepository
from backend.services.user_service import UserService


def seed_admin():
    user_repository = UserRepository(db)
    role_repository = RoleRepository(db)
    user_service = UserService(
        user_repository=user_repository,
        role_repository=role_repository,
    )

    username = os.getenv("LR_ADMIN_USERNAME")
    email = os.getenv("LR_ADMIN_EMAIL")
    password = os.getenv("LR_ADMIN_PASSWORD")

    if not username or not email or not password:
        raise RuntimeError(
            "Set LR_ADMIN_USERNAME, LR_ADMIN_EMAIL, and LR_ADMIN_PASSWORD "
            "before running the admin seeder."
        )

    existing_user = user_repository.get_by_username(username)
    if existing_user:
        print("Admin already exists")
        return

    user = user_service.create_user(
        username=username,
        email=email,
        password=password,
        role_name="ADMIN",
    )

    print(f"Admin created: {user.username}")


if __name__ == "__main__":
    seed_admin()
