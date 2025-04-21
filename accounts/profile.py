from ninja import Router
from ninja.errors import HttpError
from ninja_jwt.authentication import JWTAuth
from .schemas import UserProfileOut, UserProfileUpdate
from django.contrib.auth import get_user_model

router = Router()
User = get_user_model()

@router.get("/me", response=UserProfileOut, auth=JWTAuth())
def get_me(request):
    user = request.auth
    if user is None or not user.is_authenticated:
        raise HttpError(401, "Authentication required")
    return user

@router.patch("/me", response=UserProfileOut, auth=JWTAuth())
def update_me(request, data: UserProfileUpdate):
    user = request.auth
    if user is None or not user.is_authenticated:
        raise HttpError(401, "Authentication required")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(user, field, value)
    user.save()
    return user
