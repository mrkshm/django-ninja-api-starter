from celery import shared_task
from django.utils import timezone
from accounts.models import PendingPasswordReset, PendingEmailChange
import logging

logger = logging.getLogger(__name__)

@shared_task
def cleanup_expired_tokens():
    now = timezone.now()
    expired_pw = PendingPasswordReset.objects.filter(expires_at__lt=now)
    expired_email = PendingEmailChange.objects.filter(expires_at__lt=now)
    pw_count = expired_pw.count()
    email_count = expired_email.count()
    expired_pw.delete()
    expired_email.delete()
    logger.info(f"Deleted {pw_count} expired password reset tokens and {email_count} expired email change tokens.")
