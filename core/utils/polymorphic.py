from dataclasses import dataclass
from typing import Any

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from core.utils.auth_utils import check_object_belongs_to_org
from organizations.scope import OrgScope, resolve_org_scope

ATTACHABLE_MODELS = frozenset(
    {
        ("contacts", "contact"),
        ("organizations", "organization"),
    }
)


@dataclass(frozen=True)
class OrgScopedContentObject:
    scope: OrgScope
    organization: Any
    content_type: ContentType
    model_class: type
    obj: Any


def resolve_org_for_request(request, org_slug: str):
    return resolve_org_scope(request, org_slug).org


def resolve_content_type(app_label: str, model: str) -> ContentType:
    if (app_label.lower(), model.lower()) not in ATTACHABLE_MODELS:
        raise HttpError(404, "Object type not found")
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
    scope = resolve_org_scope(request, org_slug)
    org = scope.org
    content_type = resolve_content_type(app_label, model)
    model_class = apps.get_model(app_label, model)
    try:
        obj = get_object_or_404(model_class, pk=obj_id)
    except Http404 as exc:
        raise HttpError(404, "Object not found") from exc
    check_object_belongs_to_org(obj, org)
    return OrgScopedContentObject(
        scope=scope,
        organization=org,
        content_type=content_type,
        model_class=model_class,
        obj=obj,
    )
