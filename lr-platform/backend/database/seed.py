from backend.database.seeders.role_seeder import seed_roles


def run_seed():
    seed_roles()
    print("Roles Seeded Successfully")


if __name__ == "__main__":
    run_seed()
