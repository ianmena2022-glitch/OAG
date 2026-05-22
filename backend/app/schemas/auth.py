from pydantic import BaseModel, EmailStr
from ..models.user import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    nombre: str
    role: UserRole


class UserCreate(BaseModel):
    email: EmailStr
    nombre: str
    password: str
    role: UserRole = UserRole.AUDITOR


class UserResponse(BaseModel):
    id: int
    email: str
    nombre: str
    role: UserRole
    is_active: bool

    class Config:
        from_attributes = True


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
