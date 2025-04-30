# Deployment with Kamal

This project is ready for deployments using [Kamal](https://kamal-deploy.com/).

## Single-Server (Default)

The default `kamal.yml` deploys everything (web, Celery worker, Postgres, Redis) to a single server. This is ideal for:

- MVPs, prototypes, and small production apps
- Fast, simple setup
- Low cost (can run on a single VPS)

**How to use:**

1. Edit `kamal.yml` and set your server IP, Docker image, and secrets.
2. Run `kamal deploy` to build and launch the stack.

## Scaling Up: Multi-Server Example

When you need more robustness or performance, you can split your services:

```yaml
# kamal.multi-server.example.yml
service: django-api-starter
image: yourdockerhubuser/django-api-starter:latest
servers:
  web:
    hosts:
      - 203.0.113.100 # app server 1
      - 203.0.113.101 # app server 2
    roles:
      - web
      - worker
    env: { ... }
  db:
    hosts:
      - 203.0.113.200 # db/redis server
    roles:
      - db
      - redis
    env: { ... }
roles:
  web:
    cmd: gunicorn DjangoApiStarter.asgi:application -b 0.0.0.0:8000 -w 4 -k uvicorn.workers.UvicornWorker
    ports:
      - 80:8000
  worker:
    cmd: celery -A DjangoApiStarter worker -l info
  db:
    image: postgres:15
    ports:
      - 5432:5432
  redis:
    image: redis:7
    ports:
      - 6379:6379
```

**Tips:**

- Keep DB and Redis on a private server not exposed to the public internet.
- Use firewall rules to restrict access.
- For high availability, use a managed Postgres/Redis service or add replication.
- You can add a staging app server by copying the web/worker config and using different env vars.

## Secrets & Environment Variables

- Store secrets in Kamal’s encrypted secrets store or as environment variables.
- Never commit secrets to version control.

## Backups

- Set up regular Postgres dumps and sync to S3 or another backup location.

## Monitoring

- Monitor CPU, RAM, and disk usage.
- Upgrade your server or scale horizontally as needed.

## References

- [Kamal Docs](https://kamal-deploy.com/docs/)
- [Django Deployment Checklist](https://docs.djangoproject.com/en/stable/howto/deployment/checklist/)
- [Celery Deployment Guide](https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html)
