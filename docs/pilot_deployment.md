# WizDesk portfolio demo: Render, Neon, and Resend

This runbook deploys the existing single Django service on Render Free, with Neon Postgres and Resend transactional email. Treat this as a portfolio/demo environment, not a production service: Render sleeps after 15 idle minutes, the filesystem is ephemeral, and the free plan can restart services.

## Before provisioning

Choose the Git commit for the demo and ensure all intended UI files are committed. Review GitHub Actions `Verify` for that commit. In particular, commit any untracked frontend assets referenced by HTML; Render builds from Git and will not include local-only files. Keep credentials in Render environment variables and never commit them.

## Neon

Create a Neon project and require TLS. Set the **pooled** connection URL as Render's `DATABASE_URL` for web requests. Set the **direct** URL as `MIGRATION_DATABASE_URL`; startup migration uses this connection. Keep the database and Render service in nearby regions when possible. Neon Free currently includes 1 GB per project and 100 CU-hours monthly. Review current limits before launch.

## Resend

Verify a sending domain you control in Resend, add its DNS records, and create an API key. Use these Render variables:

```text
EMAIL_VERIFICATION_REQUIRED=True
EMAIL_BACKEND=anymail.backends.resend.EmailBackend
RESEND_API_KEY=<private API key>
DEFAULT_FROM_EMAIL=WizDesk <noreply@your-verified-domain.example>
```

The API key must remain secret. Render Free blocks common SMTP ports, so email uses Resend's HTTPS API. Test verification and password-reset delivery with real inboxes before inviting demo users.

## Render web service

Create one Docker web service from the repository, using the root `Dockerfile` and the Free plan. Set these environment variables, substituting the actual Render hostname:

```text
DEBUG=False
SECRET_KEY=<private random key, at least 50 characters>
DATABASE_URL=<Neon pooled URL with TLS>
MIGRATION_DATABASE_URL=<Neon direct URL with TLS>
ALLOWED_HOSTS=<service>.onrender.com
CSRF_TRUSTED_ORIGINS=https://<service>.onrender.com
FRONTEND_URL=https://<service>.onrender.com
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=False
SECURE_HSTS_PRELOAD=False
WEB_CONCURRENCY=1
LOG_LEVEL=INFO
```

Set `/ready/` as the health check path. `render-start.sh` runs `release.sh`, which validates configuration against the direct database URL and applies migrations, then starts Gunicorn. Render Free does not provide a pre-deploy command or free one-off job. Startup migrations therefore run again after restarts and cold starts; Django migrations must remain repeatable. Schema changes still require review and a backup first. Use one worker because this configuration has no shared Redis cache.

The web service has an ephemeral filesystem. Do not store user uploads or SQLite data there. Neon stores relational data. `/health/` checks process liveness; `/ready/` checks database readiness.

## Pre-demo checks

1. Confirm the intended frontend changes and `frontend/css/redesign.css` are committed.
2. Review successful CI checks for the selected commit, including backend SQLite/Postgres, browser, frontend, and Docker jobs.
3. Configure the Render and Neon variables above and wait for the first deploy and startup migration to finish.
4. Run `python scripts/smoke_deployment.py --base-url https://<service>.onrender.com`.
5. Use two real inboxes and separate browser profiles to register a leader and member, verify both emails, approve membership, create and complete a task, and exercise password reset.
6. Restart the Render service and confirm both accounts and task records remain available.

For a demo, create accounts through the normal registration flow. The `seed_test_data` command intentionally refuses to run with `DEBUG=False`.

## Backups and rollback

Before changing schema on a database containing demo data, take an encrypted PostgreSQL backup through Neon's direct connection and keep it outside Render. Restore a copy into a separate database and verify representative records. Render Free does not provide a persistent disk or a managed backup for this setup.

If a deploy fails before migrations, redeploy the last working commit. If migrations completed, check backward compatibility before rolling code back. Restore a backup to a separate database first; changing the live database is an explicit operator decision. Local Docker and CI checks do not prove the hosted app, Neon connectivity, or Resend delivery work.
