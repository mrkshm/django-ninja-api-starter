from dataclasses import dataclass
from typing import cast

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.http import Http404, HttpRequest
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from organizations.models import Organization
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
    organization: Organization
    content_type: ContentType
    model_class: type[models.Model]
    obj: models.Model


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
    request: HttpRequest,
    org_slug: str,
    app_label: str,
    model: str,
    obj_id: int,
) -> OrgScopedContentObject:
    scope = resolve_org_scope(request, org_slug)
    org = scope.org
    content_type = resolve_content_type(app_label, model)
    model_class = apps.get_model(app_label, model)
    if model_class is None:
        raise HttpError(404, "Object type not found")
    try:
        obj = cast(models.Model, get_object_or_404(model_class, pk=obj_id))
    except Http404 as exc:
        raise HttpError(404, "Object not found") from exc
    object_org_id = (
        obj.pk
        if isinstance(obj, Organization)
        else getattr(obj, "organization_id", None)
    )
    if object_org_id != org.pk:
        raise HttpError(404, "Object not found")
    return OrgScopedContentObject(
        scope=scope,
        organization=org,
        content_type=content_type,
        model_class=model_class,
        obj=obj,
    )
