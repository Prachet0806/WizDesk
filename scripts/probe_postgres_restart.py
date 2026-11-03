"""Verify crash rollback on a disposable local PostgreSQL cluster only."""

import argparse
import subprocess
import sys
from pathlib import Path

import psycopg2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--pg-ctl", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    data_dir = Path(args.data_dir).resolve()
    if not data_dir.name.startswith("wizdesk-pg-") or args.port == 5432:
        raise ValueError("Use a disposable wizdesk-pg-* cluster on a nondefault port")
    conninfo = f"host=127.0.0.1 port={args.port} user=wizdesk_ci dbname=postgres"
    connection = psycopg2.connect(conninfo)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW data_directory")
            actual = Path(cursor.fetchone()[0]).resolve()
            if actual != data_dir:
                raise ValueError("Connected server does not match the disposable data directory")
            cursor.execute("DROP TABLE IF EXISTS wizdesk_restart_probe")
            cursor.execute("CREATE TABLE wizdesk_restart_probe (id integer PRIMARY KEY, value text NOT NULL)")
            cursor.execute("INSERT INTO wizdesk_restart_probe VALUES (1, 'committed')")
    finally:
        connection.close()

    connection = psycopg2.connect(conninfo)
    with connection.cursor() as cursor:
        cursor.execute("UPDATE wizdesk_restart_probe SET value='uncommitted' WHERE id=1")
    try:
        subprocess.run(
            [args.pg_ctl, "-D", str(data_dir), "-m", "immediate", "stop"],
            check=True,
        )
        try:
            connection.commit()
        except psycopg2.Error:
            pass
        else:
            raise AssertionError("The interrupted transaction unexpectedly committed")
    finally:
        connection.close()
        subprocess.run(
            [
                args.pg_ctl,
                "-D", str(data_dir),
                "-l", str(data_dir.parent / "wizdesk-pg-restart.log"),
                "-o", f"-p {args.port} -h 127.0.0.1",
                "start",
            ],
            check=True,
        )

    connection = psycopg2.connect(conninfo)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT value FROM wizdesk_restart_probe WHERE id=1")
            value = cursor.fetchone()[0]
            cursor.execute("DROP TABLE wizdesk_restart_probe")
    finally:
        connection.close()
    if value != "committed":
        raise AssertionError(f"Crash rollback failed: {value}")
    print("PostgreSQL crash rollback passed: uncommitted update was absent after recovery")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, AssertionError, psycopg2.Error, subprocess.CalledProcessError) as error:
        print(f"PostgreSQL crash probe failed: {error}", file=sys.stderr)
        sys.exit(1)
