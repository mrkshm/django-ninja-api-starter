import orjson
from ninja import NinjaAPI
from ninja.renderers import BaseRenderer
from ninja_extra import NinjaExtraAPI
from ninja_jwt.controller import NinjaJWTDefaultController
from accounts.api import auth_router
from accounts.users_api import users_router
from contacts.api import contacts_router
from tags.api import get_tags_router
from images.api import router as images_router, custom_validation_error
from ninja.errors import ValidationError as NinjaValidationError
from organizations.api_export import export_router

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
    description="A modern Django API with JWT authentication"
)

# Register custom JWT controller with email verification check
from accounts.api import CustomJWTController
api.register_controllers(CustomJWTController)

# Add health check to main API instance
@api.get("/health/")
def health_check(request):
    return {"status": "ok"}

api.add_router("/auth/", auth_router, tags=["auth"])
api.add_router("/users/", users_router, tags=["users"])
api.add_router("/contacts/", contacts_router, tags=["contacts"])
api.add_router("/", get_tags_router(), tags=["tags"])
api.add_router("/images/", images_router)
api.add_router("/orgs/", export_router, tags=["organization", "export"])
# Register error handlers (especially for validation errors)
api.add_exception_handler(NinjaValidationError, custom_validation_error)
# Register fallback path for NinjaAPI for bulk endpoints
from django.urls import path, include
from django.conf.urls import handler404, handler500