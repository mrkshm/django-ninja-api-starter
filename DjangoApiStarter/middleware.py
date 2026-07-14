from django.http import HttpResponse
import logging

class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("django.healthcheck")

    def __call__(self, request):
        if request.path == "/kamal/up/":
            self.logger.debug("Health check: path=%s", request.path)
            return HttpResponse("OK")
        return self.get_response(request)
