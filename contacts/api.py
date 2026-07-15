import uuid
from typing import Annotated, List, Literal

from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404
from ninja import File, Query, Router, UploadedFile
from ninja.errors import HttpError
from ninja.pagination import LimitOffsetPagination, paginate

from contacts.services import (
    contact_response_queryset,
    create_contact_record,
    update_contact_record,
)
from contacts.throttles import contact_search_throttle
from core.authentication import JWTAuth
from core.schemas import DetailResponse
from core.utils.avatar import schedule_avatar_file_deletion
from core.utils.image import (
    InvalidImageContent,
    resize_avatar_images,
    validate_image_content,
)
from core.utils.storage import delete_from_public_storage, upload_to_public_storage
from organizations.scope import resolve_org_scope, resolve_write_org_scope

from .models import Contact
from .schemas import ContactAvatarResponse, ContactIn, ContactOut, ContactUpdate
from .validation import MAX_CONTACT_SEARCH_LENGTH, MAX_CONTACT_SEARCH_TERMS

contacts_router = Router()

# Define allowed sort fields and their corresponding model fields
ALLOWED_SORT_FIELDS = {
    "display_name": "display_name",
    "first_name": "first_name",
    "last_name": "last_name",
    "email": "email",
    "created_at": "created_at",
    "updated_at": "updated_at",
}


@contacts_router.get(
    "/orgs/{org_slug}/contacts/",
    response=List[ContactOut],
    auth=JWTAuth(),
    throttle=[contact_search_throttle],
)
@paginate(LimitOffsetPagination)
def list_contacts(
    request,
    org_slug: str,
    search: Annotated[str | None, Query(max_length=MAX_CONTACT_SEARCH_LENGTH)] = None,
    sort_by: Literal[
        "display_name",
        "first_name",
        "last_name",
        "email",
        "created_at",
        "updated_at",
    ] = "display_name",
    sort_order: Literal["asc", "desc"] = "asc",
):
    """
    List contacts with optional search and sorting.

    Query Parameters:
    - search: Optional search term to filter contacts
    - sort_by: Field to sort by (display_name, first_name, last_name, email, created_at, updated_at)
    - sort_order: Sort order (asc or desc)
    """
    scope = resolve_org_scope(request, org_slug)
    qs = contact_response_queryset().filter(organization=scope.org)

    # Apply search if provided
    if search:
        search_terms = search.split()
        if len(search_terms) > MAX_CONTACT_SEARCH_TERMS:
            raise HttpError(
                400,
                f"Search supports at most {MAX_CONTACT_SEARCH_TERMS} terms.",
            )
        search_query = Q()

        # Build a query that requires all terms to match (AND logic)
        for term in search_terms:
            term_query = (
                Q(display_name__icontains=term)  # Highest weight
                | Q(first_name__icontains=term)  # High weight
                | Q(last_name__icontains=term)  # Medium weight
                | Q(email__icontains=term)  # Low weight
                | Q(notes__icontains=term)  # Lowest weight
            )
            search_query &= term_query  # All terms must match (AND logic)

        # Annotate with match scores
        qs = qs.annotate(
            match_score=Case(
                When(display_name__icontains=search, then=Value(5)),
                When(first_name__icontains=search, then=Value(4)),
                When(last_name__icontains=search, then=Value(3)),
                When(email__icontains=search, then=Value(2)),
                When(notes__icontains=search, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        ).filter(search_query)

        # If searching, we'll sort by match score first, then by the requested field
        sort_field = ALLOWED_SORT_FIELDS[sort_by]
        sort_prefix = "" if sort_order == "asc" else "-"
        sort_field = f"{sort_prefix}{sort_field}"
        qs = qs.order_by("-match_score", sort_field)
    else:
        # If not searching, just sort by the requested field
        sort_field = ALLOWED_SORT_FIELDS[sort_by]
        if sort_order == "desc":
            sort_field = f"-{sort_field}"
        qs = qs.order_by(sort_field)

    return qs


@contacts_router.get(
    "/orgs/{org_slug}/contacts/{slug}/", response=ContactOut, auth=JWTAuth()
)
def get_contact(request, org_slug: str, slug: str):
    scope = resolve_org_scope(request, org_slug)
    contact = get_object_or_404(
        contact_response_queryset(),
        organization=scope.org,
        slug=slug,
    )
    return contact


@contacts_router.post("/orgs/{org_slug}/contacts/", response=ContactOut, auth=JWTAuth())
def create_contact(request, org_slug: str, data: ContactIn):
    scope = resolve_write_org_scope(request, org_slug)
    user = scope.user
    organization = scope.org

    return create_contact_record(organization, user, data)


@contacts_router.put(
    "/orgs/{org_slug}/contacts/{slug}/", response=ContactOut, auth=JWTAuth()
)
def update_contact(request, org_slug: str, slug: str, data: ContactIn):
    scope = resolve_write_org_scope(request, org_slug)
    contact = get_object_or_404(
        contact_response_queryset(), organization=scope.org, slug=slug
    )
    return update_contact_record(contact, data)


@contacts_router.patch(
    "/orgs/{org_slug}/contacts/{slug}/", response=ContactOut, auth=JWTAuth()
)
def partial_update_contact(request, org_slug: str, slug: str, data: ContactUpdate):
    scope = resolve_write_org_scope(request, org_slug)
    contact = get_object_or_404(
        contact_response_queryset(), organization=scope.org, slug=slug
    )
    return update_contact_record(contact, data)


@contacts_router.post(
    "/orgs/{org_slug}/contacts/{slug}/avatar/",
    response=ContactAvatarResponse,
    auth=JWTAuth(),
)
def upload_contact_avatar(
    request, org_slug: str, slug: str, file: UploadedFile = File(...)
):
    """
    Upload and set avatar for a contact. Stores small and large sizes, updates avatar_path.
    """
    scope = resolve_write_org_scope(request, org_slug)
    contact = get_object_or_404(Contact, organization=scope.org, slug=slug)
    # File validation: max size 10MB
    MAX_SIZE = 10 * 1024 * 1024
    if (file.size or 0) > MAX_SIZE:
        raise HttpError(400, "File too large. Maximum allowed size is 10MB.")
    if not str(file.content_type or "").startswith("image/"):
        raise HttpError(400, "Invalid file type. Only images are allowed.")
    try:
        data = file.read()
        validate_image_content(data)
        small_bytes, large_bytes = resize_avatar_images(data)
        token = uuid.uuid4().hex
        filename = f"public/avatars/contacts/{token}.webp"
        large_filename = f"public/avatars/contacts/{token}_lg.webp"
        old_avatar_path = contact.avatar_path
        uploaded: list[str] = []
        try:
            avatar_url = upload_to_public_storage(filename, small_bytes)
            uploaded.append(filename)
            large_avatar_url = upload_to_public_storage(large_filename, large_bytes)
            uploaded.append(large_filename)
            with transaction.atomic():
                contact.avatar_path = filename
                contact.save(update_fields=["avatar_path", "updated_at"])
                if old_avatar_path:
                    schedule_avatar_file_deletion(old_avatar_path)
        except Exception:
            for key in uploaded:
                delete_from_public_storage(key)
            raise
        return ContactAvatarResponse(
            avatar_path=filename,
            avatar_url=avatar_url,
            large_avatar_url=large_avatar_url,
        )
    except InvalidImageContent as exc:
        raise HttpError(400, str(exc)) from exc
    except Exception as exc:
        raise HttpError(503, "Avatar upload is temporarily unavailable.") from exc


@contacts_router.delete(
    "/orgs/{org_slug}/contacts/{slug}/avatar/", auth=JWTAuth(), response=DetailResponse
)
def delete_contact_avatar(request, org_slug: str, slug: str):
    scope = resolve_write_org_scope(request, org_slug)
    contact = get_object_or_404(Contact, organization=scope.org, slug=slug)
    if not contact.avatar_path:
        raise HttpError(404, "No avatar to delete.")
    old_avatar_path = contact.avatar_path
    with transaction.atomic():
        contact.avatar_path = None
        contact.save(update_fields=["avatar_path", "updated_at"])
        schedule_avatar_file_deletion(old_avatar_path)
    return DetailResponse(detail="Avatar deleted.")


@contacts_router.delete(
    "/orgs/{org_slug}/contacts/{slug}/", response=DetailResponse, auth=JWTAuth()
)
def delete_contact(request, org_slug: str, slug: str):
    scope = resolve_write_org_scope(request, org_slug)
    contact = get_object_or_404(Contact, organization=scope.org, slug=slug)
    contact.delete()
    return DetailResponse(detail="Contact deleted.")
