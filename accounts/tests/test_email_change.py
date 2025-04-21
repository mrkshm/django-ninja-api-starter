import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model
from ninja.testing import TestClient
from DjangoApiStarter.api import api
from ninja.main import NinjaAPI
from accounts.models import PendingEmailChange

User = get_user_model()
client = TestClient(api)

@pytest.fixture(autouse=True)
def clear_ninjaapi_registry():
    NinjaAPI._registry.clear()

@pytest.mark.django_db
def test_request_email_change_success(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    user = User.objects.create_user(email='old@example.com', password='pw')
    resp = client.post('/token/pair', json={'email': 'old@example.com', 'password': 'pw'})
    access = resp.json()['access']
    headers = {'Authorization': f'Bearer {access}'}
    resp = client.patch('/auth/email', json={'email': 'new@example.com'}, headers=headers)
    assert resp.status_code == 200
    assert 'Verification email sent' in resp.json()['detail']
    pending = PendingEmailChange.objects.get(user=user)
    assert pending.new_email == 'new@example.com'
    assert not pending.is_expired()

@pytest.mark.django_db
def test_verify_email_change_success(settings):
    user = User.objects.create_user(email='old2@example.com', password='pw')
    token = 'testtoken123'
    expires = timezone.now() + timezone.timedelta(hours=1)
    PendingEmailChange.objects.create(user=user, new_email='new2@example.com', token=token, expires_at=expires)
    resp = client.get(f'/auth/email/verify?token={token}')
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.email == 'new2@example.com'
    assert not PendingEmailChange.objects.filter(user=user).exists()

@pytest.mark.django_db
def test_verify_email_change_expired_token(settings):
    user = User.objects.create_user(email='expired@example.com', password='pw')
    token = 'expiredtoken123'
    # Set expires_at in the past
    expires = timezone.now() - timezone.timedelta(hours=1)
    PendingEmailChange.objects.create(user=user, new_email='expired2@example.com', token=token, expires_at=expires)
    resp = client.get(f'/auth/email/verify?token={token}')
    assert resp.status_code == 400 or resp.status_code == 410
    assert 'expired' in resp.json()['detail'].lower() or 'invalid' in resp.json()['detail'].lower()

@pytest.mark.django_db
def test_verify_email_change_invalid_token(settings):
    user = User.objects.create_user(email='invalidtoken@example.com', password='pw')
    # Do NOT create any PendingEmailChange with this token
    token = 'doesnotexisttoken'
    resp = client.get(f'/auth/email/verify?token={token}')
    assert resp.status_code == 400 or resp.status_code == 404
    assert 'invalid' in resp.json()['detail'].lower() or 'not found' in resp.json()['detail'].lower()

@pytest.mark.django_db
def test_request_email_change_invalid_format(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    user = User.objects.create_user(email='invalid1@example.com', password='pw')
    resp = client.post('/token/pair', json={'email': 'invalid1@example.com', 'password': 'pw'})
    access = resp.json()['access']
    headers = {'Authorization': f'Bearer {access}'}
    resp = client.patch('/auth/email', json={'email': 'not-an-email'}, headers=headers)
    assert resp.status_code == 400
    assert 'Invalid email address' in resp.json()['detail']

@pytest.mark.django_db
def test_request_email_change_email_taken(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    user1 = User.objects.create_user(email='taken@example.com', password='pw')
    user2 = User.objects.create_user(email='user2@example.com', password='pw')
    resp = client.post('/token/pair', json={'email': 'user2@example.com', 'password': 'pw'})
    access = resp.json()['access']
    headers = {'Authorization': f'Bearer {access}'}
    resp = client.patch('/auth/email', json={'email': 'taken@example.com'}, headers=headers)
    assert resp.status_code == 400
    assert 'Email already taken' in resp.json()['detail']

@pytest.mark.django_db
def test_multiple_pending_changes(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    user = User.objects.create_user(email='multi@example.com', password='pw')
    resp = client.post('/token/pair', json={'email': 'multi@example.com', 'password': 'pw'})
    access = resp.json()['access']
    headers = {'Authorization': f'Bearer {access}'}
    # First request
    resp1 = client.patch('/auth/email', json={'email': 'first@example.com'}, headers=headers)
    assert resp1.status_code == 200
    # Second request before verifying
    resp2 = client.patch('/auth/email', json={'email': 'second@example.com'}, headers=headers)
    assert resp2.status_code == 200
    # Only one pending change should exist
    pendings = PendingEmailChange.objects.filter(user=user)
    assert pendings.count() == 1
    assert pendings.first().new_email == 'second@example.com'

@pytest.mark.django_db
def test_email_change_after_verification(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    user = User.objects.create_user(email='afterverify@example.com', password='pw')
    token = 'verifytoken123'
    expires = timezone.now() + timezone.timedelta(hours=1)
    PendingEmailChange.objects.create(user=user, new_email='afterverify2@example.com', token=token, expires_at=expires)
    resp = client.get(f'/auth/email/verify?token={token}')
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.email == 'afterverify2@example.com'
    assert not PendingEmailChange.objects.filter(user=user).exists()

@pytest.mark.django_db
def test_case_insensitive_email_uniqueness(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    User.objects.create_user(email='caseuser@example.com', password='pw')
    user2 = User.objects.create_user(email='other@example.com', password='pw')
    resp = client.post('/token/pair', json={'email': 'other@example.com', 'password': 'pw'})
    access = resp.json()['access']
    headers = {'Authorization': f'Bearer {access}'}
    # Try to change to same email with different case
    resp = client.patch('/auth/email', json={'email': 'CaseUser@Example.com'}, headers=headers)
    assert resp.status_code == 400
    assert 'Email already taken' in resp.json()['detail']

@pytest.mark.django_db
def test_reusing_token_after_success(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    user = User.objects.create_user(email='reuse@example.com', password='pw')
    token = 'reusetoken123'
    expires = timezone.now() + timezone.timedelta(hours=1)
    PendingEmailChange.objects.create(user=user, new_email='reuse2@example.com', token=token, expires_at=expires)
    # First use (should succeed)
    resp1 = client.get(f'/auth/email/verify?token={token}')
    assert resp1.status_code == 200
    user.refresh_from_db()
    assert user.email == 'reuse2@example.com'
    # Second use (should fail)
    resp2 = client.get(f'/auth/email/verify?token={token}')
    assert resp2.status_code == 400 or resp2.status_code == 404
    assert 'invalid' in resp2.json()['detail'].lower() or 'not found' in resp2.json()['detail'].lower()

def test_request_email_change_unauthenticated(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    resp = client.patch('/auth/email', json={'email': 'unauth@example.com'})
    assert resp.status_code == 401
    # Optionally check error message
