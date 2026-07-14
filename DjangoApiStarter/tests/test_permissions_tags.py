import pytest
from types import SimpleNamespace
from ninja.errors import HttpError
from django.contrib.auth import get_user_model

from tags.api import (
    list_tags,
    search_tags,
    get_tag_by_slug,
    list_tags_for_object,
    assign_tags,
    update_tag,
    delete_tag,
    unassign_tags,
    unassign_tag_by_slug,
)
from tags.schemas import TagUpdate
from tags.models import Tag
from contacts.models import Contact
from organizations.models import Organization


@pytest.mark.django_db
class TestTagPermissions:
    def setup_method(self):
        User = get_user_model()
        self.member = User.objects.create_user(
            email="member@example.com", password="pass12345"
        )
        self.nonmember = User.objects.create_user(
            email="nonmember@example.com", password="pass12345"
        )
        self.org = Organization.objects.create(
            name="Acme", slug="acme", creator=self.member
        )
        self.other_org = Organization.objects.create(
            name="Beta", slug="beta", creator=self.nonmember
        )
        self.contact = Contact.objects.create(
            display_name="John", slug="john", organization=self.org, creator=self.member
        )
        # Direct function calls; no router introspection needed

    def _req(self, user, method="GET", path="/api/v1/"):
        return SimpleNamespace(
            auth=user, user=user, headers={}, META={}, method=method, path=path
        )

    # No op() needed

    def test_non_member_cannot_list_tags(self):
        req = self._req(self.nonmember)
        with pytest.raises(HttpError) as ctx:
            # Bypass pagination
            list_tags.__wrapped__(req, self.org.slug, None)
        assert getattr(ctx.value, "status_code", 403) == 403

    def test_non_member_cannot_search_tags(self):
        req = self._req(self.nonmember)
        with pytest.raises(HttpError) as ctx:
            search_tags.__wrapped__(req, self.org.slug, q=None)
        assert getattr(ctx.value, "status_code", 403) == 403

    def test_non_member_cannot_get_tag_by_slug(self):
        tag = Tag.objects.create(organization=self.org, name="vip", slug="vip")
        req = self._req(self.nonmember)
        with pytest.raises(HttpError) as ctx:
            get_tag_by_slug(req, self.org.slug, tag.slug)
        assert getattr(ctx.value, "status_code", 403) == 403

    def test_non_member_cannot_list_tags_for_object(self):
        req = self._req(self.nonmember)
        with pytest.raises(HttpError) as ctx:
            list_tags_for_object.__wrapped__(
                req, self.org.slug, "contacts", "contact", self.contact.id, None
            )
        assert getattr(ctx.value, "status_code", 403) == 403

    def test_non_member_cannot_assign_tags(self):
        req = self._req(self.nonmember, method="POST")
        with pytest.raises(HttpError) as ctx:
            assign_tags(
                req, self.org.slug, "contacts", "contact", self.contact.id, ["vip"]
            )
        assert getattr(ctx.value, "status_code", 403) == 403

    def test_non_member_cannot_update_tag(self):
        tag = Tag.objects.create(organization=self.org, name="vip", slug="vip")
        req = self._req(self.nonmember, method="PATCH")
        with pytest.raises(HttpError) as ctx:
            update_tag(req, self.org.slug, tag.id, TagUpdate(name="vip2"))
        assert getattr(ctx.value, "status_code", 403) == 403

    def test_non_member_cannot_delete_tag(self):
        tag = Tag.objects.create(organization=self.org, name="vip", slug="vip")
        req = self._req(self.nonmember, method="DELETE")
        with pytest.raises(HttpError) as ctx:
            delete_tag(req, self.org.slug, tag.id)
        assert getattr(ctx.value, "status_code", 403) == 403

    def test_non_member_cannot_unassign_tags_bulk(self):
        tag = Tag.objects.create(organization=self.org, name="vip", slug="vip")
        req = self._req(self.nonmember, method="DELETE")
        with pytest.raises(HttpError) as ctx:
            unassign_tags(
                req, self.org.slug, "contacts", "contact", self.contact.id, [tag.id]
            )
        assert getattr(ctx.value, "status_code", 403) == 403

    def test_non_member_cannot_unassign_tag_by_slug(self):
        tag = Tag.objects.create(organization=self.org, name="vip", slug="vip")
        req = self._req(self.nonmember, method="DELETE")
        with pytest.raises(HttpError) as ctx:
            unassign_tag_by_slug(
                req, self.org.slug, "contacts", "contact", self.contact.id, tag.slug
            )
        assert getattr(ctx.value, "status_code", 403) == 403
