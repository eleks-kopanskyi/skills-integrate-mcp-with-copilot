"""Create a pre-provisioned user account for the activities application."""

import argparse
import getpass
import json
import os
import tempfile
from pathlib import Path

from auth import ROLES, USERS_FILE, hash_password, load_users


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    parser.add_argument("email")
    parser.add_argument("role", choices=sorted(ROLES))
    args = parser.parse_args()

    username = args.username.strip()
    email = args.email.strip()
    if not username or not email:
        parser.error("Username and email must not be blank")
    users = load_users() if USERS_FILE.exists() else []
    if any(user["username"].casefold() == username.casefold() for user in users):
        parser.error(f"Username already exists: {username}")
    if any(user["email"].casefold() == email.casefold() for user in users):
        parser.error(f"Email already exists: {email}")

    password = getpass.getpass("Password (at least 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        parser.error("Passwords do not match")
    try:
        password_hash = hash_password(password)
    except ValueError as error:
        parser.error(str(error))

    users.append(
        {
            "username": username,
            "email": email,
            "role": args.role,
            "password_hash": password_hash,
        }
    )

    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=USERS_FILE.parent, delete=False
    ) as user_file:
        json.dump({"users": users}, user_file, indent=2)
        user_file.write("\n")
        temporary_path = Path(user_file.name)
    os.chmod(temporary_path, 0o600)
    temporary_path.replace(USERS_FILE)


if __name__ == "__main__":
    main()
