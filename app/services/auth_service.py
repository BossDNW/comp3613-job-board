from typing import Optional

from app.repositories.user import UserRepository
from app.schemas.user import GraduateCreate
from app.utilities.security import (
    encrypt_password,
    verify_password,
    create_access_token,
)


class AuthService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def authenticate_user(
        self,
        username: str,
        password: str,
    ) -> Optional[str]:
        user = self.user_repo.get_by_username(username)

        if not user or not verify_password(
            plaintext_password=password,
            encrypted_password=user.password,
        ):
            return None

        return create_access_token(data={"sub": str(user.id)})

    def register_user(
        self,
        username: str,
        email: str,
        password: str,
        programme: Optional[str] = None,
    ):
        username = username.strip()
        email = email.strip().lower()

        if len(username) < 3 or len(username) > 50:
            raise ValueError("Username must contain 3 to 50 characters")

        if not password:
            raise ValueError("Password is required")

        if programme not in {None, "DCIT", "OTHER"}:
            raise ValueError("Invalid programme selected")

        if self.user_repo.get_by_username(username) is not None:
            raise ValueError("Username is already registered")

        if self.user_repo.get_by_email(email) is not None:
            raise ValueError("Email is already registered")

        new_user = GraduateCreate(
            username=username,
            email=email,
            password=encrypt_password(password),
            programme=programme,
        )

        return self.user_repo.create(new_user)
