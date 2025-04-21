import os
from django.core.mail import EmailMultiAlternatives, get_connection
from django.conf import settings

# Utility to send email using Django's EmailMultiAlternatives (works with SES or SMTP)
def send_email(subject, to_email, body_text, body_html=None):
    from_email = settings.DEFAULT_FROM_EMAIL
    connection = get_connection(
        host=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        username=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_tls=settings.EMAIL_USE_TLS,
        use_ssl=settings.EMAIL_USE_SSL,
    )
    msg = EmailMultiAlternatives(subject, body_text, from_email, [to_email], connection=connection)
    if body_html:
        msg.attach_alternative(body_html, "text/html")
    msg.send()
