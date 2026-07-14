from django.http import HttpResponse
from django.test import Client, RequestFactory
from django.urls import resolve

from DjangoApiStarter.middleware import HealthCheckMiddleware

def test_health_check_url():
    client = Client()
    response = client.get("/kamal/up/")
    assert response.status_code == 200
    assert response.content == b"OK"
    # Optionally check that the view is correctly resolved
    match = resolve("/kamal/up/")
    assert match.func.__name__ == "health_check"


def test_health_check_middleware_logs_only_health_checks(caplog, capsys):
    def get_response(request):
        return HttpResponse("next")

    middleware = HealthCheckMiddleware(get_response)
    request = RequestFactory().get("/api/v1/contacts/")

    response = middleware(request)

    assert response.content == b"next"
    assert "HealthCheckMiddleware" not in caplog.text
    assert capsys.readouterr().out == ""


def test_health_check_middleware_returns_ok_and_debug_logs(caplog, capsys):
    def get_response(request):
        raise AssertionError("health check should not reach downstream handler")

    middleware = HealthCheckMiddleware(get_response)
    request = RequestFactory().get("/kamal/up/")

    with caplog.at_level("DEBUG", logger="django.healthcheck"):
        response = middleware(request)

    assert response.status_code == 200
    assert response.content == b"OK"
    assert "Health check: path=/kamal/up/" in caplog.text
    assert capsys.readouterr().out == ""
