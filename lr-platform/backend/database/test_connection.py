from backend.extensions import client


try:
    client.admin.command("ping")
    print("MongoDB connection SUCCESS")
except Exception as e:
    print(f"MongoDB connection ERROR: {e}")
