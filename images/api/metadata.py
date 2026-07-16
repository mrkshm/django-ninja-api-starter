from django.shortcuts import get_object_or_404

from core.authentication import JWTAuth
from images.api.common import router
from images.models import Image
from images.schemas import ImageOut, ImagePatchIn
from images.serializers import serialize_image
from organizations.scope import resolve_org_scope


@router.patch(
    "/orgs/{org_slug}/images/{image_id}/",
    response={200: ImageOut, 400: dict},
    auth=JWTAuth(),
)
def edit_image_metadata(request, org_slug: str, image_id: int, data: ImagePatchIn):
    scope = resolve_org_scope(request, org_slug).require_write()
    image = get_object_or_404(Image, id=image_id, organization=scope.org)
    payload = data.model_dump(exclude_unset=True)
    for field in ("title", "description", "alt_text"):
        if field in payload:
            setattr(image, field, payload[field])
    image.save(update_fields=[*payload, "updated_at"])
    return serialize_image(image)
