# Optional PostGIS

The starter defaults to standard PostgreSQL because no included model has a GIS
field. Adding PostGIS later is easier and safer than carrying native GIS
libraries, a specialized image, and an extension in every application that does
not use them.

When a product needs spatial fields:

1. Replace the PostgreSQL image with a pinned, supported PostGIS image.
2. Install matching GEOS/GDAL system libraries in both Docker stages.
3. Change the database engine to `django.contrib.gis.db.backends.postgis` in a
   product-specific settings module.
4. Add `django.contrib.gis` and a migration containing
   `CreateExtension("postgis")` before the first GIS field.
5. Add PostgreSQL/PostGIS CI coverage and spatial indexes for real query shapes.

Do not merely change the database engine: verify container architecture support,
backup/restore compatibility, and extension privileges first.
