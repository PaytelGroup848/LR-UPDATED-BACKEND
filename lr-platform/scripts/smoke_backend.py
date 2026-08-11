import uuid
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core.app_factory import create_app
from backend.models.user import User
from shared.security.password import hash_password


def _delete_user(username):
    user = User.find_by_username(username)
    if user:
        User.delete(user.id)


def main():
    app = create_app()
    register_name = f"smoke_register_{uuid.uuid4().hex[:8]}"
    admin_name = f"smoke_admin_{uuid.uuid4().hex[:8]}"
    created_name = f"smoke_user_{uuid.uuid4().hex[:8]}"

    try:
        with app.test_client() as client:
            response = client.get("/health")
            print("health", response.status_code)
            assert response.status_code == 200

            response = client.post(
                "/register",
                json={"username": register_name, "password": "SmokePass123!"},
            )
            print("register", response.status_code, response.get_json().get("message"))
            assert response.status_code == 201

            response = client.post(
                "/login",
                json={"username": register_name, "password": "SmokePass123!"},
            )
            print("login", response.status_code, response.get_json().get("message"))
            assert response.status_code == 200

        admin = User.create(admin_name, hash_password("AdminPass123!"), "Admin")
        assert admin

        with app.test_client() as client:
            response = client.post(
                "/login",
                json={"username": admin_name, "password": "AdminPass123!"},
            )
            print("admin_login", response.status_code)
            assert response.status_code == 200

            response = client.post(
                "/users",
                json={
                    "username": created_name,
                    "password": "UserPass123!",
                    "role": "User",
                },
            )
            print("create_user", response.status_code, response.get_json().get("message"))
            assert response.status_code == 201

    finally:
        for username in (register_name, admin_name, created_name):
            _delete_user(username)
        print("cleanup done")


if __name__ == "__main__":
    main()
