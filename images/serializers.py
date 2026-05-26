import os

from django.core.files.storage import default_storage

from images.models import Image, PolymorphicImageRelation
from images.schemas import ImageOut, ImageVariants, PolymorphicImageRelationOut


def build_relative_urls(file_name: str) -> tuple[str, ImageVariants]:
    base, _ext = os.path.splitext(file_name)

    def rel(key: str) -> str:
        return f"/media/{key}"

    def exists(key: str) -> bool:
        try:
            return default_storage.exists(key)
        except Exception:
            return False

    original_key = file_name
    original_url = rel(original_key) if exists(original_key) else None
    original_or_fallback = original_url or rel(original_key)

    variants = ImageVariants(
        original=original_or_fallback,
        thumb=rel(f"{base}_thumb.webp") if exists(f"{base}_thumb.webp") else original_or_fallback,
        sm=rel(f"{base}_sm.webp") if exists(f"{base}_sm.webp") else original_or_fallback,
        md=rel(f"{base}_md.webp") if exists(f"{base}_md.webp") else original_or_fallback,
        lg=rel(f"{base}_lg.webp") if exists(f"{base}_lg.webp") else original_or_fallback,
    )
    return original_or_fallback, variants


def serialize_image(image: Image) -> ImageOut:
    file_name = image.file.name if hasattr(image.file, "name") else str(image.file)
    url, variants = build_relative_urls(file_name)
    return ImageOut.model_validate(
        {
            "id": image.id,
            "file": file_name,
            "url": url,
            "variants": variants.model_dump(),
            "description": image.description,
            "alt_text": image.alt_text,
            "title": image.title,
            "organization_id": image.organization_id,
            "creator_id": image.creator_id,
            "created_at": image.created_at.isoformat() if image.created_at else None,
            "updated_at": image.updated_at.isoformat() if image.updated_at else None,
        }
    )


def serialize_image_relation(relation: PolymorphicImageRelation) -> PolymorphicImageRelationOut:
    return PolymorphicImageRelationOut.model_validate(
        {
            "id": relation.id,
            "image": serialize_image(relation.image),
            "content_type": relation.content_type.model,
            "object_id": relation.object_id,
            "is_cover": getattr(relation, "is_cover", False),
            "order": relation.order,
            "custom_description": relation.custom_description,
            "custom_alt_text": relation.custom_alt_text,
            "custom_title": relation.custom_title,
        }
    )
