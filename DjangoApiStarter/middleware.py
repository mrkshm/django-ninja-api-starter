from django.http import HttpResponse
import logging
from django.conf import settings

class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("django.healthcheck")

    def __call__(self, request):
        # Log the path and APPEND_SLASH value
        self.logger.warning(f"HealthCheckMiddleware: path={request.path} APPEND_SLASH={getattr(settings, 'APPEND_SLASH', None)}")
        print(f"HealthCheckMiddleware: path={request.path} APPEND_SLASH={getattr(settings, 'APPEND_SLASH', None)}")
        if request.path == "/kamal/up/":
            return HttpResponse("OK")
        return self.get_response(request)
