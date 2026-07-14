from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.template import Context, Template


def render_email_template(template_name, context):
    template_path = settings.BASE_DIR / "core" / "email_templates" / template_name
    template = Template(template_path.read_text())
    rendered = template.render(Context(context))
    subject, body_text = rendered.split("\n", 1)
    subject = subject.replace("Subject: ", "").strip()
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
