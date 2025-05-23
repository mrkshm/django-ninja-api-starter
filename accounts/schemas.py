from ninja import Schema, Field
from typing import Optional
from datetime import datetime

class UserProfileOut(Schema):
    id: int
    email: str
    first_name: str = Field(..., max_length=50)
    last_name: str = Field(..., max_length=50)
    username: str = Field(..., max_length=50)
    location: Optional[str]
    about: Optional[str]
    avatar_path: Optional[str]
    notification_preferences: Optional[dict]
    created_at: Optional[datetime]

class UserProfileUpdate(Schema):
    first_name: str = Field(None, max_length=50)
    last_name: str = Field(None, max_length=50)
    location: Optional[str] = None
    about: Optional[str] = None
    model_config = {
        "extra": "forbid"
    }

class UsernameCheckResponse(Schema):
    available: bool
    reason: Optional[str] = None
