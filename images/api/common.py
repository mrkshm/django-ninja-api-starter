import logging

from ninja import Router

from organizations.scope import resolve_org_scope

router = Router(tags=["images"])
logger = logging.getLogger("audit")


def get_org_for_request(request, org_slug):
    return resolve_org_scope(request, org_slug).org


def get_org_scope_for_request(request, org_slug):
    return resolve_org_scope(request, org_slug)
