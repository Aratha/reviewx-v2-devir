import re

import pyodbc

from services.sql_env import resolve_base_connection_string


def connection_string_with_database(base: str, database: str) -> str:
    """Mevcut ODBC dizesinden Database= kısmını çıkarıp seçilen veritabanını ekler."""
    db = database.strip()
    if not db:
        raise ValueError("Veritabanı adı boş olamaz")
    escaped = db.replace("}", "}}")
    db_segment = f"Database={{{escaped}}};"
    cleaned = re.sub(r"(?i);?\s*Database\s*=\s*[^;]+", "", base)
    cleaned = cleaned.strip().rstrip(";")
    if cleaned:
        return f"{cleaned};{db_segment}"
    return db_segment


def get_connection(database: str | None = None) -> pyodbc.Connection:
    base = resolve_base_connection_string()
    conn_str = (
        connection_string_with_database(base, database)
        if database
        else base
    )
    return pyodbc.connect(conn_str, timeout=30)
