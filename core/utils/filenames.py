from __future__ import annotations

import os
from datetime import datetime, timezone

from django.utils.crypto import get_random_string


def generate_upload_filename(
    prefix: str,
    original_name: str,
    ext: str | None = None,
) -> str:
    """Generate a timestamped, randomized storage filename."""
    base, original_extension = os.path.splitext(original_name)
    base = base[:12]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    random_suffix = get_random_string(6)
    extension = ext if ext is not None else original_extension
    parts = [part for part in (prefix, base, timestamp, random_suffix) if part]
    return "-".join(parts) + extension.lower()
