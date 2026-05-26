from ninja import Schema, Field
from typing import Optional
from datetime import datetime


class UnverifiedUserSchema(Schema):
    detail: str
    email_verified: bool = False


class CustomTokenOutputSchema(Schema):
    access: str
    refresh: str
    email: str


class TokenPairInputSchema(Schema):
    email: str
    password: str


class RegisterSchema(Schema):
    email: str
    password: str


class ChangePasswordSchema(Schema):
    old_password: str
    new_password: str


class EmailUpdateSchema(Schema):
    email: str


class EmailSchema(Schema):
    email: str


class PasswordResetRequestSchema(Schema):
    email: str


class PasswordResetSchema(Schema):
    token: str
    new_password: str


class UserProfileOut(Schema):
    id: int
    email: str
    first_name: str = Field(..., max_length=50)
    last_name: str = Field(..., max_length=50)
    username: str = Field(..., max_length=50)
    slug: str
    org_name: str
    org_slug: str
    location: Optional[str]
    about: Optional[str]
    avatar_path: Optional[str]
    notification_preferences: Optional[dict]
    preferred_theme: str
    preferred_language: str
    finished_onboarding: bool
    email_verified: bool
    created_at: Optional[datetime]

class UserProfileUpdate(Schema):
    first_name: str = Field(None, max_length=50)
    last_name: str = Field(None, max_length=50)
    location: Optional[str] = None
    about: Optional[str] = None
    preferred_theme: Optional[str] = None
    preferred_language: Optional[str] = None
    model_config = {
        "extra": "forbid"
    }

class UsernameCheckResponse(Schema):
    available: bool
    reason: Optional[str] = None
