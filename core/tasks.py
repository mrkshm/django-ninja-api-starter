from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_email_task(self, subject, message, recipient_list, from_email=None, html_message=None):
    """
    Celery task to send an email asynchronously using Django's email backend.
    Usage:
        send_email_task.delay(subject, message, recipient_list, from_email, html_message)
    Args:
        subject (str): Email subject
        message (str): Plain text message
        recipient_list (list[str]): List of recipient email addresses
        from_email (str, optional): Sender address (defaults to settings.DEFAULT_FROM_EMAIL)
        html_message (str, optional): HTML message body
    """
    if from_email is None:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'webmaster@localhost')
    send_mail(
        subject,
        message,
        from_email,
        recipient_list,
        fail_silently=False,
        html_message=html_message,
    )