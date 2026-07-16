# Production deployment

The supported example is a single Linux server running Docker Compose. Caddy is
the only internet-facing service and terminates TLS. Django, PostgreSQL, and
password-protected Redis share a private Compose network. Web, worker, and beat
run as a non-root user with read-only root filesystems.

This is a sound default for a small product when the server, backups, upgrades,
and monitoring have a named operator. Move to a managed database or an
orchestrator when availability requirements exceed what one host can provide.

## Prepare

1. Install Docker Engine with the Compose plugin.
2. Point the API DNS name at the host and allow inbound TCP 80/443 and UDP 443.
3. Create private and public S3-compatible buckets. Public access must apply
   only to the avatar bucket. Enable versioning where supported.
4. Copy `env.production.example` to a root-readable location outside the Git
   checkout, replace every placeholder, and set `APP_ENV_FILE` to that path.
5. Set `APP_IMAGE` to an immutable registry tag or digest and `DOMAIN` to the
   public hostname in the Compose interpolation environment.

Validate without starting services:

```sh
docker compose --env-file /etc/myapp/compose.env -f compose.production.yaml config --quiet
```

## Release procedure

Build and scan the exact commit in CI, publish it under an immutable tag, then:

```sh
docker compose --env-file /etc/myapp/compose.env -f compose.production.yaml pull
docker compose --env-file /etc/myapp/compose.env -f compose.production.yaml up -d db redis
docker compose --env-file /etc/myapp/compose.env -f compose.production.yaml run --rm web python manage.py migrate --noinput
docker compose --env-file /etc/myapp/compose.env -f compose.production.yaml up -d web worker beat caddy
curl --fail https://api.example.com/health/live/
curl --fail https://api.example.com/health/ready/
```

Migrations are a controlled, one-off release step. Web containers never migrate
on startup. Workers start only after the migration command succeeds.

Before every release, take an encrypted database backup and confirm enough free
disk space. For schema changes, use forward-compatible expand/migrate/contract
releases. Roll back application images only while the deployed schema remains
compatible; otherwise deploy a forward fix. Never reverse a destructive
migration without a tested restore.

## Configuration and TLS

Production settings fail immediately when hosts, database, Redis, SMTP, signing,
or storage values are absent. `SECRET_KEY` and `JWT_SIGNING_KEY` must be long,
random, and independent. Caddy replaces forwarded scheme headers before proxying
to Django, which is the only reason `SECURE_PROXY_SSL_HEADER` is enabled.

Caddy limits request bodies to 20 MiB; image decoding applies stricter byte,
pixel, and dimension limits. HSTS is enabled for one year. Do not enable preload
until every subdomain is permanently HTTPS.

The default `NINJA_NUM_PROXIES=1` is part of this topology: Caddy is the only
proxy between a public client and Django, and Caddy replaces untrusted incoming
`X-Forwarded-*` values. If a CDN or load balancer is added in front of Caddy,
configure its address ranges as trusted proxies in Caddy and increase
`NINJA_NUM_PROXIES` to match the complete trusted chain. Never expose the web
container directly while trusting caller-supplied forwarding headers.

## Shutdown and sizing

`WEB_CONCURRENCY` defaults to two bounded Gunicorn workers rather than deriving
workers from host CPU count. Tune it from measured memory/latency under the
container's resource limits. Compose allows 45 seconds for graceful shutdown;
Celery tasks also have hard and soft time limits. Drain long export jobs before
host maintenance where possible.

See [operations.md](operations.md) for backups, monitoring, release validation,
and incident recovery.
