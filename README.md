# WizDesk

WizDesk provides Django/DRF APIs and vanilla JavaScript dashboards for team leaders and approved members. Leaders manage tasks, assignments, membership, and transfer approvals. Members claim available subtasks and report progress.

## Local setup

Use Python 3.11+ and Node 22+ for frontend tests. A private `SECRET_KEY` is required. `.env.example` defaults to local SQLite and disabled email verification; it contains no enabled remote database connection.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Replace SECRET_KEY with a private random key before starting.
cd wizdesk_backend
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000. Register a leader, then register a member using the generated team code and approve the membership. Do not copy the example over an existing `.env`.

## Behavior and architecture

- `wizdesk_backend/wizdesk_backend/` contains canonical settings, URLs, WSGI and ASGI. Root wrappers support server startup from the repository root.
- `users/permissions.py` and `users/authentication.py` enforce active, approved, current team membership on access and refresh. When verification is enabled, email must be verified. Only the actual team leader can manage tasks and membership.
- `tasks/serializers.py` validates complete request payloads before mutation. Invalid dates, statuses, text types and assignees return 400. Unknown string priorities preserve an existing priority or use the model default `medium` for new records.
- `tasks/services.py` applies task edits atomically. The editor sends updated/new subtasks, explicit `deleted_subtask_ids`, and `expected_updated_at`. A stale revision returns 409. Omitted subtasks are preserved; omission does not mean deletion.
- Task status derives from child progress when children exist. Tasks without children retain explicit completion. Archived tasks stay archived. Direct child mutations require unarchiving first; a leader can edit an archived aggregate while preserving the archive.
- Removing or transferring a member releases unfinished work. Completed assignments retain the original user and task team for history. Removal detaches membership rather than deleting the account. Pending transfers are canceled when membership is rejected or removed.
- PostgreSQL row locks serialize membership changes, assignments, claims, completions and refresh rotations. SQLite is suitable for local development; the concurrency suite specifically requires PostgreSQL.
- List APIs use page-number pagination: `{count, next, previous, results}`. Dashboard helpers follow same-origin pages to retain their existing whole-team displays. Assigned-subtask queries select related task and user data to avoid per-row queries.
- Performance reports count current members' assignments within the current task team, across all time. Completion rate is a ratio of completed to assigned subtasks, not a measure of individual productivity. `productivityScore` remains as an API compatibility alias.
- `frontend/js/api.js` owns authentication, refresh rotation, logout, error normalization, page traversal and polling. Both tokens rotate together. Concurrent requests share refresh; supported browsers also coordinate refresh across tabs using Web Locks. Logout blacklists the submitted refresh token and clears session keys. An already-issued access token can remain valid until expiry, provided membership remains eligible.
- Dashboard scripts live in separate files. Editable user content is escaped; tasks with identical titles group by ID. Datetime inputs convert local time to explicit UTC instants. Dialogs manage focus, keyboard navigation and Escape.
- Automatic refresh runs only in visible tabs, waits for previous refresh completion, backs off on failures, and scales its interval with page/request count. Changes initiated by the user refresh the relevant display immediately.

## Email verification

Set `EMAIL_VERIFICATION_REQUIRED=True`, configure SMTP and `FRONTEND_URL`, and use the SMTP email backend. Verification links expire after 24 hours, bind the user/email/role/password, and cannot verify the other registration role. Registration pages consume the link and remove the token from the address bar. Resend is available on the registration page.

Registration acceptance and resend responses deliberately do not guarantee delivery or disclose whether an email is registered. SMTP failure leaves an unverified account available for resend. Delivery errors omit tokens and addresses. Gunicorn access logs omit query strings and referrers. Development console email delivery intentionally prints the email; never use that backend for production mail.

Verification defaults to disabled. In that mode, leaders get a team immediately and members still require leader approval. Names support Unicode letters and combining marks, spaces, apostrophes, periods and hyphens. Passwords require at least eight characters and pass Django's common, numeric and account-similarity checks; special characters are optional.

## Verification

Run backend commands from `wizdesk_backend/` so Django discovers all app tests:

```powershell
python manage.py test --settings=wizdesk_backend.test_settings --noinput
python manage.py makemigrations --settings=wizdesk_backend.test_settings --check --dry-run
```

Tests default to an isolated in-memory SQLite database, a dedicated test signing key, and local memory email/cache. To run the PostgreSQL races against a disposable test server, set `TEST_DATABASE_URL` first. Django creates and removes a test database; do not point this at a production account.

```powershell
$env:TEST_DATABASE_URL='postgresql://test_user:TEST_PASSWORD@localhost:5432/postgres'
python manage.py test --settings=wizdesk_backend.test_settings --noinput
```

From the repository root:

```powershell
npm ci
npm test
npx playwright install chromium
$env:PYTHON='venv/Scripts/python.exe'
npm run test:browser
```

Browser tests create a disposable SQLite database and serve fixtures on 127.0.0.1:8019. They do not use the application's configured database. To use an installed browser instead, set `BROWSER_EXECUTABLE` to its executable path. GitHub Actions runs SQLite, PostgreSQL races, JavaScript tests, browser workflows, migration checks and production static checks.

## Existing data and rollout

Back up the database before migration. The new migrations enforce case-insensitive email uniqueness and valid task/subtask state choices. Existing conflicting records must be resolved before these constraints can be applied.

```powershell
# Read-only audits, using the application's intended database configuration:
python manage.py audit_memberships
python manage.py repair_task_states
python manage.py migrate --plan
```

Review duplicate identities, invalid priorities/progress, obsolete transfers, leader ownership, and accounts without a team. `repair_task_states` defaults to dry run. After reviewing a backup and its output, `--apply` repairs deterministic state drift; it does not merge identities, invent completion timestamps, or infer the intended timezone of historical deadlines. Resolve ambiguous records manually, then run `migrate`. No data audit or repair is run automatically during application requests or build.

Check production environment configuration, then run `collectstatic` and `check --deploy`. Deployment needs a private secret, correct allowed hosts/origins, PostgreSQL, HTTPS/cookie settings, and SMTP only when verification is enabled. Set `CACHE_URL` to shared Redis when running multiple workers. Without shared cache, run `WEB_CONCURRENCY=1`; a deployment check flags multiple workers with per-process throttling. DRF throttles are application rate limits, not an atomic perimeter defense.

`build.sh` installs dependencies and collects static without database migration. `release.sh` runs migrations as a release operation. The existing Render free-service blueprint invokes this once at service startup before Gunicorn; do not scale startup migration commands concurrently. For multiple replicas, run migrations once through a platform release job and start Gunicorn separately. `/health/` is unthrottled liveness; `/ready/` checks the database and returns 503 when it is unavailable. WhiteNoise serves manifest-named static assets.

Docker Compose uses private passwords supplied through environment variables, a separate migration service, PostgreSQL and Redis. No source bind mounts hide the image's collected static assets. `docker compose up --build` is a local deployment option after setting `SECRET_KEY` and `POSTGRES_PASSWORD`; it changes its own container database, so inspect the configuration first.

Demo seeding is development-only, requires explicit strong credentials and an `example.com` address, and refuses to overwrite an existing account or team:

```powershell
python manage.py seed_test_data --email leader@example.com --password YOUR_STRONG_DEMO_PASSWORD --team-code DEMO01
```

## Practical limits

The dashboards still load all pages for aggregate counts and client-side filtering. Very large teams would benefit from server-filtered views and visible pagination controls. Tokens remain in browser local storage; the implemented escaping and session checks reduce exposure, while a future cookie-based session design would require a separate authentication/CSRF migration. SMTP credentials, a live deployment, external backups and existing production data must be verified in the target environment.
