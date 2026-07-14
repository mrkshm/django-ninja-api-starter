from ninja import Router
from ninja.errors import HttpError
from core.authentication import JWTAuth
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
import os
from core.utils.auth_utils import get_request_user
from core.utils.utils import make_it_unique, generate_upload_filename
from core.utils.storage import generate_presigned_storage_url, upload_to_storage
from core.utils.image import resize_avatar_images
from core.utils.avatar import delete_existing_avatar
from .models import Contact
from .schemas import ContactIn, ContactOut, ContactAvatarResponse, ContactUpdate, DetailResponse
from organizations.models import Organization
from organizations.access import assert_org_view, assert_org_write
from ninja.pagination import paginate, LimitOffsetPagination
from ninja import File, UploadedFile
from django.core.files.storage import default_storage
from django.db.models import Q, Case, When, Value, IntegerField
from botocore.exceptions import ClientError
from typing import List

contacts_router = Router()

# Define allowed sort fields and their corresponding model fields
ALLOWED_SORT_FIELDS = {
    'display_name': 'display_name',
    'first_name': 'first_name',
    'last_name': 'last_name',
    'email': 'email',
    'created_at': 'created_at',
    'updated_at': 'updated_at',
}

@contacts_router.get("/", response=List[ContactOut], auth=JWTAuth())
@paginate(LimitOffsetPagination)
def list_contacts(
    request,
    search: str | None = None,
    sort_by: str = 'display_name',
    sort_order: str = 'asc'
):
    """
    List contacts with optional search and sorting.
    
    Query Parameters:
    - search: Optional search term to filter contacts
    - sort_by: Field to sort by (display_name, first_name, last_name, email, created_at, updated_at)
    - sort_order: Sort order (asc or desc)
    """
    user = get_request_user(request)
    
    # Only show contacts for orgs the user is a member of
    org_slugs = [m.organization.slug for m in user.memberships.select_related("organization").all()]
    qs = Contact.objects.select_related("organization", "creator").prefetch_related("tagged_items__tag").filter(organization__slug__in=org_slugs)
    
    # Apply search if provided
    if search:
        search_terms = search.split()
        search_query = Q()
        
        # Build a query that requires all terms to match (AND logic)
        for term in search_terms:
            term_query = (
                Q(display_name__icontains=term) |  # Highest weight
                Q(first_name__icontains=term) |    # High weight
                Q(last_name__icontains=term) |     # Medium weight
                Q(email__icontains=term) |         # Low weight
                Q(notes__icontains=term)           # Lowest weight
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
        sort_field = ALLOWED_SORT_FIELDS.get(sort_by, 'display_name')
        sort_prefix = '' if sort_order.lower() == 'asc' else '-'
        sort_field = f"{sort_prefix}{sort_field}"
        qs = qs.order_by('-match_score', sort_field)
    else:
        # If not searching, just sort by the requested field
        sort_field = ALLOWED_SORT_FIELDS.get(sort_by, 'display_name')
        if sort_order.lower() == 'desc':
            sort_field = f"-{sort_field}"
        qs = qs.order_by(sort_field)
    
    return qs

@contacts_router.get("/{slug}/", response=ContactOut, auth=JWTAuth())
def get_contact(request, slug: str):
    contact = get_object_or_404(Contact.objects.select_related("organization", "creator").prefetch_related("tagged_items__tag"), slug=slug)
    assert_org_view(get_request_user(request), contact.organization)
    return contact

@contacts_router.post("/", response=ContactOut, auth=JWTAuth())
def create_contact(request, data: ContactIn):
    user = get_request_user(request)
    
    # Get the user's organization or use specified organization
    if data.organization:
        org_slug = data.organization
        organization = get_object_or_404(Organization, slug=org_slug)
        assert_org_write(user, organization)
    else:
        # Use the user's primary organization
        user_orgs = user.memberships.select_related("organization").all()
        if not user_orgs:
            raise HttpError(400, "User has no organizations. Cannot create contact.")
        organization = user_orgs[0].organization
    
    # Compute display_name per rule
    display_name = data.display_name
    if not display_name:
        if data.first_name and data.last_name:
            display_name = f"{data.first_name} {data.last_name}".strip()
        elif data.first_name:
            display_name = data.first_name
        elif data.last_name:
            display_name = data.last_name
        else:
            display_name = "Untitled contact"
    
    contact_data = data.model_dump(exclude={"organization"})
    contact_data["display_name"] = display_name
    contact_data["organization"] = organization
    
    # Ensure slug is always generated and unique
    slug_candidate = slugify(display_name)
    contact_data["slug"] = make_it_unique(slug_candidate, Contact, "slug")
    
    contact = Contact.objects.create(
        **contact_data, creator_id=getattr(user, "id", None)
    )
    return contact

@contacts_router.put("/{slug}/", response=ContactOut, auth=JWTAuth())
def update_contact(request, slug: str, data: ContactIn):
    user = get_request_user(request)
    contact = get_object_or_404(Contact, slug=slug)
    assert_org_write(user, contact.organization)
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "organization":
            org = get_object_or_404(Organization, slug=value)
            assert_org_write(user, org)
            setattr(contact, "organization", org)
        else:
            setattr(contact, field, value)
    contact.save()
    return contact

@contacts_router.patch("/{slug}/", response=ContactOut, auth=JWTAuth())
def partial_update_contact(request, slug: str, data: ContactUpdate):
    user = get_request_user(request)
    contact = get_object_or_404(Contact, slug=slug)
    assert_org_write(user, contact.organization)
    update_fields = data.model_dump(exclude_unset=True)
    if "organization" in update_fields:
        org = get_object_or_404(Organization, slug=update_fields.pop("organization"))
        assert_org_write(user, org)
        contact.organization = org
    for field, value in update_fields.items():
        setattr(contact, field, value)
    if "display_name" in update_fields and update_fields["display_name"]:
        base_slug = slugify(update_fields["display_name"])
        contact.slug = make_it_unique(base_slug, Contact, "slug", exclude_pk=contact.pk)
    contact.save()
    return contact

@contacts_router.post("/{slug}/avatar/", response=ContactAvatarResponse, auth=JWTAuth())
def upload_contact_avatar(request, slug: str, file: UploadedFile = File(...)):
    """
    Upload and set avatar for a contact. Stores small and large sizes, updates avatar_path.
    """
    contact = get_object_or_404(Contact, slug=slug)
    assert_org_write(get_request_user(request), contact.organization)
    # File validation: max size 10MB
    MAX_SIZE = 10 * 1024 * 1024
    if (file.size or 0) > MAX_SIZE:
        raise HttpError(400, "File too large. Maximum allowed size is 10MB.")
    if not str(file.content_type or "").startswith("image/"):
        raise HttpError(400, "Invalid file type. Only images are allowed.")
    try:
        # Resize images (small, large)
        small_bytes, large_bytes = resize_avatar_images(file.read())
        # Generate unique filenames
        prefix = f"ct_{contact.slug[:8]}"
        original_name = file.name or "avatar"
        filename = generate_upload_filename(prefix, original_name, ext=".webp")
        large_filename = generate_upload_filename(prefix + "_lg", original_name, ext=".webp")
        # Upload avatars
        upload_to_storage(filename, small_bytes)
        upload_to_storage(large_filename, large_bytes)
        # Store only the filename (object key) in the DB
        avatar_path = filename
        # Enforce single avatar: delete old after successful upload
        if contact.avatar_path:
            delete_existing_avatar(contact)
        contact.avatar_path = avatar_path
        contact.save(update_fields=["avatar_path"])
        # Generate URLs for API response
        avatar_url = default_storage.url(filename)
        large_avatar_url = default_storage.url(large_filename)
        return ContactAvatarResponse(
            avatar_path=avatar_path,
            avatar_url=avatar_url,
            large_avatar_url=large_avatar_url
        )
    except Exception as e:
        raise HttpError(400, f"Failed to process avatar: {str(e)}")

@contacts_router.delete("/{slug}/avatar/", auth=JWTAuth(), response=DetailResponse)
def delete_contact_avatar(request, slug: str):
    contact = get_object_or_404(Contact, slug=slug)
    assert_org_write(get_request_user(request), contact.organization)
    if not contact.avatar_path:
        raise HttpError(404, "No avatar to delete.")
    delete_existing_avatar(contact)
    contact.avatar_path = None
    contact.save(update_fields=["avatar_path"])
    return DetailResponse(detail="Avatar deleted.")

@contacts_router.delete("/{slug}/", response=DetailResponse, auth=JWTAuth())
def delete_contact(request, slug: str):
    contact = get_object_or_404(Contact, slug=slug)
    assert_org_write(get_request_user(request), contact.organization)
    contact.delete()
    return DetailResponse(detail="Contact deleted.")

@contacts_router.get("/avatars/{path:path}", auth=JWTAuth())
def get_contact_avatar_url(request, path: str):
    """
    Generate a presigned URL for a contact's avatar image.
    For large version, append '_lg' before the file extension.
    Example: /api/v1/contacts/avatars/avatar-user123-20240529.webp
             /api/v1/contacts/avatars/avatar-user123-20240529_lg.webp
    """
    # Validate path to prevent directory traversal
    if '..' in path or path.startswith('/'):
        raise HttpError(400, "Invalid path")
    
    # Get the base filename without extension
    base, ext = os.path.splitext(path)
    
    # Check if requesting large version
    is_large = base.endswith('_lg')
    if is_large:
        base = base[:-3]  # Remove _lg suffix
    
    # Validate filename format (example: avatar-{id}-{timestamp}-{random}.webp)
    if not (base.startswith('ct_') and ext.lower() == '.webp'):
        raise HttpError(400, "Invalid avatar filename format")
    
    try:
        url = generate_presigned_storage_url(
            path,
            expires_in=3600,
            content_type="image/webp",
            cache_control="public, max-age=3600",
        )
        return {"url": url}
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "NoSuchKey":
            raise HttpError(404, "Avatar not found")
        raise HttpError(500, f"S3 error: {error_code} - {str(e)}")
    except Exception as e:
        raise HttpError(500, f"Error generating URL: {str(e)}")
