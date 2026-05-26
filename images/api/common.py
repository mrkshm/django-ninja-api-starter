import logging

from ninja import Router

from core.utils.polymorphic import resolve_org_for_request


router = Router(tags=["images"])
logger = logging.getLogger("audit")


def get_org_for_request(request, org_slug):
    return resolve_org_for_request(request, org_slug)
