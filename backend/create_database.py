"""
create_database.py
-------------------
One-time step: creates the erp_masterdata_prep database if it doesn't exist yet.
Run this BEFORE setup_db.py.

Usage:
  python create_database.py
"""
from app.config import DB_CONFIG, get_admin_connection


def create():
    db_name = DB_CONFIG["database"]
    conn = get_admin_connection()
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    if cur.fetchone():
        print(f"  Database '{db_name}' already exists.")
    else:
        cur.execute(f'CREATE DATABASE "{db_name}"')
        print(f"  Database '{db_name}' created.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    create()
