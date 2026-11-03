"""Exercise pg_dump and pg_restore against a disposable local WizDesk schema."""

import argparse
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import psycopg2


SOURCE = "wizdesk_backup_probe_source"
RESTORED = "wizdesk_backup_probe_restored"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--pg-bin", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    data_dir = Path(args.data_dir).resolve()
    if not data_dir.name.startswith("wizdesk-pg-") or args.port == 5432:
        raise ValueError("Use a disposable wizdesk-pg-* cluster on a nondefault port")
    admin = psycopg2.connect(
        f"host=127.0.0.1 port={args.port} user=wizdesk_ci dbname=postgres"
    )
    admin.autocommit = True
    created = []
    backup = Path(tempfile.gettempdir()) / f"wizdesk-backup-{uuid.uuid4().hex}.dump"
    try:
        with admin.cursor() as cursor:
            cursor.execute("SHOW data_directory")
            if Path(cursor.fetchone()[0]).resolve() != data_dir:
                raise ValueError("Connected server does not match the disposable data directory")
            cursor.execute(
                "SELECT datname FROM pg_database WHERE datname IN (%s, %s)",
                (SOURCE, RESTORED),
            )
            if cursor.fetchone():
                raise ValueError("Probe databases already exist; refusing to overwrite them")
            cursor.execute(f"CREATE DATABASE {SOURCE}")
            created.append(SOURCE)

        backend = Path(__file__).resolve().parents[1] / "wizdesk_backend"
        env = os.environ.copy()
        env.update(
            SECRET_KEY="disposable-backup-probe-only-key-0123456789",
            DATABASE_URL=f"postgresql://wizdesk_ci@127.0.0.1:{args.port}/{SOURCE}",
            DEBUG="False",
        )
        subprocess.run(
            [sys.executable, "manage.py", "migrate", "--noinput"],
            cwd=backend,
            env=env,
            check=True,
            capture_output=True,
        )
        source = psycopg2.connect(env["DATABASE_URL"])
        try:
            with source.cursor() as cursor:
                team_id = str(uuid.uuid4())
                cursor.execute(
                    "INSERT INTO users_team (id, code, name, created_at) "
                    "VALUES (%s, 'BACKUP', 'Backup probe', CURRENT_TIMESTAMP)",
                    (team_id,),
                )
                cursor.execute(
                    "INSERT INTO tasks_task "
                    "(id, title, status, priority, team_id, created_at, updated_at) "
                    "VALUES (%s, 'Restored task', 'active', 'medium', %s, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    (str(uuid.uuid4()), team_id),
                )
            source.commit()
        finally:
            source.close()

        pg_bin = Path(args.pg_bin)
        common = ["-h", "127.0.0.1", "-p", str(args.port), "-U", "wizdesk_ci"]
        subprocess.run(
            [str(pg_bin / "pg_dump.exe"), *common, "-Fc", "-f", str(backup), SOURCE],
            check=True,
        )
        with admin.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE {RESTORED}")
            created.append(RESTORED)
        subprocess.run(
            [
                str(pg_bin / "pg_restore.exe"), *common,
                "--no-owner", "-d", RESTORED, str(backup),
            ],
            check=True,
        )
        restored = psycopg2.connect(
            f"host=127.0.0.1 port={args.port} user=wizdesk_ci dbname={RESTORED}"
        )
        try:
            with restored.cursor() as cursor:
                cursor.execute(
                    "SELECT t.title, team.code FROM tasks_task t "
                    "JOIN users_team team ON team.id=t.team_id"
                )
                if cursor.fetchall() != [("Restored task", "BACKUP")]:
                    raise AssertionError("Restored task and team do not match")
                cursor.execute("SELECT COUNT(*) FROM django_migrations")
                if cursor.fetchone()[0] == 0:
                    raise AssertionError("Restored schema has no migration history")
        finally:
            restored.close()
        print("PostgreSQL backup restore passed: schema, migrations, team and task recovered")
    finally:
        with admin.cursor() as cursor:
            for database in reversed(created):
                cursor.execute(f"DROP DATABASE {database} WITH (FORCE)")
        admin.close()
        backup.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, AssertionError, psycopg2.Error, subprocess.CalledProcessError) as error:
        print(f"PostgreSQL backup probe failed: {error}", file=sys.stderr)
        sys.exit(1)
