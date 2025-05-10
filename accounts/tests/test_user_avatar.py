import io
import pytest
from django.contrib.auth import get_user_model
from accounts.tests.utils import create_test_user
from django.utils.datastructures import MultiValueDict
from django.core.files.uploadedfile import SimpleUploadedFile
from ninja.testing import TestClient
from DjangoApiStarter.api import api
from PIL import Image

User = get_user_model()
client = TestClient(api)

def create_test_image(format="PNG", size=(100, 100)):
    image = Image.new("RGB", size, color=(255, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format=format)
    buf.seek(0)
    return buf

@pytest.mark.django_db
def test_avatar_upload_too_large(monkeypatch):
    user = create_test_user(email="bigavatar@example.com", password="pw")
    response = client.post("/token/pair", json={"email": "bigavatar@example.com", "password": "pw"})
    access = response.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    # Create a dummy 11MB file for upload
    large_bytes = b"x" * (11 * 1024 * 1024)
    uploaded = SimpleUploadedFile("large.png", large_bytes, content_type="image/png")
    files = MultiValueDict({"file": [uploaded]})
    response = client.post("/users/avatar", data={}, FILES=files, headers=headers)
    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()

@pytest.mark.django_db
def test_avatar_upload_invalid_content_type():
    user = create_test_user(email="badtype@example.com", password="pw")
    response = client.post("/token/pair", json={"email": "badtype@example.com", "password": "pw"})
    access = response.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    img_buf = create_test_image()
    img_buf.name = "notanimage.txt"
    class FakeFile(io.BytesIO):
        size = len(img_buf.getvalue())
        content_type = "text/plain"
        name = "notanimage.txt"
        file = property(lambda self: self)
    fake_file = FakeFile(img_buf.read())
    uploaded = SimpleUploadedFile(fake_file.name, fake_file.read(), content_type=fake_file.content_type)
    files = MultiValueDict({"file": [uploaded]})
    response = client.post("/users/avatar", data={}, FILES=files, headers=headers)
    assert response.status_code == 400
    assert "invalid file type" in response.json()["detail"].lower()

@pytest.mark.django_db
def test_avatar_upload_corrupt_image():
    user = create_test_user(email="corruptimg@example.com", password="pw")
    response = client.post("/token/pair", json={"email": "corruptimg@example.com", "password": "pw"})
    access = response.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    class CorruptFile(io.BytesIO):
        size = 100
        content_type = "image/png"
        name = "corrupt.png"
        file = property(lambda self: self)
    corrupt_file = CorruptFile(b"notanimageatall")
    uploaded = SimpleUploadedFile(corrupt_file.name, corrupt_file.read(), content_type=corrupt_file.content_type)
    files = MultiValueDict({"file": [uploaded]})
    response = client.post("/users/avatar", data={}, FILES=files, headers=headers)
    assert response.status_code == 400
    assert "not a valid image" in response.json()["detail"].lower()

@pytest.mark.django_db
def test_avatar_delete_unauthenticated():
    response = client.delete("/users/avatar")
    assert response.status_code == 401
    assert (
        "authentication required" in response.json()["detail"].lower()
        or "unauthorized" in response.json()["detail"].lower()
    )

@pytest.mark.django_db
def test_avatar_delete_authenticated(monkeypatch):
    user = create_test_user(email="delavatar@example.com", password="pw")
    user.avatar_path = "avatars/delme.webp"
    user.save()
    response = client.post("/token/pair", json={"email": "delavatar@example.com", "password": "pw"})
    access = response.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    called = {}
    def fake_delete_existing_avatar(u):
        called["deleted"] = True
        assert u.id == user.id
    monkeypatch.setattr("accounts.users_api.delete_existing_avatar", fake_delete_existing_avatar)
    response = client.delete("/users/avatar", headers=headers)
    assert response.status_code == 200
    assert "deleted" in response.json()["detail"].lower()
    assert called.get("deleted") is True
    user.refresh_from_db()
    assert user.avatar_path is None

@pytest.mark.django_db
def test_avatar_delete_when_no_avatar(monkeypatch):
    user = create_test_user(email="noavatar@example.com", password="pw")
    user.avatar_path = None
    user.save()
    response = client.post("/token/pair", json={"email": "noavatar@example.com", "password": "pw"})
    access = response.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    called = {}
    def fake_delete_existing_avatar(u):
        called["deleted"] = True
        assert u.id == user.id
    monkeypatch.setattr("accounts.users_api.delete_existing_avatar", fake_delete_existing_avatar)
    response = client.delete("/users/avatar", headers=headers)
    assert response.status_code == 200
    assert "deleted" in response.json()["detail"].lower()
    assert called.get("deleted") is True
    user.refresh_from_db()
    assert user.avatar_path is None

@pytest.mark.django_db
def test_avatar_upload_valid(monkeypatch):
    user = create_test_user(email="validavatar@example.com", password="pw")
    response = client.post("/token/pair", json={"email": "validavatar@example.com", "password": "pw"})
    access = response.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    img_buf = create_test_image(format="PNG", size=(128, 128))
    uploaded = SimpleUploadedFile("avatar.png", img_buf.read(), content_type="image/png")
    files = MultiValueDict({"file": [uploaded]})
    # Patch out storage and resize logic to simulate real behavior and capture arguments
    called = {}
    def fake_delete_existing_avatar(u):
        called["deleted"] = True
    def fake_generate_upload_filename(prefix, name, ext=None):
        return f"avatars/tested{ext or ''}"
    def fake_resize_avatar_images(img_bytes):
        called["resized"] = True
        return b"small", b"large"
    def fake_upload_to_storage(filename, data):
        called.setdefault("uploads", []).append((filename, data))
        return f"https://cdn.example.com/{filename}"
    monkeypatch.setattr("accounts.users_api.delete_existing_avatar", fake_delete_existing_avatar)
    monkeypatch.setattr("accounts.users_api.generate_upload_filename", fake_generate_upload_filename)
    monkeypatch.setattr("accounts.users_api.resize_avatar_images", fake_resize_avatar_images)
    monkeypatch.setattr("accounts.users_api.upload_to_storage", fake_upload_to_storage)
    response = client.post("/users/avatar", data={}, FILES=files, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["avatar_url"].endswith("avatars/tested.webp")
    assert data["avatar_large_url"].endswith("avatars/tested_lg.webp")
    assert called.get("deleted") is True
    assert called.get("resized") is True
    assert len(called.get("uploads", [])) == 2
    user.refresh_from_db()
    assert user.avatar_path == "avatars/tested.webp"
