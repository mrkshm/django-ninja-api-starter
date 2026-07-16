import logging

from ninja import Router

router = Router(tags=["images"])
logger = logging.getLogger("audit")
