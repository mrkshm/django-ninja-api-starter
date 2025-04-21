import random
import string
import os
from datetime import datetime, timezone
from django.utils.crypto import get_random_string

def make_it_unique(base_value, model, field_name, exclude_pk=None):
    """
    Returns a unique value for `field_name` in `model`, starting from base_value.
    If exclude_pk is provided, excludes that pk from the uniqueness check (useful for updates).
    """
    value = base_value
    i = 1
    q = {field_name: value}
    qs = model.objects.filter(**q)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    while qs.exists():
        value = f"{base_value}-{i}"
        q[field_name] = value
        qs = model.objects.filter(**q)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        i += 1
    return value

def generate_upload_filename(prefix: str, original_name: str, ext: str = None) -> str:
    """
    Generate a unique filename for uploads.
    - prefix: string to prepend (e.g. 'avatar', 'doc', or '').
    - original_name: original filename (extension is preserved, base name truncated to 12 chars).
    - ext: override extension (should include dot, e.g. '.webp').
    """
    base, orig_ext = os.path.splitext(original_name)
    base = base[:12]  # Truncate base name
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    rand = get_random_string(6)
    extension = ext if ext is not None else orig_ext
    parts = [p for p in [prefix, base, timestamp, rand] if p]
    return "-".join(parts) + extension.lower()