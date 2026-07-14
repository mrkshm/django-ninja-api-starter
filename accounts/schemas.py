from ninja import Schema, Field
from typing import Optional
from datetime import datetime
from pydantic import ConfigDict


class UnverifiedUserSchema(Schema):
    detail: str
    email_verified: bool = False


class CustomTokenOutputSchema(Schema):
    access: str
    refresh: str
    email: str


class TokenRefreshInputSchema(Schema):
    refresh: str
    model_config = ConfigDict(extra="forbid")


class TokenRefreshOutputSchema(Schema):
    access: str
    refresh: str


class LogoutInputSchema(Schema):
    refresh: str
    model_config = ConfigDict(extra="forbid")


class TokenPairInputSchema(Schema):
    email: str
    password: str
    device_name: Optional[str] = Field(None, max_length=120)
    model_config = ConfigDict(extra="forbid")


class RegisterSchema(Schema):
    email: str
    password: str
    model_config = ConfigDict(extra="forbid")


class ChangePasswordSchema(Schema):
    old_password: str
    new_password: str
    model_config = ConfigDict(extra="forbid")


class DeleteAccountSchema(Schema):
    password: str
    model_config = ConfigDict(extra="forbid")


class EmailUpdateSchema(Schema):
    email: str
    model_config = ConfigDict(extra="forbid")


class EmailSchema(Schema):
    email: str
    model_config = ConfigDict(extra="forbid")


class TokenInputSchema(Schema):
    token: str = Field(min_length=8, max_length=128)
    model_config = ConfigDict(extra="forbid")


class PasswordResetRequestSchema(Schema):
    email: str
    model_config = ConfigDict(extra="forbid")


class PasswordResetSchema(Schema):
    token: str
    new_password: str
    model_config = ConfigDict(extra="forbid")


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
    first_name: Optional[str] = Field(None, max_length=50)
    last_name: Optional[str] = Field(None, max_length=50)
    location: Optional[str] = None
    about: Optional[str] = None
    preferred_theme: Optional[str] = None
    preferred_language: Optional[str] = None
    model_config = ConfigDict(extra="forbid")


class UsernameCheckResponse(Schema):
    available: bool
    reason: Optional[str] = None
