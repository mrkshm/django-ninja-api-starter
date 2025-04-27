# Sharing Model Brainstorm

## Generic Share Model Concept

- **Do NOT create a new organization for each share event.**
  - Orgs are for persistent groups, not ad-hoc sharing.
  - Creating a "sharing_org" for every share would bloat the org table and confuse users.

## Recommended Approach: Generic Share Model

- Use a single, flexible `Share` model (possibly with Django's contenttypes framework) to represent sharing any object (contact, file, etc.) between users or orgs.

### Example Model

```python
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

class Share(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    shared_by = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='shares_given')
    shared_with = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='shares_received')
    permissions = models.CharField(max_length=20, default="view")  # e.g., view, edit
    membership_only = models.BooleanField(default=False)
    active = models.BooleanField(default=True)  # If revoked, set to False
    created_at = models.DateTimeField(auto_now_add=True)

    def revoke_if_membership_ended(self):
        if self.membership_only and not self.shared_with.has_active_membership():
            self.active = False
            self.save()
```

- `membership_only`: If True, share is only active while the recipient has an active (paid) membership.
- When a user's membership ends, check and revoke any shares with `membership_only=True`.

## Why Use a Single Model?

- Centralizes sharing logic, easy to extend (add more share types, e.g., time-limited, org-only, etc.).
- Keeps your org and membership models clean.
- API consumers can always check the `membership_only` flag for access logic.

## When to Split Models?

- Only if sharing logic or workflows are radically different (rare).
- For most apps, a single, generic Share model is best.

---

**Summary:**

- Use a generic Share model with a `membership_only` flag for flexible, scalable sharing.
- Avoid creating a new org for every share.
- Handle revocation and access logic in your business layer.
