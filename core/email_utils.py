from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import Context, Template


class EmailTemplateFormatError(ValueError):
    pass


@lru_cache(maxsize=32)
def _load_email_template(template_path: str) -> Template:
    return Template(Path(template_path).read_text(encoding="utf-8"))


def render_email_template(template_name, context):
    template_path = settings.BASE_DIR / "core" / "email_templates" / template_name
    template = _load_email_template(str(template_path))
    rendered = template.render(Context(context))
    subject_line, separator, body_text = rendered.partition("\n")
    if not separator or not subject_line.startswith("Subject:"):
        raise EmailTemplateFormatError(
            f"Email template {template_name!r} must begin with a Subject: line."
        )
    subject = subject_line.removeprefix("Subject:").strip()
    if not subject:
        raise EmailTemplateFormatError(
            f"Email template {template_name!r} has an empty subject."
        )
    return subject, body_text.strip()


def send_email(subject, to_email, body_text, body_html=None):
    msg = EmailMultiAlternatives(
        subject,
        body_text,
        settings.DEFAULT_FROM_EMAIL,
        [to_email],
    )
    if body_html:
        msg.attach_alternative(body_html, "text/html")
    return msg.send()
