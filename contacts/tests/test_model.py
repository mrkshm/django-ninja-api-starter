from django.test import TestCase
from django.contrib.auth import get_user_model
from organizations.models import Organization
from contacts.models import Contact

# Create your tests here.

class ContactModelTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email="test@example.com", password="pw")
        self.org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=self.user)

    def test_create_contact_minimal(self):
        contact = Contact.objects.create(
            display_name="Joe",
            organization=self.org,
            creator=self.user
        )
        self.assertEqual(contact.display_name, "Joe")
        self.assertEqual(contact.organization, self.org)
        self.assertEqual(contact.creator, self.user)

    def test_optional_fields(self):
        contact = Contact.objects.create(
            display_name="Ann",
            organization=self.org,
            creator=self.user,
            email="ann@example.com",
            location="Berlin",
            phone="12345",
            notes="Friend",
            avatar_path="/avatars/ann.png"
        )
        self.assertEqual(contact.email, "ann@example.com")
        self.assertEqual(contact.location, "Berlin")
        self.assertEqual(contact.phone, "12345")
        self.assertEqual(contact.notes, "Friend")
        self.assertEqual(contact.avatar_path, "/avatars/ann.png")

    def test_str_method(self):
        contact = Contact.objects.create(
            display_name="Bob",
            organization=self.org,
            creator=self.user
        )
        self.assertEqual(str(contact), "Bob")

    def test_on_delete_organization(self):
        contact = Contact.objects.create(
            display_name="Del",
            organization=self.org,
            creator=self.user
        )
        self.org.delete()
        self.assertFalse(Contact.objects.filter(id=contact.id).exists())

    def test_on_delete_creator_set_null(self):
        contact = Contact.objects.create(
            display_name="Null Creator",
            organization=self.org,
            creator=self.user
        )
        self.user.delete()
        contact.refresh_from_db()
        self.assertIsNone(contact.creator)
