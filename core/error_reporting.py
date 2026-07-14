"""Small provider-neutral exception reporting boundary.

Replace or wrap ``report_exception`` when integrating Sentry, Honeybadger, or
another provider. Keeping the boundary local avoids coupling domain code to an
observability vendor.
"""

from collections.abc import Mapping
from typing import Any


def report_exception(
    exception: BaseException, *, context: Mapping[str, Any] | None = None
) -> None:
    """Report an exception to an external provider when one is configured."""

    # Intentionally a no-op in the starter. Production projects should connect
    # their provider here and must not include credentials, tokens, or bodies.
    return None
