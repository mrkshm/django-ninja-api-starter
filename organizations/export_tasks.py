import io
import json
import tempfile
import zipfile
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone
from celery import shared_task
from core.email_utils import send_email
from organizations.models import Organization, Membership
from contacts.models import Contact
from tags.models import Tag, TaggedItem
from images.models import Image
import boto3
from botocore.exceptions import ClientError

User = get_user_model()

EXPORT_RETENTION_DAYS = 7
EXPORT_PREFIX = "exports/"

def get_export_bucket():
    # Use custom export bucket if set, else default S3 bucket
    return getattr(settings, "EXPORT_BUCKET", getattr(settings, "AWS_STORAGE_BUCKET_NAME", None))

def _serialize_org_data(org):
    # Users/Members
    memberships = Membership.objects.filter(organization=org).select_related("user")
    users = [
        {
            "email": m.user.email,
            "username": m.user.username,
            "first_name": m.user.first_name,
            "last_name": m.user.last_name,
            "role": m.role,
            "preferred_language": getattr(m.user, "preferred_language", None),
            "created_at": m.user.created_at.isoformat() if m.user.created_at else None,
        }
        for m in memberships
    ]
    # Contacts
    contacts = list(Contact.objects.filter(organization=org))
    contacts_data = [
        {
            "id": c.id,
            "display_name": c.display_name,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "email": c.email,
            "location": c.location,
            "phone": c.phone,
            "notes": c.notes,
            "avatar_path": c.avatar_path,
            "creator": c.creator_id,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "tags": list(c.tags.values_list("tag__name", flat=True)),
        }
        for c in contacts
    ]
    # Tags
    tags = list(Tag.objects.filter(organization=org))
    tags_data = [
        {"id": t.id, "name": t.name, "slug": t.slug} for t in tags
    ]
    # Images
    images = list(Image.objects.filter(organization=org))
    images_data = [
        {
            "id": img.id,
            "title": img.title,
            "description": img.description,
            "alt_text": img.alt_text,
            "creator": img.creator_id,
            "created_at": img.created_at.isoformat() if img.created_at else None,
            "updated_at": img.updated_at.isoformat() if img.updated_at else None,
            "file": img.file.name if img.file else None,
        }
        for img in images
    ]
    return {
        "organization": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "type": org.type,
            "created_at": org.created_at.isoformat() if org.created_at else None,
            "updated_at": org.updated_at.isoformat() if org.updated_at else None,
        },
        "users": users,
        "contacts": contacts_data,
        "tags": tags_data,
        "images": images_data,
    }

def _add_images_to_zip(zipf, images):
    for img in images:
        if img.file:
            img.file.open("rb")
            with img.file as f:
                zipf.writestr(f"images/{img.file.name.split('/')[-1]}", f.read())

def _upload_to_s3(file_bytes, s3_key):
    s3 = boto3.client("s3")
    bucket = get_export_bucket()
    if not bucket:
        raise RuntimeError("No S3 bucket configured for exports. Set AWS_STORAGE_BUCKET_NAME or EXPORT_BUCKET in settings.")
    s3.upload_fileobj(io.BytesIO(file_bytes), bucket, s3_key)

def _generate_presigned_url(s3_key, expires=3600):
    s3 = boto3.client("s3")
    bucket = get_export_bucket()
    if not bucket:
        raise RuntimeError("No S3 bucket configured for exports. Set AWS_STORAGE_BUCKET_NAME or EXPORT_BUCKET in settings.")
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=expires,
        )
    except ClientError:
        url = None
    return url

@shared_task
def export_org_data_task(org_id, user_email):
    org = Organization.objects.get(id=org_id)
    data = _serialize_org_data(org)
    images = list(Image.objects.filter(organization=org))
    with tempfile.NamedTemporaryFile() as tmp:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Add JSON data
            zipf.writestr("data.json", json.dumps(data, indent=2))
            # Add images
            _add_images_to_zip(zipf, images)
        tmp.seek(0)
        now = timezone.now().strftime("%Y%m%dT%H%M%S")
        s3_key = f"{EXPORT_PREFIX}org_{org.slug}_{now}.zip"
        _upload_to_s3(tmp.read(), s3_key)
    url = _generate_presigned_url(s3_key, expires=3600 * 24 * EXPORT_RETENTION_DAYS)
    # Email user
    subject = f"Your organization export for {org.name} is ready"
    body = f"Your export is ready. Download it here (link expires in {EXPORT_RETENTION_DAYS} days):\n{url}"
    send_email(subject, user_email, body)
    return {"s3_key": s3_key, "url": url}
