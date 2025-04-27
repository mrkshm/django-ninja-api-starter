from ninja import Router, Schema
from ninja.errors import HttpError
from ninja_jwt.authentication import JWTAuth
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from core.utils.utils import make_it_unique, generate_upload_filename
from core.utils.storage import upload_to_storage
from core.utils.image import resize_avatar_images
from core.utils.avatar import delete_existing_avatar
from .models import Contact
from .schemas import ContactIn, ContactOut, ContactAvatarResponse, DetailResponse
from organizations.models import Organization
from organizations.permissions import is_member
from ninja.pagination import paginate, LimitOffsetPagination
from ninja import File, UploadedFile
from django.core.files.storage import default_storage

contacts_router = Router()

# Utility for consistent contact serialization
def serialize_contact(contact):
    # Convert datetimes to ISO strings for API output
    return {
        **contact.__dict__,
        "organization": contact.organization.slug,
        "creator": contact.creator.slug if contact.creator else None,
        "created_at": contact.created_at.isoformat() if contact.created_at else None,
        "updated_at": contact.updated_at.isoformat() if contact.updated_at else None,
        "tags": [ti.tag for ti in contact.tags.select_related("tag").all()]
    }

class ContactUpdate(Schema):
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    organization: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None

# Helper to check org membership for a contact
def check_contact_member(request, contact):
    user = request.user
    if not is_member(user, contact.organization):
        raise HttpError(403, "You do not have access to this organization.")

@contacts_router.get("/", response=list[ContactOut], auth=JWTAuth())
@paginate(LimitOffsetPagination)
def list_contacts(request):
    user = request.user
    # Only show contacts for orgs the user is a member of
    org_slugs = [m.organization.slug for m in user.memberships.select_related("organization").all()]
    qs = Contact.objects.select_related("organization", "creator").filter(organization__slug__in=org_slugs)
    return [serialize_contact(c) for c in qs]

@contacts_router.get("/{slug}/", response=ContactOut, auth=JWTAuth())
def get_contact(request, slug: str):
    contact = get_object_or_404(Contact.objects.select_related("organization", "creator"), slug=slug)
    check_contact_member(request, contact)
    return ContactOut.model_validate(serialize_contact(contact))

@contacts_router.post("/", response=ContactOut, auth=JWTAuth())
def create_contact(request, data: ContactIn):
    org_slug = data.organization
    organization = get_object_or_404(Organization, slug=org_slug)
    user = request.user
    if not is_member(user, organization):
        raise HttpError(403, "You do not have access to this organization.")
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
    if not display_name:
        return 400, {"detail": "display_name or first/last name required"}
    contact_data = data.model_dump()
    contact_data["display_name"] = display_name
    contact_data["organization"] = organization
    contact = Contact.objects.create(
        **contact_data, creator=user
    )
    return ContactOut.model_validate(serialize_contact(contact))

@contacts_router.put("/{slug}/", response=ContactOut, auth=JWTAuth())
def update_contact(request, slug: str, data: ContactIn):
    contact = get_object_or_404(Contact, slug=slug)
    check_contact_member(request, contact)
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "organization":
            org = get_object_or_404(Organization, slug=value)
            setattr(contact, "organization", org)
        else:
            setattr(contact, field, value)
    contact.save()
    return ContactOut.model_validate(serialize_contact(contact))

@contacts_router.patch("/{slug}/", response=ContactOut, auth=JWTAuth())
def partial_update_contact(request, slug: str, data: ContactUpdate):
    contact = get_object_or_404(Contact, slug=slug)
    check_contact_member(request, contact)
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
    return ContactOut.model_validate(serialize_contact(contact))

@contacts_router.post("/{slug}/avatar/", response={200: ContactAvatarResponse, 400: DetailResponse}, auth=JWTAuth())
def upload_contact_avatar(request, slug: str, file: UploadedFile = File(...)):
    """
    Upload and set avatar for a contact. Stores small and large sizes, updates avatar_path.
    """
    print('FILES:', request.FILES)
    print('DATA:', request.POST)
    print('FILE ARG:', file)
    contact = get_object_or_404(Contact, slug=slug)
    check_contact_member(request, contact)
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
    check_contact_member(request, contact)
    if not contact.avatar_path:
        return 404, DetailResponse(detail="No avatar to delete.")
    delete_existing_avatar(contact)
    contact.avatar_path = None
    contact.save(update_fields=["avatar_path"])
    return DetailResponse(detail="Avatar deleted.")

@contacts_router.delete("/{slug}/", auth=JWTAuth())
def delete_contact(request, slug: str):
    contact = get_object_or_404(Contact, slug=slug)
    check_contact_member(request, contact)
    contact.delete()
    return {"detail": "Contact deleted."}