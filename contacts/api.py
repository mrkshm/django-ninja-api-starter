from ninja import Router, Schema
from ninja.errors import HttpError
from ninja_jwt.authentication import JWTAuth
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from core.utils.utils import make_it_unique, generate_upload_filename
from core.utils.storage import upload_to_storage
from core.utils.image import resize_avatar_images
from core.utils.avatar import delete_existing_avatar
from core.utils.auth_utils import check_contact_member
from .models import Contact
from .schemas import ContactIn, ContactOut, ContactAvatarResponse, DetailResponse
from organizations.models import Organization
from organizations.permissions import is_member
from ninja.pagination import paginate, LimitOffsetPagination, PaginationBase
from ninja import File, UploadedFile
from django.core.files.storage import default_storage
from django.db.models import Q, Case, When, Value, IntegerField
from typing import Any, List, Optional, Dict
from django.http import HttpRequest

contacts_router = Router()

# Custom pagination class with next/prev page info
class EnhancedLimitOffsetPagination(LimitOffsetPagination):
    def get_paginated_response(self, request: HttpRequest, data: List, count: int, limit: int, offset: int) -> Dict[str, Any]:
        # Calculate next and previous offsets
        next_offset = offset + limit if offset + limit < count else None
        prev_offset = offset - limit if offset - limit >= 0 else None
        
        # Build the response with pagination info
        response = {
            "items": data,
            "count": count,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "hasNext": next_offset is not None,
                "hasPrevious": prev_offset is not None,
            }
        }
        
        # Add next and previous page URLs if they exist
        if next_offset is not None:
            response["pagination"]["next"] = f"?limit={limit}&offset={next_offset}"
        
        if prev_offset is not None:
            response["pagination"]["previous"] = f"?limit={limit}&offset={prev_offset}"
        
        return response

class ContactUpdate(Schema):
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    organization: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None

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
    search: str = None,
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
    user = getattr(request, "auth", request.user)
    
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
    check_contact_member(getattr(request, "auth", request.user), contact.organization)
    return contact

@contacts_router.post("/", response=ContactOut, auth=JWTAuth())
def create_contact(request, data: ContactIn):
    user = request.user
    
    # Get the user's organization or use specified organization
    if data.organization:
        org_slug = data.organization
        organization = get_object_or_404(Organization, slug=org_slug)
        check_contact_member(user, organization)
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
            display_name = None
    
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
    contact = get_object_or_404(Contact, slug=slug)
    check_contact_member(getattr(request, "auth", request.user), contact.organization)
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "organization":
            org = get_object_or_404(Organization, slug=value)
            setattr(contact, "organization", org)
        else:
            setattr(contact, field, value)
    contact.save()
    return contact

@contacts_router.patch("/{slug}/", response=ContactOut, auth=JWTAuth())
def partial_update_contact(request, slug: str, data: ContactUpdate):
    contact = get_object_or_404(Contact, slug=slug)
    check_contact_member(request.user, contact.organization)
    update_fields = data.model_dump(exclude_unset=True)
    if "organization" in update_fields:
        org = get_object_or_404(Organization, slug=update_fields.pop("organization"))
        contact.organization = org
    for field, value in update_fields.items():
        setattr(contact, field, value)
    if "display_name" in update_fields and update_fields["display_name"]:
        base_slug = slugify(update_fields["display_name"])
        contact.slug = make_it_unique(base_slug, Contact, "slug", exclude_pk=contact.pk)
    contact.save()
    return contact

@contacts_router.post("/{slug}/avatar/", response={200: ContactAvatarResponse, 400: DetailResponse}, auth=JWTAuth())
def upload_contact_avatar(request, slug: str, file: UploadedFile = File(...)):
    """
    Upload and set avatar for a contact. Stores small and large sizes, updates avatar_path.
    """
    print('FILES:', request.FILES)
    print('DATA:', request.POST)
    print('FILE ARG:', file)
    contact = get_object_or_404(Contact, slug=slug)
    check_contact_member(request.user, contact.organization)
    # File validation: max size 10MB
    MAX_SIZE = 10 * 1024 * 1024
    if file.size > MAX_SIZE:
        return 400, DetailResponse(detail="File too large. Maximum allowed size is 10MB.")
    if not file.content_type.startswith("image/"):
        return 400, DetailResponse(detail="Invalid file type. Only images are allowed.")
    try:
        # Resize images (small, large)
        small_bytes, large_bytes = resize_avatar_images(file.read())
        # Generate unique filenames
        prefix = f"ct_{contact.slug[:8]}"
        filename = generate_upload_filename(prefix, file.name, ext=".webp")
        large_filename = generate_upload_filename(prefix + "_lg", file.name, ext=".webp")
        # Upload avatars
        upload_to_storage(filename, small_bytes)
        upload_to_storage(large_filename, large_bytes)
        # Store only the filename (object key) in the DB
        avatar_path = filename
        print("avatar_path:", avatar_path, "length:", len(avatar_path))
        print("large_avatar_path:", large_filename, "length:", len(large_filename))
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
        return 400, DetailResponse(detail=f"Failed to process avatar: {str(e)}")

@contacts_router.delete("/{slug}/avatar/", auth=JWTAuth(), response={200: DetailResponse, 404: DetailResponse})
def delete_contact_avatar(request, slug: str):
    contact = get_object_or_404(Contact, slug=slug)
    check_contact_member(request.user, contact.organization)
    if not contact.avatar_path:
        return 404, DetailResponse(detail="No avatar to delete.")
    delete_existing_avatar(contact)
    contact.avatar_path = None
    contact.save(update_fields=["avatar_path"])
    return DetailResponse(detail="Avatar deleted.")

@contacts_router.delete("/{slug}/", auth=JWTAuth())
def delete_contact(request, slug: str):
    contact = get_object_or_404(Contact, slug=slug)
    check_contact_member(request.user, contact.organization)
    contact.delete()
    return {"detail": "Contact deleted."}

@contacts_router.get("/avatars/{path:path}", auth=JWTAuth())
def get_contact_avatar_url(request, path: str):
    """
    Generate a presigned URL for a contact's avatar image.
    For large version, append '_lg' before the file extension.
    Example: /api/v1/contacts/avatars/avatar-user123-20240529.webp
             /api/v1/contacts/avatars/avatar-user123-20240529_lg.webp
    """
    import os
    from urllib.parse import urlparse
    import boto3
    from django.conf import settings
    from ninja.errors import HttpError

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
    
    # Construct the S3 key - use the path directly as it's already the full key
    s3_key = path
    
    # Generate presigned URL
    s3_client = boto3.client(
        's3',
        endpoint_url=settings.STORAGES['default']['OPTIONS']['endpoint_url'],
        aws_access_key_id=settings.STORAGES['default']['OPTIONS']['access_key'],
        aws_secret_access_key=settings.STORAGES['default']['OPTIONS']['secret_key'],
        region_name=settings.STORAGES['default']['OPTIONS']['region_name'],
        config=boto3.session.Config(signature_version='s3v4')
    )
    
    try:
        # Generate presigned URL for the object
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.STORAGES['default']['OPTIONS']['bucket_name'], 'Key': s3_key},
            ExpiresIn=3600  # URL expires in 1 hour
        )
        return {"url": url}
    except Exception as e:
        return HttpError(500, f"Failed to generate presigned URL: {str(e)}")
