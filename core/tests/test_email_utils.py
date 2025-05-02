import pytest
from django.conf import settings
from core.email_utils import send_email

def test_send_email_uses_default_from_email_and_connection(monkeypatch):
    settings.DEFAULT_FROM_EMAIL = 'sender@example.com'
    settings.EMAIL_HOST = 'smtp.example.com'
    settings.EMAIL_PORT = 587
    settings.EMAIL_HOST_USER = 'user'
    settings.EMAIL_HOST_PASSWORD = 'pw'
    settings.EMAIL_USE_TLS = True
    settings.EMAIL_USE_SSL = False
    called = {}
    def fake_get_connection(**kwargs):
        called['connection'] = kwargs
        class DummyConn: pass
        return DummyConn()
    def fake_email_multi(subject, body_text, from_email, to_list, connection=None):
        called['subject'] = subject
        called['body_text'] = body_text
        called['from_email'] = from_email
        called['to_list'] = to_list
        called['connection'] = connection
        class DummyMsg:
            def attach_alternative(self, html, mimetype):
                called['attached_html'] = (html, mimetype)
            def send(self):
                called['sent'] = True
        return DummyMsg()
    monkeypatch.setattr('core.email_utils.get_connection', fake_get_connection)
    monkeypatch.setattr('core.email_utils.EmailMultiAlternatives', fake_email_multi)
    # Plain text only
    send_email('Sub', 'to@example.com', 'bodytext')
    assert called['from_email'] == 'sender@example.com'
    assert called['to_list'] == ['to@example.com']
    assert called['subject'] == 'Sub'
    assert called['body_text'] == 'bodytext'
    assert called['sent'] is True
    # With HTML
    called.clear()
    send_email('Sub2', 'to2@example.com', 'plain', body_html='<b>html</b>')
    assert called['attached_html'] == ('<b>html</b>', 'text/html')
    assert called['sent'] is True