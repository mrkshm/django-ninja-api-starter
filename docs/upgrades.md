# Upgrade policy

Dependabot opens weekly grouped updates, but automation does not replace review.
Patch security releases for Django, Pillow, authentication/cryptography,
database drivers, boto3, Redis/Celery, and the container base within 48 hours
when the project is affected. Address other high/critical findings within seven
days.

For each update:

1. Read the upstream changelog or advisory and confirm supported Python,
   PostgreSQL, and Redis versions.
2. Change exact versions through `uv add`/`uv lock`; never hand-edit only the
   lock file.
3. Run the complete verification set and review OpenAPI and migration diffs.
4. Build and scan the image, run the PostgreSQL/Redis CI suite, and exercise
   authentication, image decoding, email publication, and export in staging.
5. Deploy with a backup and observe errors, latency, queues, and authentication
   failures through at least one normal traffic window.

Minor Django/Python upgrades get a dedicated branch and release note. Major
upgrades require following the full deprecation path and should not combine with
unrelated domain changes. Base image and GitHub Action digest updates receive the
same review as application dependencies. Keep the previous immutable application
image until the compatibility window in the deployment guide has passed.
