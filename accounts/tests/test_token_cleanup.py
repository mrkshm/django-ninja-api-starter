import pytest
from django.utils import timezone
from accounts.models import (
    AuthSession,
    PendingEmailChange,
    PendingPasswordReset,
    PendingRegistration,
    User,
)
from accounts.tasks import cleanup_expired_tokens

@pytest.mark.django_db
def test_cleanup_expired_tokens():
    user = User.objects.create_user(email="test@example.com", password="pw")
    now = timezone.now()
    # Create expired tokens
    pw_expired = PendingPasswordReset.objects.create(user=user, token="pw1", expires_at=now - timezone.timedelta(hours=1))
    email_expired = PendingEmailChange.objects.create(user=user, new_email="new@example.com", token="em1", expires_at=now - timezone.timedelta(hours=1))
    registration_expired = PendingRegistration.objects.create(
        user=user,
        token="reg1",
        expires_at=now - timezone.timedelta(hours=1),
    )
    session_expired = AuthSession.objects.create(
        user=user,
        auth_version=user.auth_version,
        expires_at=now - timezone.timedelta(hours=1),
    )
    # Create valid (not expired) tokens
    pw_valid = PendingPasswordReset.objects.create(user=user, token="pw2", expires_at=now + timezone.timedelta(hours=1))
    email_valid = PendingEmailChange.objects.create(user=user, new_email="new2@example.com", token="em2", expires_at=now + timezone.timedelta(hours=1))
    # Run the cleanup task
    cleanup_expired_tokens()
    # Only non-expired tokens should remain
    assert PendingPasswordReset.objects.filter(pk=pw_expired.pk).count() == 0
    assert PendingEmailChange.objects.filter(pk=email_expired.pk).count() == 0
    assert PendingRegistration.objects.filter(pk=registration_expired.pk).count() == 0
    assert AuthSession.objects.filter(pk=session_expired.pk).count() == 0
    assert PendingPasswordReset.objects.filter(pk=pw_valid.pk).count() == 1
    assert PendingEmailChange.objects.filter(pk=email_valid.pk).count() == 1
