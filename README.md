# WizDesk - Team Task Management Platform

WizDesk is a powerful, lightweight team and task management application designed for straightforward collaboration between Team Leaders and Team Members. Featuring dynamic real-time dashboards, an automated performance analytics suite, and a streamlined subtask delegation system.

## Key Features

*   **Role-Based Dashboards**: Distinct experiences for Team Leaders (who manage the team and assign subtasks) and Team Members (who receive and report progress on subtasks).
*   **Approval Workflows**: Secure team registration where members join via a unique "Team Code" and undergo an approval pipeline by the Leader.
*   **Team Transfers**: Members can request a move to another team; the current and future Leaders must both approve the transfer before the member is moved (their assigned subtasks are automatically released).
*   **Rich Task Hierarchies**: Create high-level tasks and break them down into granular, assignable subtasks, each with its own priority and optional deadline.
*   **Task Priority**: Assign `low` / `medium` / `high` priority to tasks and subtasks; invalid values gracefully fall back to `medium`.
*   **Automatic State Sync**: Subtask status stays in sync with progress, and a task is marked `completed` automatically once all of its subtasks are completed.
*   **Performance Analytics**: Leader-only dashboard computing productivity scores, completion rates, and active workloads per member.
*   **Mock Verification Engine**: For local development, user registration seamlessly bypasses the need for an SMTP mail server using an in-browser mock JWT token system to test user verification safely.
*   **JWT Authentication**: Secure API handling using JSON Web Tokens.

---

## Tech Stack

**Frontend**
*   **HTML5 / CSS3**: Vanilla responsive design (No heavy frameworks required).
*   **Javascript (ES6+)**: Handles dynamic DOM updates, dashboard switching, and asynchronous `fetch` calls.

**Backend**
*   **Python 3.11+**: Core language.
*   **Django 5 / Django REST Framework (DRF)**: Powers the resilient backend ecosystem.
*   **Database**: SQLite by default for local development, switchable to PostgreSQL via `DATABASE_URL` (`psycopg2`).
*   **SimpleJWT**: Token generation and API permission enforcement.
*   **WhiteNoise / Gunicorn**: Static file serving and production WSGI deployment.

---

## Project Structure

```text
WIZDESK/
├── frontend/                     # Client-side UI (also served by Django)
│   ├── index.html                # Landing / Login page
│   ├── register-leader.html      # Leader registration
│   ├── member-register.html      # Member team-join
│   ├── leader-dashboard.html     # Leader command center
│   ├── member-dashboard.html     # Member task hub
│   ├── verify-email.html         # Mock email verification
│   ├── verify-member-email.html
│   ├── *.css                     # Styles
│   └── js/                       # Shared frontend helpers
│
├── wizdesk_backend/              # Django project
│   ├── manage.py                 # Management CLI (run commands from here)
│   ├── settings.py / urls.py     # Root-level re-exports (for tooling run from the repo root)
│   ├── wizdesk_backend/          # Canonical settings and routing package
│   ├── users/                    # Auth, teams, registrations & transfers
│   ├── tasks/                    # Tasks & subtasks CRUD + priority & state sync
│   ├── performance/              # Leader analytics
│   └── db.sqlite3                # Local SQLite database (created on first migrate)
│
├── requirements.txt
├── .env                          # Environment variable secrets (Not tracked)
└── build.sh                      # Render.com build commands
```

---

## Local Development Setup

To get WizDesk running on your local machine, you only need **Python 3.11+**. A database is configured automatically (SQLite) — PostgreSQL is optional.

### 1. Environment (optional)

Create a `.env` file in the root `WIZDESK` directory to override defaults. If omitted, Django uses safe local defaults (SQLite, `DEBUG=True`).

```env
DEBUG=True
SECRET_KEY=your-secret-django-key
# ALLOWED_HOSTS=localhost,127.0.0.1
# DATABASE_URL=postgres://postgres:postgres@localhost:5432/wizdesk
```

### 2. Backend Initialization

Open a terminal in the root `WIZDESK` directory and set up the Python dependencies.

```bash
# 1. Create an isolated virtual environment
python -m venv venv

# 2. Activate the environment
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Apply the database schema (migrations are committed)
cd wizdesk_backend
python manage.py migrate

# 5. Start the API Server!
python manage.py runserver
```

The server will begin listening on `http://127.0.0.1:8000/`.

### 3. Accessing the Frontend

The frontend is served directly by Django, so simply open **http://127.0.0.1:8000/** in your browser — no separate static server required. If you prefer to preview the raw HTML files, you can serve the `frontend/` folder on its own:

```bash
cd frontend
python -m http.server 3000
# then browse to http://localhost:3000
```

### 4. Optional: Seed Test Data

To quickly populate the database with sample teams, leaders, and members:

```bash
python manage.py seed_test_data
```

---

## License & Contributions

Built for team organization and speed. Contributions, tweaks, and PRs are open and welcome.
