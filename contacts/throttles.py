from django.conf import settings
from ninja.throttling import UserRateThrottle


class ContactSearchRateThrottle(UserRateThrottle):
    scope = "contacts_search"

    def allow_request(self, request, view=None):
        if not request.GET.get("search", "").strip():
            return True
        return super().allow_request(request)


contact_search_throttle = ContactSearchRateThrottle(
    getattr(settings, "CONTACTS_RATE_LIMIT_SEARCH", "60/m")
)
