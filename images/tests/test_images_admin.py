import pytest
from django.utils.html import format_html
from images.admin import ImageAdmin
from images.models import Image
from django.contrib.admin.sites import AdminSite

class DummyFile:
    def __init__(self, url):
        self.url = url

class DummyObj:
    def __init__(self, file):
        self.file = file

def make_admin():
    return ImageAdmin(Image, AdminSite())

@pytest.mark.parametrize("url,expected_thumb", [
    ("/media/img.jpg", "/media/img_thumb.webp"),
    ("/media/img.jpeg", "/media/img_thumb.webp"),
    ("/media/img.png", "/media/img_thumb.webp"),
    ("/media/img.webp", "/media/img_thumb.webp"),
    ("/media/img.gif", "/media/img_thumb.webp"),
    ("/media/img.unknown", "/media/img.unknown"),
])
def test_thumbnail_url_generation(url, expected_thumb):
    obj = DummyObj(DummyFile(url))
    admin = make_admin()
    html = admin.thumbnail(obj)
    assert expected_thumb in html or (expected_thumb == url and html)
    assert html.startswith("<img src=")
    assert "width=\"60\"" in html
    assert "object-fit:cover" in html


def test_thumbnail_no_file():
    obj = DummyObj(None)
    admin = make_admin()
    html = admin.thumbnail(obj)
    assert html == ""
