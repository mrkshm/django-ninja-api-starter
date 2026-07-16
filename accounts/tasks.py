import logging

from celery import shared_task
from django.core.management import call_command
from django.utils import timezone

from accounts.models import (
    AuthSession,
    PendingEmailChange,
    PendingPasswordReset,
    PendingRegistration,
)

logger = logging.getLogger(__name__)


@shared_task
def cleanup_expired_tokens():
    now = timezone.now()
    expired_pw = PendingPasswordReset.objects.filter(expires_at__lt=now)
    expired_email = PendingEmailChange.objects.filter(expires_at__lt=now)
    expired_registration = PendingRegistration.objects.filter(expires_at__lt=now)
    expired_sessions = AuthSession.objects.filter(expires_at__lt=now)
    pw_count = expired_pw.count()
    email_count = expired_email.count()
    registration_count = expired_registration.count()
    session_count = expired_sessions.count()
    expired_pw.delete()
    expired_email.delete()
    expired_registration.delete()
    expired_sessions.delete()
    call_command("flushexpiredtokens", verbosity=0)
    logger.info(
        "Deleted expired auth records: password_resets=%s email_changes=%s "
        "registrations=%s sessions=%s.",
        pw_count,
        email_count,
        registration_count,
        session_count,
    )
