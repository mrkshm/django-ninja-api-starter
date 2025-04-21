import pytest
from organizations.models import Organization
from core.utils import make_it_unique, generate_upload_filename
import re
from datetime import datetime, timezone


@pytest.mark.django_db
def test_make_it_unique_returns_base_if_unique():
    unique = make_it_unique('foo', Organization, 'slug')
    assert unique == 'foo'
    Organization.objects.create(name='Test Org', slug=unique, type='personal')
    # Now 'foo' is taken, next call should return different value
    unique2 = make_it_unique('foo', Organization, 'slug')
    assert unique2 != 'foo'
    assert unique2.startswith('foo')
    Organization.objects.create(name='Test Org 2', slug=unique2, type='personal')
    # Try again, should return yet another unique value
    unique3 = make_it_unique('foo', Organization, 'slug')
    assert unique3 not in [unique, unique2]
    assert unique3.startswith('foo')

@pytest.mark.django_db
def test_make_it_unique_handles_long_base():
    base = 'x' * 45  # 45 chars, leaves room for suffix
    Organization.objects.create(name='Long Org', slug=base, type='personal')
    unique = make_it_unique(base, Organization, 'slug')
    assert unique != base
    assert unique.startswith(base)
    assert len(unique) <= 50  # SlugField default max_length is 50

def test_generate_upload_filename_prefix_and_truncation():
    name = generate_upload_filename('avatar', 'averylongfilenameforavatar.jpg')
    # Should start with 'avatar-'
    assert name.startswith('avatar-')
    # Truncated base name should be 12 chars
    base = name.split('-')[1]
    assert len(base) == 12
    # Should end with .jpg
    assert name.endswith('.jpg')

def test_generate_upload_filename_no_prefix():
    name = generate_upload_filename('', 'testfile.png')
    # Should not start with _
    assert not name.startswith('_')
    assert name.endswith('.png')

def test_generate_upload_filename_timestamp_and_rand():
    name = generate_upload_filename('doc', 'file.docx')
    parts = name.rsplit('.', 1)[0].split('-')
    # Should have 4 parts: prefix, base, timestamp, rand
    assert len(parts) == 4
    # Timestamp format check
    ts = parts[2]
    dt = datetime.strptime(ts, '%Y%m%dT%H%M%S')
    # Rand is 6 chars
    assert len(parts[3]) == 6


def test_generate_upload_filename_uniqueness():
    names = {generate_upload_filename('avatar', 'dup.png') for _ in range(10)}
    assert len(names) == 10


def test_generate_upload_filename_extension_case():
    name = generate_upload_filename('avatar', 'MyPic.JPEG')
    assert name.endswith('.jpeg')


def test_generate_upload_filename_no_double_underscore():
    name = generate_upload_filename('', 'pic.jpg')
    assert '__' not in name


def test_generate_upload_filename_with_custom_extension():
    name = generate_upload_filename('report', 'summary.txt', ext='.pdf')
    assert name.endswith('.pdf')
    assert '-summary-' in name  # base name truncated and present
    assert name.startswith('report-')
    # Should not contain original extension
    assert '.txt' not in name
