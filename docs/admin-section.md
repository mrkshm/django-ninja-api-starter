# Django Admin Section

This project comes with a Django admin interface for managing users, organizations, contacts, tags, images, and more.

## Setting Up the Admin

To enable and use the admin section, follow these steps:

1. **Apply Migrations:**
   Ensure all migrations are applied, including for the `sites` app:

   ```bash
   python manage.py migrate
   ```

2. **Create a Superuser:**
   Create an admin user who can log in to `/admin`:

   ```bash
   python manage.py createsuperuser
   ```

3. **Create a Site Entry:**
   If you see `Site matching query does not exist`, create a Site object:
   ```python
   from django.contrib.sites.models import Site
   Site.objects.create(domain='localhost:8000', name='localhost')
   ```
   Or use the Django shell:
   ```bash
   python manage.py shell
   ```
   Then run the above Python code.

## Image Uploads in Admin

- **Image uploads are intentionally disabled in the admin.**
- Images must be uploaded via the API, which handles S3 storage and automatic image resizing.
- In the admin, the image file field is read-only and the "Add Image" button is disabled to prevent accidental bypass of these processing steps.

## Customizations

- Admin includes thumbnails for images, improved user management, and sensible filters/search for all major models.
- You can further customize the admin as needed.

## Troubleshooting

- If you see errors about missing `Site` objects, make sure to follow step 3 above.
