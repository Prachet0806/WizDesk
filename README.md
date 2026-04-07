# WizDesk - Team Task Management Platform

WizDesk is a powerful, lightweight team and task management application designed for straightforward collaboration between Team Leaders and Team Members. Featuring dynamic real-time dashboards, an automated performance analytics suite, and a streamlined subtask delegation system.

## Key Features

*   **Role-Based Dashboards**: Distinct experiences for Team Leaders (who manage the team and assign subtasks) and Team Members (who receive and report progress on subtasks).
*   **Approval Workflows**: Secure team registration where members join via a unique "Team Code" and undergo an approval pipeline by the Leader.
*   **Rich Task Hierarchies**: Create high-level tasks and break them down into granular, assignable subtasks.
*   **Performance Analytics**: Automatic calculation of productivity scores, completion rates, and active workloads.
*   **Mock Verification Engine**: For local development, user registration seamlessly bypasses the need for an SMTP mail server using an in-browser mock JWT token system to test user verification safely.
*   **JWT Authentication**: Secure API handling using JSON Web Tokens.

---

## Tech Stack

**Frontend**
*   **HTML5 / CSS3**: Vanilla responsive design (No heavy frameworks required).
*   **Javascript (ES6+)**: Handles dynamic DOM updates, dashboard switching, and asynchronous `fetch` calls.

**Backend**
*   **Python 3.1x**: Core language
*   **Django 5 / Django REST Framework (DRF)**: Powers the resilient backend ecosystem.
*   **PostgreSQL**: Relational database utilized for data integrity over tasks, teams, and users (connected via `psycopg2`).
*   **SimpleJWT**: Token generation and API permission enforcement.

---

## Project Structure

```text
WIZDESK/
├── frontend/                 # Client-side UI
│   ├── index.html            # Landing / Login page
│   ├── register-leader.html  # Leader setup
│   ├── member-register.html  # Member team-join
│   ├── leader-dashboard.html # Operations command center
│   ├── member-dashboard.html # Member task hub
│   └── css & js files...     
│
├── wizdesk_backend/          # Django API Server
│   ├── manage.py             
│   ├── wizdesk_backend/      # Core settings and routing
│   ├── users/                # Authentication, teams & registration APIs
│   ├── tasks/                # Tasks & Subtasks CRUD APIs
│   └── performance/          # Analytics & Leaderboard endpoint APIs
│
├── .env                      # Environment variable secrets (Not tracked)
└── build.sh                  # Render.com build commands
```

---

## Local Development Setup

To get WizDesk running on your local machine, you will need **Python** and **PostgreSQL** installed.

### 1. Database Setup
Ensure PostgreSQL is running on port `5433` (or adjust your `.env`). Create a new database named `wizdesk` or update the environment variables to match your configuration. 

Create a `.env` file in the root directory:
```env
DEBUG=True
SECRET_KEY=your-secret-django-key
DATABASE_URL=postgres://postgres:postgres@localhost:5433/wizdesk
```

### 2. Backend Initialization
Open a terminal in the root `WIZDESK` directory and setup the Python dependencies.

```bash
# 1. Create a isolated virtual environment
python -m venv venv

# 2. Activate the environment
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Migrate the database schema
cd wizdesk_backend
python manage.py makemigrations
python manage.py migrate

# 5. Start the API Server!
python manage.py runserver
```

The server will begin listening on `http://127.0.0.1:8000/`.

### 3. Running the Frontend
Because the frontend uses vanilla HTML/JS, you can serve it via any basic static server. Optionally, you can use Python's built-in `http.server` extension:

Open a *second terminal* inside the `WIZDESK/frontend` folder:
```bash
python -m http.server 3000
```
Then simply open your browser and navigate to `http://localhost:3000` to interact with WizDesk!

---

## License & Contributions
Built for team organization and speed. Contributions, tweaks, and PRs are open and welcome.
