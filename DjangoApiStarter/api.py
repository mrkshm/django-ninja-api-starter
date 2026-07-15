import orjson
from ninja.errors import HttpError
from ninja.errors import ValidationError as NinjaValidationError
from ninja.renderers import BaseRenderer
from ninja_extra import NinjaExtraAPI

from accounts.api import auth_router, token_router
from accounts.users_api import users_router
from contacts.api import contacts_router
from core.api_errors import (
    http_error_response,
    unhandled_error_response,
    validation_error_response,
)
from images.api import router as images_router
from organizations.api_export import export_router
from tags.api import router as tags_router


# Custom ORJSON Renderer
class ORJSONRenderer(BaseRenderer):
    media_type = "application/json"

    def render(self, request, data, *, response_status):
        return orjson.dumps(data)


# Main API instance with URLs prefixed correctly for Django integration
api = NinjaExtraAPI(
    renderer=ORJSONRenderer(),
    urls_namespace="api",
    version="v1",
    title="Django API Starter",
    description="A modern Django API with JWT authentication",
)

api.add_router("/token", token_router, tags=["token"])
api.add_router("/auth/", auth_router, tags=["auth"])
api.add_router("/users/", users_router, tags=["users"])
api.add_router("/", contacts_router, tags=["contacts"])
api.add_router("/", tags_router, tags=["tags"])
api.add_router("/", images_router)
api.add_router("/", export_router, tags=["organization", "export"])
# Register error handlers (especially for validation errors)
api.add_exception_handler(NinjaValidationError, validation_error_response)
api.add_exception_handler(HttpError, http_error_response)
api.add_exception_handler(Exception, unhandled_error_response)
