# Operations and recovery

## Monitoring

Collect JSON application/audit logs from stdout and proxy/container logs with
access restricted to operators. Preserve `X-Request-ID` across systems. Alert on:

- readiness failure, elevated 5xx rate, p95/p99 latency, and disk saturation;
- abnormal login failures/throttling and password-reset/email failure rates;
- Redis unavailability, Celery queue age/depth, task failures/retries, and worker
  or beat heartbeat absence;
- export/cleanup failures and private/public storage errors.

Liveness proves only that the process responds. Readiness checks database and
cache; remove an instance from service when it fails. Monitor SMTP and S3 with
synthetic delivery/upload checks outside the application.

## Backups

The target RPO is 24 hours and target RTO is four hours until a product chooses
stricter objectives. Run `deploy/backup-postgres.sh` at least daily from a host
timer. It creates an age-encrypted custom-format dump. Copy backups off-host,
retain daily copies for 14 days and monthly copies for 12 months, and alert when
the newest backup is too old. Protect the age identity separately.

Example cron entry (adjust paths and environment loading):

```cron
17 2 * * * cd /srv/myapp && /usr/bin/env sh -c '. /etc/myapp/backup.env; ./deploy/backup-postgres.sh'
```

Enable versioning on both object buckets. Apply an object lifecycle matching
the application export retention, but do not expire current private media.
Redis persistence helps restart behavior but Redis is never the system of
record; lost cache/broker messages are recovered by retrying visible workflows.

Quarterly, restore the newest backup into an isolated database with
`deploy/restore-postgres.sh`, run migrations and `manage.py check`, compare row
counts, and run tenant/media reconciliation with `manage.py audit_media` in dry
run mode. Test retrieval of versioned objects. Record duration and evidence.

## Failed work

Inspect worker logs and the persistent domain record first. Export jobs expose a
safe failure state, activity heartbeat, attempt count, and admin retry endpoint.
Beat automatically requeues pending or processing jobs after
`EXPORT_STALE_AFTER_SECONDS`; keep that value longer than the Celery hard task
limit. A PostgreSQL advisory lock prevents concurrent workers from generating
the same export, and each attempt replaces the same object key. Email tasks
retry transient exceptions three times; replay only after checking provider
status and avoiding duplicate user-facing actions. Maintenance tasks are
idempotent. Never replay a task by editing broker payloads containing user data.

Bulk image idempotency responses are retained in PostgreSQL for 24 hours and
expired daily by the maintenance queue. Redis loss does not remove them. A
rolled-back upload can still leave an unreferenced object because object storage
is not transactional; upload keys contain a logged operation UUID, and
`manage.py audit_media` finds and reconciles unreferenced objects
after the configured minimum age.

## Incident runbooks

Compromised JWT key: replace the key, increment `auth_version` and revoke active
sessions, restart web/workers, require reauthentication, inspect audit events,
and notify affected users as policy/law requires.

Leaked storage credentials: disable the credential, issue least-privilege
replacement credentials, restart services, audit object/access logs, verify
public-bucket policy, rotate any affected share links, and reconcile objects.

Accidental tenant deletion: stop writes, preserve logs and current storage
versions, restore the database into isolation, extract only the affected tenant
and related rows, reconcile object versions, validate ownership/cross-tenant
isolation, then reopen traffic. A full rollback is safer when selective recovery
cannot preserve referential integrity.

## Release exercise

Before calling a derived product production-ready, execute the final gate in the
[hardening checklist](hardening/production-readiness-checklist.md) against real
PostgreSQL, Redis, SMTP capture, and S3-compatible services. CI verifies code;
operators must still prove DNS/TLS, delivery, backups, restoration, monitoring,
and provider permissions in the target environment.
