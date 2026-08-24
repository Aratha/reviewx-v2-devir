"""SQL Server bağlantı ayarlarını okur/yazar; ODBC dizesi üretir."""

from __future__ import annotations

import os
import re
from typing import Any

import pyodbc

from config import BACKEND_ROOT, Settings

_ENV_PATH = BACKEND_ROOT / ".env"
_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")

FIELD_TO_ENV = {
    "mssql_server": "MSSQL_SERVER",
    "mssql_port": "MSSQL_PORT",
    "mssql_user": "MSSQL_USER",
    "mssql_password": "MSSQL_PASSWORD",
    "mssql_trusted_connection": "MSSQL_TRUSTED_CONNECTION",
    "mssql_encrypt": "MSSQL_ENCRYPT",
    "mssql_trust_server_certificate": "MSSQL_TRUST_SERVER_CERTIFICATE",
    "mssql_connection_string": "MSSQL_CONNECTION_STRING",
}


def _bool_env(v: bool) -> str:
    return "true" if v else "false"


def _parse_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _sanitize_env_value(v: str) -> str:
    return v.replace("\r", " ").replace("\n", " ").strip()


def _parse_connection_string(conn_str: str) -> dict[str, Any]:
    parts: dict[str, str] = {}
    for segment in conn_str.split(";"):
        segment = segment.strip()
        if not segment or "=" not in segment:
            continue
        key, _, val = segment.partition("=")
        parts[key.strip().lower()] = val.strip()

    server_raw = parts.get("server", "")
    server = server_raw
    port = 1433
    if "," in server_raw:
        host, port_raw = server_raw.rsplit(",", 1)
        server = host.strip()
        try:
            port = int(port_raw.strip())
        except ValueError:
            port = 1433

    trusted = _parse_bool(parts.get("trusted_connection"))
    return {
        "mssql_server": server,
        "mssql_port": port,
        "mssql_user": parts.get("uid", ""),
        "mssql_password": parts.get("pwd", ""),
        "mssql_trusted_connection": trusted,
        "mssql_encrypt": _parse_bool(parts.get("encrypt"), default=True),
        "mssql_trust_server_certificate": _parse_bool(
            parts.get("trustservercertificate"), default=True
        ),
    }


def _structured_from_settings(s: Settings) -> dict[str, Any]:
    server = (s.mssql_server or "").strip()
    if server:
        return {
            "mssql_server": server,
            "mssql_port": int(getattr(s, "mssql_port", 1433) or 1433),
            "mssql_user": (s.mssql_user or "").strip(),
            "mssql_password": s.mssql_password or "",
            "mssql_trusted_connection": bool(s.mssql_trusted_connection),
            "mssql_encrypt": bool(getattr(s, "mssql_encrypt", True)),
            "mssql_trust_server_certificate": bool(
                getattr(s, "mssql_trust_server_certificate", True)
            ),
        }
    legacy = (s.mssql_connection_string or "").strip()
    if legacy:
        return _parse_connection_string(legacy)
    return {
        "mssql_server": "",
        "mssql_port": 1433,
        "mssql_user": "",
        "mssql_password": "",
        "mssql_trusted_connection": False,
        "mssql_encrypt": True,
        "mssql_trust_server_certificate": True,
    }


def build_connection_string(
    *,
    server: str,
    port: int = 1433,
    user: str = "",
    password: str = "",
    trusted_connection: bool = False,
    encrypt: bool = True,
    trust_server_certificate: bool = True,
    database: str | None = None,
) -> str:
    host = server.strip()
    if not host:
        raise ValueError("SQL sunucu adı boş olamaz")
    segments = [
        "Driver={ODBC Driver 18 for SQL Server}",
        f"Server={host},{port}",
    ]
    if database and database.strip():
        db = database.strip().replace("}", "}}")
        segments.append(f"Database={{{db}}}")
    if trusted_connection:
        segments.append("Trusted_Connection=yes")
    else:
        segments.append("Trusted_Connection=no")
        if user.strip():
            segments.append(f"UID={user.strip()}")
        if password:
            segments.append(f"PWD={password}")
    segments.append(f"Encrypt={'yes' if encrypt else 'no'}")
    segments.append(
        f"TrustServerCertificate={'yes' if trust_server_certificate else 'no'}"
    )
    return ";".join(segments) + ";"


def resolve_base_connection_string() -> str:
    s = Settings()
    data = _structured_from_settings(s)
    server = (data["mssql_server"] or "").strip()
    if not server:
        raise ValueError(
            "SQL bağlantısı yapılandırılmamış. "
            "Arayüzden SQL ayarları sayfasına gidin veya backend/.env içinde "
            "MSSQL_SERVER ve kimlik bilgilerini tanımlayın."
        )
    trusted = bool(data["mssql_trusted_connection"])
    user = (data["mssql_user"] or "").strip()
    password = data["mssql_password"] or ""
    if not trusted and not user:
        raise ValueError(
            "SQL kullanıcı adı boş. Windows kimlik doğrulaması kullanmıyorsanız "
            "MSSQL_USER değerini doldurun."
        )
    return build_connection_string(
        server=server,
        port=int(data["mssql_port"] or 1433),
        user=user,
        password=password,
        trusted_connection=trusted,
        encrypt=bool(data["mssql_encrypt"]),
        trust_server_certificate=bool(data["mssql_trust_server_certificate"]),
    )


def read_sql_snapshot() -> dict[str, Any]:
    s = Settings()
    data = _structured_from_settings(s)
    server = (data["mssql_server"] or "").strip()
    password = (data["mssql_password"] or "").strip()
    trusted = bool(data["mssql_trusted_connection"])
    user = (data["mssql_user"] or "").strip()
    configured = bool(server) and (trusted or bool(user))
    return {
        "mssql_server": server,
        "mssql_port": int(data["mssql_port"] or 1433),
        "mssql_user": user,
        "mssql_trusted_connection": trusted,
        "mssql_encrypt": bool(data["mssql_encrypt"]),
        "mssql_trust_server_certificate": bool(data["mssql_trust_server_certificate"]),
        "password_set": bool(password),
        "configured": configured,
    }


def _effective_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = read_sql_snapshot()
    current = Settings()
    data = _structured_from_settings(current)
    merged = {
        "mssql_server": base["mssql_server"],
        "mssql_port": base["mssql_port"],
        "mssql_user": base["mssql_user"],
        "mssql_password": data["mssql_password"] or "",
        "mssql_trusted_connection": base["mssql_trusted_connection"],
        "mssql_encrypt": base["mssql_encrypt"],
        "mssql_trust_server_certificate": base["mssql_trust_server_certificate"],
    }
    if overrides:
        for key, val in overrides.items():
            if val is None:
                continue
            if key == "mssql_password":
                merged[key] = str(val)
            else:
                merged[key] = val
    return merged


def test_sql_connection(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _effective_config(overrides)
    server = (cfg["mssql_server"] or "").strip()
    if not server:
        return {"ok": False, "message": "Sunucu adı boş."}
    trusted = bool(cfg["mssql_trusted_connection"])
    user = (cfg["mssql_user"] or "").strip()
    password = cfg["mssql_password"] or ""
    if not trusted and not user:
        return {"ok": False, "message": "Kullanıcı adı boş."}
    if not trusted and not password and not read_sql_snapshot()["password_set"]:
        return {"ok": False, "message": "Şifre girilmedi."}
    try:
        conn_str = build_connection_string(
            server=server,
            port=int(cfg["mssql_port"] or 1433),
            user=user,
            password=password,
            trusted_connection=trusted,
            encrypt=bool(cfg["mssql_encrypt"]),
            trust_server_certificate=bool(cfg["mssql_trust_server_certificate"]),
            database="master",
        )
        with pyodbc.connect(conn_str, timeout=15) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sys.databases WHERE state = 0 ORDER BY name"
            )
            databases = [str(row[0]) for row in cur.fetchall()]
        return {
            "ok": True,
            "message": f"Bağlantı başarılı ({server}). {len(databases)} veritabanı bulundu.",
            "databases": databases,
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc).strip() or "Bağlantı başarısız."}


def merge_sql_into_dotenv(updates: dict[str, str | bool | int | None]) -> None:
    path = _ENV_PATH
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()

    env_patch: dict[str, str] = {}
    remove_password = False

    for field, env_upper in FIELD_TO_ENV.items():
        if field not in updates:
            continue
        val = updates[field]
        if val is None:
            continue
        if field == "mssql_password":
            assert isinstance(val, str)
            if not val.strip():
                remove_password = True
                continue
            env_patch[env_upper] = val
        elif field in {
            "mssql_trusted_connection",
            "mssql_encrypt",
            "mssql_trust_server_certificate",
        }:
            assert isinstance(val, bool)
            env_patch[env_upper] = _bool_env(val)
        elif field == "mssql_port":
            assert isinstance(val, int)
            env_patch[env_upper] = str(val)
        elif field == "mssql_connection_string":
            assert isinstance(val, str)
            env_patch[env_upper] = _sanitize_env_value(val)
        else:
            assert isinstance(val, str)
            env_patch[env_upper] = _sanitize_env_value(val)

    if updates:
        snapshot = read_sql_snapshot()
        current = Settings()
        data = _structured_from_settings(current)
        merged = {
            "mssql_server": snapshot["mssql_server"],
            "mssql_port": snapshot["mssql_port"],
            "mssql_user": snapshot["mssql_user"],
            "mssql_password": data["mssql_password"] or "",
            "mssql_trusted_connection": snapshot["mssql_trusted_connection"],
            "mssql_encrypt": snapshot["mssql_encrypt"],
            "mssql_trust_server_certificate": snapshot["mssql_trust_server_certificate"],
        }
        for field in (
            "mssql_server",
            "mssql_port",
            "mssql_user",
            "mssql_password",
            "mssql_trusted_connection",
            "mssql_encrypt",
            "mssql_trust_server_certificate",
        ):
            if field in updates and updates[field] is not None:
                merged[field] = updates[field]
        if remove_password:
            merged["mssql_password"] = ""
        try:
            env_patch[FIELD_TO_ENV["mssql_connection_string"]] = build_connection_string(
                server=str(merged["mssql_server"]),
                port=int(merged["mssql_port"] or 1433),
                user=str(merged["mssql_user"] or ""),
                password=str(merged["mssql_password"] or ""),
                trusted_connection=bool(merged["mssql_trusted_connection"]),
                encrypt=bool(merged["mssql_encrypt"]),
                trust_server_certificate=bool(
                    merged["mssql_trust_server_certificate"]
                ),
                database="master",
            )
        except ValueError:
            env_patch.pop(FIELD_TO_ENV["mssql_connection_string"], None)

    if not env_patch and not remove_password:
        return

    out: list[str] = []
    seen: set[str] = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out.append(line)
            continue
        m = _LINE.match(line)
        if not m:
            out.append(line)
            continue
        key = m.group(1)
        if remove_password and key == FIELD_TO_ENV["mssql_password"]:
            continue
        if key in env_patch:
            out.append(f"{key}={env_patch[key]}")
            seen.add(key)
        else:
            out.append(line)

    for key, sval in env_patch.items():
        if key in seen:
            continue
        out.append(f"{key}={sval}")

    text = "\n".join(out)
    if text and not text.endswith("\n"):
        text += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    for key, sval in env_patch.items():
        os.environ[key] = sval
    if remove_password:
        os.environ.pop(FIELD_TO_ENV["mssql_password"], None)
