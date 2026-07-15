from __future__ import annotations

import threading
from collections.abc import Callable

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import close_old_connections, connection

from accounts.models import User
from images.models import Image, PolymorphicImageRelation
from images.operations import attach_images_to_object, reorder_object_images
from organizations.models import Organization

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="row-lock behavior requires PostgreSQL",
    ),
]


def run_concurrently(*operations: Callable[[], None]) -> list[BaseException | None]:
    barrier = threading.Barrier(len(operations))
    outcomes: list[BaseException | None] = []
    outcomes_lock = threading.Lock()

    def run(operation: Callable[[], None]) -> None:
        close_old_connections()
        outcome: BaseException | None = None
        try:
            barrier.wait(timeout=5)
            operation()
        except BaseException as exc:
            outcome = exc
        finally:
            close_old_connections()
            with outcomes_lock:
                outcomes.append(outcome)

    threads = [
        threading.Thread(target=run, args=(operation,)) for operation in operations
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(
        not thread.is_alive() for thread in threads
    ), "possible database deadlock"
    return outcomes


def image_operation_fixture():
    user = User.objects.create_user(email="image-locks@example.com", password="pw")
    organization = Organization.objects.get(type="personal", creator=user)
    content_type = ContentType.objects.get_for_model(Organization)
    images = [
        Image.objects.create(organization=organization, creator=user) for _ in range(3)
    ]
    return organization, content_type, images


def test_concurrent_attaches_preserve_unique_order_and_cover():
    organization, content_type, images = image_operation_fixture()

    outcomes = run_concurrently(
        lambda: attach_images_to_object(
            organization_id=organization.pk,
            target=organization,
            content_type=content_type,
            image_ids=[images[0].pk],
        ),
        lambda: attach_images_to_object(
            organization_id=organization.pk,
            target=organization,
            content_type=content_type,
            image_ids=[images[1].pk],
        ),
    )

    assert outcomes == [None, None]
    relations = list(
        PolymorphicImageRelation.objects.filter(
            content_type=content_type,
            object_id=organization.pk,
        ).order_by("order")
    )
    assert {relation.order for relation in relations} == {0, 1}
    assert sum(relation.is_cover for relation in relations) == 1


def test_concurrent_reorders_finish_in_one_complete_valid_order():
    organization, content_type, images = image_operation_fixture()
    image_ids = [image.pk for image in images]
    attach_images_to_object(
        organization_id=organization.pk,
        target=organization,
        content_type=content_type,
        image_ids=image_ids,
    )
    first_order = list(reversed(image_ids))
    second_order = image_ids[1:] + image_ids[:1]

    outcomes = run_concurrently(
        lambda: reorder_object_images(
            organization_id=organization.pk,
            target=organization,
            content_type=content_type,
            image_ids=first_order,
        ),
        lambda: reorder_object_images(
            organization_id=organization.pk,
            target=organization,
            content_type=content_type,
            image_ids=second_order,
        ),
    )

    assert outcomes == [None, None]
    relations = list(
        PolymorphicImageRelation.objects.filter(
            content_type=content_type,
            object_id=organization.pk,
        ).order_by("order")
    )
    final_order = [relation.image_id for relation in relations]
    assert final_order in (first_order, second_order)
    assert [relation.order for relation in relations] == [0, 1, 2]
    assert relations[0].is_cover is True
    assert sum(relation.is_cover for relation in relations) == 1
