# Testing Image Uploads in Django Ninja

This guide explains how to write tests for image (or file) upload endpoints in Django Ninja using the Ninja TestClient. This approach ensures compatibility with Django Ninja's file handling and avoids common pitfalls with multipart form data.

## Key Steps

1. **Use `SimpleUploadedFile` to create in-memory file objects.**
2. **Wrap your file(s) in a `MultiValueDict` from `django.utils.datastructures`.**
3. **Pass the files using the `FILES` parameter to the Ninja TestClient's `post` method.**
4. **Include any authentication headers as needed.**

## Example: Testing an Avatar Upload Endpoint

```python
from django.utils.datastructures import MultiValueDict
from django.core.files.uploadedfile import SimpleUploadedFile
from ninja.testing import TestClient
from PIL import Image
import io

# Setup test user, org, and client as usual...

img = Image.new("RGB", (300, 300), color="red")
buf = io.BytesIO()
img.save(buf, format="PNG")
buf.seek(0)
uploaded = SimpleUploadedFile("avatar.png", buf.getvalue(), content_type="image/png")
files = MultiValueDict({"file": [uploaded]})

response = client.post(
    f"/contacts/{contact.slug}/avatar/",
    data={},  # Add form fields here if needed
    FILES=files,
    headers=headers,  # Include JWT or session auth headers
)

assert response.status_code == 200
```

## Notes

- This approach works for both single and multiple file uploads (just add more files to the MultiValueDict).
- **Do not use the `files=` parameter** (like with requests or FastAPI); always use `FILES=...` with Ninja TestClient.
- For endpoints expecting additional form fields, include them in the `data` parameter.

## Troubleshooting

- If you see errors like `Field required` or the file is missing in your endpoint, double-check that you are using `MultiValueDict` and the `FILES` parameter.
- If you use Django's `Client` instead, authentication context may not be set correctly for Ninja endpoints.

---

This pattern is based on community feedback and is known to work with Django Ninja as of 2025.
