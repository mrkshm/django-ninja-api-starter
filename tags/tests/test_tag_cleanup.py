import pytest
from django.contrib.contenttypes.models import ContentType
from tags.models import Tag, TaggedItem
from tags.tasks import cleanup_orphaned_tags
from organizations.models import Organization
from accounts.models import User

@pytest.mark.django_db
def test_cleanup_orphaned_tags(tmp_path, settings):
    org = Organization.objects.create(name="Test Org")
    user = User.objects.create_user(email="test@example.com", password="pw")
    org_ct = ContentType.objects.get_for_model(Organization)

    # Tag referenced by a TaggedItem
    tag_used = Tag.objects.create(organization=org, name="used", slug="used")
    TaggedItem.objects.create(
        tag=tag_used,
        content_type=org_ct,
        object_id=org.id
    )
    # Orphaned tag
    tag_orphaned = Tag.objects.create(organization=org, name="orphaned", slug="orphaned")

    deleted_count = cleanup_orphaned_tags()
    assert deleted_count == 1
    assert Tag.objects.filter(id=tag_orphaned.id).count() == 0
    assert Tag.objects.filter(id=tag_used.id).exists()
