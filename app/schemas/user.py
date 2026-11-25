from typing import Optional

from pydantic import EmailStr
from sqlmodel import SQLModel

from app.models.user import UserBase


class UserUpdate(SQLModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None


class AdminCreate(UserBase):
    pass


class GraduateCreate(UserBase):
    programme: Optional[str] = None


class UserResponse(SQLModel):
    id: int
    username: str
    email: EmailStr


class SignupRequest(SQLModel):
    username: str
    email: EmailStr
    password: str
