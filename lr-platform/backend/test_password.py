import os

from shared.security.password import hash_password, verify_password


password = os.getenv("LR_PASSWORD_TEST_VALUE")
if not password:
    raise RuntimeError("Set LR_PASSWORD_TEST_VALUE before running this smoke test.")

hashed = hash_password(password)
assert verify_password(password, hashed)
print("Password hashing smoke test passed.")
