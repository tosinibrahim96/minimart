import sys

from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.auth.exceptions import UserAlreadyExistsError
from app.auth.models import User
from app.auth.repository import UserRepository
from app.auth.schemas import UserCreate
from app.auth.service import AuthService
from app.core.config import settings
from app.core.database import engine


def main() -> None:
    print("Creating admin user...")
    try:
        email = settings.admin_email
        password = settings.admin_password

        if email is None or password is None:
            print(
                "Admin email or password is not set. Please set the ADMIN_EMAIL and ADMIN_PASSWORD environment variables."
            )
            sys.exit(1)
        with Session(engine) as db:
            user_repository = UserRepository(db)
            auth_service = AuthService(db, user_repository, PasswordHash.recommended())
            admin = auth_service.create_account(
                UserCreate(email=email, password=password)
            )
            print(f"Admin user created: {admin.email}")

            auth_service.update_user_is_admin(admin.id, True)
            print("User has been updated to admin")
            sys.exit(0)
    except UserAlreadyExistsError:
        if email is None:
            print(
                "Admin email is not set. Please set the ADMIN_EMAIL environment variable."
            )
            sys.exit(1)
        print(f"User '{email}' already exists. Checking administrative privileges...")

        with Session(engine) as db:
            user_repository = UserRepository(db)
            auth_service = AuthService(db, user_repository, PasswordHash.recommended())
            user: User | None = user_repository.get_user_by_email(email)
            if user and user.is_admin:
                print(f"Success: '{email}' is already a registered admin.")
                sys.exit(0)
            elif user:
                print(
                    f"User '{email}' exists but is NOT an admin. Upgrading permissions..."
                )
                auth_service.update_user_is_admin(user.id, True)
                print("User has been updated to admin")
                sys.exit(0)
            elif user is None:
                print(f"User '{email}' does not exist.")
                sys.exit(1)
    except Exception as e:
        print(f"Error creating admin user: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
