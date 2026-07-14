import pytest
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from images.models import Image, PolymorphicImageRelation
from organizations.models import Organization
from io import BytesIO
from PIL import Image as PilImage

@pytest.mark.django_db
class TestImageModel:
    def setup_method(self):
        self.org = Organization.objects.create(name="Test Org", slug="test-org")

    def create_test_image_file(self, color=(255, 0, 0), size=(300, 300), name="test.png"):
        img = PilImage.new("RGB", size, color)
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return SimpleUploadedFile(name, buf.read(), content_type="image/png")

    def test_image_creation(self):
        file = self.create_test_image_file()
        image = Image.objects.create(
            file=file,
            description="desc",
            alt_text="alt",
            title="title",
            organization=self.org,
        )
        assert image.description == "desc"
        assert image.alt_text == "alt"
        assert image.title == "title"
        assert image.file

@pytest.mark.django_db
class TestPolymorphicImageRelation:
    def setup_method(self):
        self.org = Organization.objects.create(name="Test Org", slug="test-org")
        self.image = Image.objects.create(
            file=self.create_test_image_file(),
            description="desc",
            alt_text="alt",
            title="title",
            organization=self.org,
        )
        # Use User as a dummy target for relation
        User = get_user_model()
        self.target = User.objects.create(username="testuser")
        self.target_type = ContentType.objects.get_for_model(User)

    def create_test_image_file(self, color=(0, 255, 0), size=(300, 300), name="test2.png"):
        img = PilImage.new("RGB", size, color)
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return SimpleUploadedFile(name, buf.read(), content_type="image/png")

    def test_relation_creation(self):
        relation = PolymorphicImageRelation.objects.create(
            image=self.image,
            content_type=self.target_type,
            object_id=self.target.pk,
            is_cover=True,
            order=1,
            custom_description="custom desc",
            custom_alt_text="custom alt",
            custom_title="custom title",
        )
        assert relation.image == self.image
        assert relation.content_object == self.target
        assert relation.is_cover
        assert relation.order == 1
        assert relation.custom_description == "custom desc"
        assert relation.custom_alt_text == "custom alt"
        assert relation.custom_title == "custom title"
