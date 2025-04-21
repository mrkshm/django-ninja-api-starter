import pytest
from accounts.models import User, UserManager

@pytest.mark.django_db
def test_username_generated_from_email(db):
    manager = User.objects
    user1 = manager.create_user(email="jane.doe@gmail.com", password="pw")
    assert user1.username == "jane.doe"

@pytest.mark.django_db
def test_username_uniqueness(db):
    manager = User.objects
    user1 = manager.create_user(email="jane.doe@gmail.com", password="pw")
    user2 = manager.create_user(email="jane.doe@goomail.com", password="pw")
    assert user2.username.startswith("jane.doe")
    assert user1.username != user2.username

@pytest.mark.django_db
def test_username_slugify(db):
    manager = User.objects
    user = manager.create_user(email="Jane Doe+foo@gmail.com", password="pw")
    assert "-" not in user.username