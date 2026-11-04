# WizDesk pilot deployment: Northflank, Neon, Resend

This is the release procedure for the existing single Django service. Keep credentials in Northflank secrets; do not add them to Git, command history, tickets, or test logs. Use one service replica and `WEB_CONCURRENCY=1` until throttling uses a shared cache.

## 1. Fix the candidate

Record the full Git commit SHA and a successful GitHub Actions `Verify` run for that SHA. The combined commit-status endpoint can be empty even when Actions ran, so inspect the Actions run and its backend SQLite/PostgreSQL, browser, frontend, and Docker jobs. Create a candidate tag only after the desired code is committed. Keep the preceding image/commit available for rollback.

## 2. Provision the database

Create a Neon project and production database. Copy its **pooled** connection string into the Northflank service as `DATABASE_URL`. Copy its **direct** connection string into the migration job as `MIGRATION_DATABASE_URL`. Require TLS in both connection strings. Never connect the local or CI concurrency suite to production.

Before the first release, use a disposable PostgreSQL database to run the suite with `TEST_DATABASE_URL`, then run the existing backup and restart probes against a disposable `wizdesk-pg-*` cluster. The probes are described in the README. For production, take a backup using the direct connection before every schema change, store it outside Northflank, and restore a copy into a separate database to verify both schema and representative team/task records. Record backup age and restore duration. A successful local probe does not establish Neon backup retention.

## 3. Configure the service and migration job

Build with the repository `Dockerfile`. The service uses the image's Gunicorn command on port `8000`; route HTTPS to it. Configure `/health/` for liveness and `/ready/` for readiness. Run one service replica with `WEB_CONCURRENCY=1`.

Set these service secrets and environment variables, substituting your actual hostname and private values:

```text
DEBUG=False
SECRET_KEY=<private random key of at least 50 characters>
DATABASE_URL=<Neon pooled PostgreSQL URL>
ALLOWED_HOSTS=<service hostname>
CSRF_TRUSTED_ORIGINS=https://<service hostname>
NORTHFLANK_SERVICE_URL=https://<service hostname>
FRONTEND_URL=https://<service hostname>
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=False
SECURE_HSTS_PRELOAD=False
WEB_CONCURRENCY=1
LOG_LEVEL=INFO
```

Do not enable HSTS subdomain coverage or preload on a shared Northflank domain. Enable them only after checking every subdomain of a domain you control. The live smoke test requires a positive HSTS `max-age`; it accepts this conservative policy. Django's generic deployment check may still warn about the deliberately disabled HSTS preload/subdomain flags. `check_production_config` is the release's mandatory gate for the concrete pilot settings.

Create a Northflank job using the **same image build** as the service. Override its command to `/app/release.sh`. Set `MIGRATION_DATABASE_URL` to the Neon direct URL in that job, along with the service's other production settings. The script replaces `DATABASE_URL` inside the job, validates configuration, runs Django deployment checks, then runs `migrate --noinput`. Run the job to completion before starting or updating the service. Stop if validation or migration fails. Northflank supports one-off jobs and command overrides for a built image. [Northflank jobs](https://northflank.com/docs/v1/application/run/run-an-image-once-or-on-a-schedule), [command overrides](https://northflank.com/docs/v1/application/run/override-command-entrypoint)

## 4. Configure Resend before the release job

Verify a sending domain and its DNS records in Resend, then create an API key. Set these values in **both** the service and migration job so release validation uses the same email configuration:

```text
EMAIL_VERIFICATION_REQUIRED=True
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.resend.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=resend
EMAIL_HOST_PASSWORD=<Resend API key>
DEFAULT_FROM_EMAIL=WizDesk <noreply@your-verified-domain.example>
EMAIL_TIMEOUT=10
```

Do not use the console email backend in production: verification and reset links must not be printed in logs. Registration and resend return generic responses, and an SMTP failure leaves an unverified account eligible for resend. Verify this using a real inbox before inviting pilot users.

## 5. Release and smoke test

After the migration job succeeds, start the service and run:

```text
python scripts/smoke_deployment.py --base-url https://<service hostname>
```

The smoke checks liveness, database readiness, CSS/JS delivery, an invalid login, and HSTS. Check application logs for startup errors and accidental secret disclosure without copying credentials into a report. A local Docker smoke and hosted CI cannot establish that the live service or Resend works.

## 6. Pilot acceptance

Using two real inboxes and two browser profiles on the live service:

1. Register a leader, receive and use the verification link, then create a team.
2. Register a member using the team code, receive and use the verification link, and have the leader approve membership.
3. Have the leader create a task with multiple subtasks and assign one to the member.
4. Have the member claim an available subtask, update progress, and complete it while the leader observes status and performance updates.
5. Request a password reset, use the delivered link, and verify old access and refresh tokens are rejected.
6. Rotate the join code from the leader's Members screen. Confirm the old code rejects new registration and the new code works. Existing dashboards using the old code should be refreshed.
7. Restart the service, sign in again as both users, and confirm team, task, assignment, and audit records persist.
8. Restore a production backup into a separate database and verify it before declaring recovery ready.

Record the commit SHA, image digest, migration job run, smoke result, email delivery evidence, backup age, restore result, and any failed step. Pilot acceptance requires all steps on the live Northflank service with Neon and Resend.

## Rollback

If a release fails before migration, keep the previous image running. If migration completed, review whether the schema is backward compatible before redeploying the preceding image. Restore the verified pre-migration backup into a separate database first; switching production to a restored database is a deliberate operator action after checking data loss and downtime. Never assume `migrate` automatically reverses a migration.
