import pytest
from django.contrib.auth import get_user_model

from contacts.models import Contact
from organizations.tests.utils import create_test_group

# Create your tests here.


@pytest.mark.django_db
class TestContactModel:
    def setup_method(self):
        User = get_user_model()
        self.user = User.objects.create_user(email="test@example.com", password="pw")
        self.org = create_test_group(
            name="Test Org",
            slug="test-org",
            creator=self.user,
        )

    def test_create_contact_minimal(self):
        contact = Contact.objects.create(
            display_name="Joe", organization=self.org, creator=self.user
        )
        assert contact.display_name == "Joe"
        assert contact.organization == self.org
        assert contact.creator == self.user

    def test_optional_fields(self):
        contact = Contact.objects.create(
            display_name="Ann",
            organization=self.org,
            creator=self.user,
            email="ann@example.com",
            location="Berlin",
            phone="12345",
            notes="Friend",
            avatar_path="/avatars/ann.png",
        )
        assert contact.email == "ann@example.com"
        assert contact.location == "Berlin"
        assert contact.phone == "12345"
        assert contact.notes == "Friend"
        assert contact.avatar_path == "/avatars/ann.png"

    def test_str_method(self):
        contact = Contact.objects.create(
            display_name="Bob", organization=self.org, creator=self.user
        )
        assert str(contact) == "Bob"

    def test_on_delete_organization(self):
        contact = Contact.objects.create(
            display_name="Del", organization=self.org, creator=self.user
        )
        self.org.delete()
        assert not Contact.objects.filter(id=contact.id).exists()

    def test_on_delete_creator_set_null(self):
        contact = Contact.objects.create(
            display_name="Null Creator", organization=self.org, creator=self.user
        )
        self.user.delete()
        contact.refresh_from_db()
        assert contact.creator is None
