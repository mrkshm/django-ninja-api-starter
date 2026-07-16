import pytest
from django.conf import settings

from core.email_utils import (
    EmailTemplateFormatError,
    _load_email_template,
    render_email_template,
    send_email,
)


def test_render_email_template_returns_subject_and_body(settings):
    settings.PROJECT_NAME = "Django API Starter"

    subject, body = render_email_template(
        "registration_verification.txt",
        {
            "project_name": settings.PROJECT_NAME,
            "user_display_name": "Ada",
            "verification_link": "https://example.test/verify",
        },
    )

    assert subject
    assert "Subject:" not in subject
    assert "Ada" in body
    assert "https://example.test/verify" in body


def test_render_email_template_rejects_missing_subject_line(settings, tmp_path):
    template_dir = tmp_path / "core" / "email_templates"
    template_dir.mkdir(parents=True)
    (template_dir / "invalid.txt").write_text("Body without a subject")
    settings.BASE_DIR = tmp_path
    _load_email_template.cache_clear()

    with pytest.raises(EmailTemplateFormatError, match="Subject: line"):
        render_email_template("invalid.txt", {})


def test_render_email_template_caches_compiled_template(settings, tmp_path):
    template_dir = tmp_path / "core" / "email_templates"
    template_dir.mkdir(parents=True)
    template_path = template_dir / "cached.txt"
    template_path.write_text("Subject: First\nFirst body")
    settings.BASE_DIR = tmp_path
    _load_email_template.cache_clear()

    assert render_email_template("cached.txt", {}) == ("First", "First body")
    template_path.write_text("Subject: Second\nSecond body")
    assert render_email_template("cached.txt", {}) == ("First", "First body")

    _load_email_template.cache_clear()
    assert render_email_template("cached.txt", {}) == ("Second", "Second body")


def test_send_email_uses_configured_backend(monkeypatch):
    settings.DEFAULT_FROM_EMAIL = "sender@example.com"
    called = {}

    def fake_email_multi(subject, body_text, from_email, to_list):
        called["subject"] = subject
        called["body_text"] = body_text
        called["from_email"] = from_email
        called["to_list"] = to_list

        class DummyMsg:
            def attach_alternative(self, html, mimetype):
                called["attached_html"] = (html, mimetype)

            def send(self):
                called["sent"] = True

        return DummyMsg()

    monkeypatch.setattr("core.email_utils.EmailMultiAlternatives", fake_email_multi)
    # Plain text only
    send_email("Sub", "to@example.com", "bodytext")
    assert called["from_email"] == "sender@example.com"
    assert called["to_list"] == ["to@example.com"]
    assert called["subject"] == "Sub"
    assert called["body_text"] == "bodytext"
    assert called["sent"] is True
    # With HTML
    called.clear()
    send_email("Sub2", "to2@example.com", "plain", body_html="<b>html</b>")
    assert called["attached_html"] == ("<b>html</b>", "text/html")
    assert called["sent"] is True
