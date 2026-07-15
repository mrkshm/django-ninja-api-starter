import secrets
from datetime import timedelta

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja.errors import HttpError

from core.authentication import JWTAuth
from images.api.common import router
from images.models import Image, ImageShareLink, hash_share_token
from images.schemas import (
    CreateImageShareIn,
    DetailResponse,
    ImageShareOut,
    ImageSignedUrlsOut,
    ResolveImageShareIn,
)
from images.services import sign_image_variant_urls
from images.throttles import share_link_throttle
from organizations.scope import resolve_org_scope


def serialize_share_link(share_link: ImageShareLink, raw_token: str) -> ImageShareOut:
    return ImageShareOut(
        id=share_link.id,
        token=raw_token,
        image_id=share_link.image_id,
        created_at=share_link.created_at.isoformat(),
        expires_at=share_link.expires_at.isoformat() if share_link.expires_at else None,
        revoked_at=share_link.revoked_at.isoformat() if share_link.revoked_at else None,
    )


@router.get(
    "/orgs/{org_slug}/images/{image_id}/urls",
    response=ImageSignedUrlsOut,
    auth=JWTAuth(),
)
def get_image_signed_urls(request, org_slug: str, image_id: int):
    scope = resolve_org_scope(request, org_slug)
    image = get_object_or_404(Image, id=image_id, organization=scope.org)
    return sign_image_variant_urls(image)


@router.post(
    "/orgs/{org_slug}/images/{image_id}/shares", response=ImageShareOut, auth=JWTAuth()
)
def create_image_share(request, org_slug: str, image_id: int, data: CreateImageShareIn):
    scope = resolve_org_scope(request, org_slug).require_write()
    org = scope.org
    user = scope.user
    image = get_object_or_404(Image, id=image_id, organization=org)
    default_ttl = int(
        getattr(settings, "IMAGE_SHARE_LINK_DEFAULT_TTL_SECONDS", 60 * 60 * 24 * 7)
    )
    ttl = (
        data.expires_in_seconds if data.expires_in_seconds is not None else default_ttl
    )
    raw_token = secrets.token_urlsafe(32)
    share_link = ImageShareLink.objects.create(
        image=image,
        token_hash=hash_share_token(raw_token),
        created_by=user,
        expires_at=timezone.now() + timedelta(seconds=ttl) if ttl else None,
    )
    return serialize_share_link(share_link, raw_token)


@router.delete(
    "/orgs/{org_slug}/images/{image_id}/shares/{share_id}",
    response={200: DetailResponse},
    auth=JWTAuth(),
)
def revoke_image_share(request, org_slug: str, image_id: int, share_id: int):
    scope = resolve_org_scope(request, org_slug).require_write()
    image = get_object_or_404(Image, id=image_id, organization=scope.org)
    share_link = get_object_or_404(ImageShareLink, id=share_id, image=image)
    share_link.revoke()
    return DetailResponse(detail="ok")


@router.post(
    "/shared/images/resolve/",
    response=ImageSignedUrlsOut,
    auth=None,
    throttle=[share_link_throttle],
)
def get_shared_image_signed_urls(request, data: ResolveImageShareIn):
    share_link = get_object_or_404(
        ImageShareLink.objects.select_related("image"),
        token_hash=hash_share_token(data.token),
    )
    if not share_link.is_active():
        raise HttpError(404, "Share link not found")
    return sign_image_variant_urls(share_link.image)
