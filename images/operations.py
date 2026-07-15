from __future__ import annotations

from dataclasses import dataclass

from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction

from images.models import Image, PolymorphicImageRelation


class ImageOperationError(ValueError):
    pass


class ImageNotFoundError(ImageOperationError):
    pass


class ImageOwnershipError(ImageOperationError):
    pass


@dataclass(frozen=True)
class AttachImagesResult:
    relations: list[PolymorphicImageRelation]
    attached_image_ids: list[int]


def _lock_target(target: models.Model) -> None:
    target._meta.model._base_manager.select_for_update().only("pk").get(pk=target.pk)


def _locked_relations(
    *, content_type: ContentType, object_id: int
) -> list[PolymorphicImageRelation]:
    return list(
        PolymorphicImageRelation.objects.select_for_update()
        .filter(content_type=content_type, object_id=object_id)
        .select_related("image")
        .order_by("order", "pk")
    )


def _images_in_request_order(
    *, organization_id: int, image_ids: list[int]
) -> list[Image]:
    images_by_id = {
        image.pk: image
        for image in Image.objects.filter(
            organization_id=organization_id,
            pk__in=image_ids,
        )
    }
    missing = [image_id for image_id in image_ids if image_id not in images_by_id]
    if missing:
        raise ImageNotFoundError(
            "One or more images do not belong to this organization"
        )
    return [images_by_id[image_id] for image_id in image_ids]


@transaction.atomic
def attach_images_to_object(
    *,
    organization_id: int,
    target: models.Model,
    content_type: ContentType,
    image_ids: list[int],
) -> AttachImagesResult:
    _lock_target(target)
    existing_relations = _locked_relations(
        content_type=content_type,
        object_id=target.pk,
    )
    images = _images_in_request_order(
        organization_id=organization_id,
        image_ids=image_ids,
    )

    relation_by_image_id = {
        relation.image_id: relation for relation in existing_relations
    }
    has_cover = any(relation.is_cover for relation in existing_relations)
    existing_orders = [
        relation.order for relation in existing_relations if relation.order is not None
    ]
    next_order = max(existing_orders, default=-1) + 1
    attached_image_ids: list[int] = []
    result_relations: list[PolymorphicImageRelation] = []

    for image in images:
        relation = relation_by_image_id.get(image.pk)
        if relation is None:
            relation = PolymorphicImageRelation.objects.create(
                image=image,
                content_type=content_type,
                object_id=target.pk,
                order=next_order,
                is_cover=not has_cover,
            )
            relation_by_image_id[image.pk] = relation
            next_order += 1
            has_cover = True
            attached_image_ids.append(image.pk)
        result_relations.append(relation)

    return AttachImagesResult(
        relations=result_relations,
        attached_image_ids=attached_image_ids,
    )


@transaction.atomic
def detach_images_from_object(
    *,
    target: models.Model,
    content_type: ContentType,
    image_ids: list[int],
) -> list[int]:
    _lock_target(target)
    relations = _locked_relations(
        content_type=content_type,
        object_id=target.pk,
    )
    requested_ids = set(image_ids)
    detached_ids = [
        relation.image_id
        for relation in relations
        if relation.image_id in requested_ids
    ]
    if detached_ids:
        PolymorphicImageRelation.objects.filter(
            content_type=content_type,
            object_id=target.pk,
            image_id__in=detached_ids,
        ).delete()
    return detached_ids


@transaction.atomic
def reorder_object_images(
    *,
    organization_id: int,
    target: models.Model,
    content_type: ContentType,
    image_ids: list[int],
) -> None:
    _lock_target(target)
    relations = _locked_relations(
        content_type=content_type,
        object_id=target.pk,
    )
    if not relations:
        return

    if len(set(image_ids)) != len(image_ids):
        raise ImageOperationError("Duplicate image ids in request")
    relation_by_image_id = {relation.image_id: relation for relation in relations}
    if any(image_id not in relation_by_image_id for image_id in image_ids):
        raise ImageOperationError(
            "One or more image ids are not attached to this object"
        )
    if len(image_ids) != len(relations):
        raise ImageOperationError(
            "Reorder must include all currently attached image ids"
        )
    if {relation.image.organization_id for relation in relations} != {organization_id}:
        raise ImageOwnershipError(
            "One or more images do not belong to this organization"
        )

    order_updates: list[PolymorphicImageRelation] = []
    for order, image_id in enumerate(image_ids):
        relation = relation_by_image_id[image_id]
        if relation.order != order:
            relation.order = order
            order_updates.append(relation)
    if order_updates:
        PolymorphicImageRelation.objects.bulk_update(order_updates, ["order"])

    desired_cover = relation_by_image_id[image_ids[0]]
    current_cover = next(
        (relation for relation in relations if relation.is_cover),
        None,
    )
    if current_cover is None or current_cover.pk != desired_cover.pk:
        PolymorphicImageRelation.objects.filter(
            content_type=content_type,
            object_id=target.pk,
            is_cover=True,
        ).update(is_cover=False)
        PolymorphicImageRelation.objects.filter(pk=desired_cover.pk).update(
            is_cover=True
        )


@transaction.atomic
def set_object_cover_image(
    *,
    organization_id: int,
    target: models.Model,
    content_type: ContentType,
    image_id: int,
) -> None:
    _lock_target(target)
    relations = _locked_relations(
        content_type=content_type,
        object_id=target.pk,
    )
    target_relation = next(
        (relation for relation in relations if relation.image_id == image_id),
        None,
    )
    if (
        target_relation is None
        or target_relation.image.organization_id != organization_id
    ):
        raise ImageNotFoundError("Image is not attached to this object")
    PolymorphicImageRelation.objects.filter(
        content_type=content_type,
        object_id=target.pk,
        is_cover=True,
    ).exclude(pk=target_relation.pk).update(is_cover=False)
    if not target_relation.is_cover:
        PolymorphicImageRelation.objects.filter(pk=target_relation.pk).update(
            is_cover=True
        )


@transaction.atomic
def unset_object_cover_image(
    *, target: models.Model, content_type: ContentType
) -> None:
    _lock_target(target)
    _locked_relations(content_type=content_type, object_id=target.pk)
    PolymorphicImageRelation.objects.filter(
        content_type=content_type,
        object_id=target.pk,
        is_cover=True,
    ).update(is_cover=False)
