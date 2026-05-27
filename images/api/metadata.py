from django.shortcuts import get_object_or_404
from images.api.common import get_org_for_request, router
from images.models import Image
from images.schemas import ImageOut, ImagePatchIn
from images.serializers import serialize_image
from ninja_jwt.authentication import JWTAuth


@router.patch("/orgs/{org_slug}/images/{image_id}/", response={200: ImageOut, 400: dict}, auth=JWTAuth())
def edit_image_metadata(request, org_slug: str, image_id: int, data: ImagePatchIn):
    org = get_org_for_request(request, org_slug)
    image = get_object_or_404(Image, id=image_id, organization=org)
    payload = data.model_dump(exclude_unset=True)
    for field in ("title", "description", "alt_text"):
        if field in payload:
            setattr(image, field, payload[field])
    image.save()
    return serialize_image(image)
