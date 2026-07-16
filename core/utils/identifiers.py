from __future__ import annotations

from django.db import models


def make_it_unique(
    base_value: object,
    model: type[models.Model],
    field_name: str,
    exclude_pk: int | None = None,
) -> str:
    """Return an available field value derived from ``base_value``."""
    field = model._meta.get_field(field_name)
    max_length = getattr(field, "max_length", None)
    value = str(base_value)
    if max_length:
        value = value[:max_length]

    lookup_prefix = value[: max(1, max_length - 32)] if max_length else value
    queryset = model._default_manager.filter(
        **{f"{field_name}__startswith": lookup_prefix}
    )
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    existing_values = set(queryset.values_list(field_name, flat=True))

    def fit(suffix: int | None = None) -> str:
        if suffix is None:
            return value
        suffix_text = f"-{suffix}"
        if max_length:
            return f"{value[: max_length - len(suffix_text)]}{suffix_text}"
        return f"{value}{suffix_text}"

    candidate = fit()
    counter = 1
    while candidate in existing_values:
        candidate = fit(counter)
        counter += 1
    return candidate
