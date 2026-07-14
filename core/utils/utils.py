import os
from datetime import datetime, timezone
from typing import Optional
from django.utils.crypto import get_random_string


def make_it_unique(base_value, model, field_name, exclude_pk=None):
    """
    Returns a unique value for `field_name` in `model`, starting from base_value.
    If exclude_pk is provided, excludes that pk from the uniqueness check (useful for updates).
    """
    field = model._meta.get_field(field_name)
    max_length = getattr(field, "max_length", None)
    base_value = str(base_value)
    if max_length:
        base_value = base_value[:max_length]

    # Reserve generous suffix room so max-length bases still find prior values
    # such as "<base truncated>-1" in the same single query.
    lookup_prefix = base_value[: max(1, max_length - 32)] if max_length else base_value
    qs = model.objects.filter(**{f"{field_name}__startswith": lookup_prefix})
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    existing_values = set(qs.values_list(field_name, flat=True))

    def fit(value, suffix=None):
        if suffix is None:
            return value
        suffix_text = f"-{suffix}"
        if max_length:
            return f"{value[: max_length - len(suffix_text)]}{suffix_text}"
        return f"{value}{suffix_text}"

    candidate = fit(base_value)
    counter = 1
    while candidate in existing_values:
        candidate = fit(base_value, counter)
        counter += 1
    return candidate


def generate_upload_filename(
    prefix: str, original_name: str, ext: Optional[str] = None
) -> str:
    """
    Generate a unique filename for uploads.
    - prefix: string to prepend (e.g. 'avatar', 'doc', or '').
    - original_name: original filename (extension is preserved, base name truncated to 12 chars).
    - ext: override extension (should include dot, e.g. '.webp').
    """
    base, orig_ext = os.path.splitext(original_name)
    base = base[:12]  # Truncate base name
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    rand = get_random_string(6)
    extension = ext if ext is not None else orig_ext
    parts = [p for p in [prefix, base, timestamp, rand] if p]
    return "-".join(parts) + extension.lower()
