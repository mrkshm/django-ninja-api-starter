from dataclasses import dataclass
from typing import Any

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from core.utils.auth_utils import check_object_belongs_to_org, get_org_or_404
from organizations.access import assert_org_view


@dataclass(frozen=True)
class OrgScopedContentObject:
    organization: Any
    content_type: ContentType
    model_class: type
    obj: Any


def get_request_user(request):
    return getattr(request, "auth", None) or getattr(request, "user", None)


def resolve_org_for_request(request, org_slug: str):
    org = get_org_or_404(org_slug)
    assert_org_view(get_request_user(request), org)
    return org


def resolve_content_type(app_label: str, model: str) -> ContentType:
    try:
        model_class = apps.get_model(app_label, model)
    except LookupError as exc:
        raise HttpError(404, "Object type not found") from exc

    if model_class is None:
        raise HttpError(404, "Object type not found")

    try:
        return ContentType.objects.get(app_label=app_label, model=model)
    except ContentType.DoesNotExist as exc:
        raise HttpError(404, "Object type not found") from exc


def resolve_org_scoped_content_object(
    request,
    org_slug: str,
    app_label: str,
    model: str,
    obj_id: int,
) -> OrgScopedContentObject:
    org = resolve_org_for_request(request, org_slug)
    content_type = resolve_content_type(app_label, model)
    model_class = apps.get_model(app_label, model)
    try:
        obj = get_object_or_404(model_class, pk=obj_id)
    except Http404 as exc:
        raise HttpError(404, "Object not found") from exc
    check_object_belongs_to_org(obj, org)
    return OrgScopedContentObject(
        organization=org,
        content_type=content_type,
        model_class=model_class,
        obj=obj,
    )
