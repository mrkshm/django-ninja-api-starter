# Deployment with Kamal

This project uses [Kamal](https://kamal-deploy.com/) for deployment.

## Prerequisites

- Ruby must be installed on your system.
- Kamal must be installed. See the [Kamal installation guide](https://kamal-deploy.com/docs/installation/) for instructions.
- If you don't want to install Ruby, other good options for deployment are [Dokku](https://dokku.com/) and [Dokploy](https://dokploy.com/).

## Single-Server Deployment

The default `config/deploy.yml` deploys the web server, Celery worker, Postgres, and Redis to a single server.

## How to Deploy

1. Edit `config/deploy.yml`:

   - Set your server IP, Docker image, and update the `clear:` section with your environment values or keep the examples.
   - Non-sensitive config is set directly under `clear:`.
   - Secrets are listed under `secret:` and must be set in `.kamal/secrets`.

2. Edit `.kamal/secrets`:

   - Add values for each secret variable listed in the `secret:` section of your `deploy.yml`.
   - Example:
     ```env
     SECRET_KEY=your-production-secret-key
     POSTGRES_PASSWORD=your-db-password
     R2_ACCESS_KEY_ID=your-access-key
     R2_SECRET_ACCESS_KEY=your-secret-access-key
     EMAIL_HOST_PASSWORD=your-email-password
     ```
   - Do not commit real secrets to version control.

3. Deploy:
   - Run:
     ```sh
     kamal deploy
     ```

## Environment Variable Management

- All required environment variables are defined in `config/deploy.yml`.
- Non-sensitive variables are set in `clear:`. Edit these as needed.
- Sensitive variables are referenced in `secret:` and set in `.kamal/secrets`.

## Notes

- For more information or multi-server setups, see the [Kamal documentation](https://kamal-deploy.com/).
- [Dokku](https://dokku.com/) and [Dokploy](https://dokploy.com/) are also good alternatives for deploying Django projects.

## References

- [Kamal Docs](https://kamal-deploy.com/docs/)
- [Django Deployment Checklist](https://docs.djangoproject.com/en/stable/howto/deployment/checklist/)
- [Celery Deployment Guide](https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html)
