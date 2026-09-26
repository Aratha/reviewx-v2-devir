"""The single ODBC connection-string builder (sql-review/PRDs/002-sql-server-connection Req. 2).

Values are never concatenated raw: user, password and database are wrapped in braces with every
closing brace doubled, so ``;``, ``=``, ``{`` or ``}`` cannot add a driver keyword. The server
must be a plain host name or address (optionally with an instance name), and control characters
in the server or user name are rejected before a string is built.
"""

import re

from app.domain.sql_server import SqlServerConnectionConfig

DRIVER = "ODBC Driver 18 for SQL Server"
_SERVER = re.compile(r"^[A-Za-z0-9._\-]+(\\[A-Za-z0-9_$]+)?$|^\[[0-9A-Fa-f:.]+\]$")


class InvalidConnectionValue(ValueError):
    """A server or user value that cannot be placed in a connection string."""


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def validate_server(server: str) -> str:
    value = server.strip()
    if _has_control_character(server) or (value and _SERVER.fullmatch(value) is None):
        raise InvalidConnectionValue("server")
    return value


def validate_user(user: str) -> str:
    if _has_control_character(user):
        raise InvalidConnectionValue("user")
    return user.strip()


def _braced(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def build_connection_string(config: SqlServerConnectionConfig, database: str) -> str:
    """ODBC Driver 18 string for one database; the result carries the password, never log it."""

    server = validate_server(config.server)
    user = validate_user(config.user)
    if not server or not user or not config.password or not database:
        raise InvalidConnectionValue("incomplete")
    if _has_control_character(database):
        raise InvalidConnectionValue("control-character")
    return (
        ";".join(
            (
                f"Driver={{{DRIVER}}}",
                f"Server={server},{config.port}",
                f"Database={_braced(database)}",
                f"UID={_braced(user)}",
                f"PWD={_braced(config.password)}",
                f"Encrypt={'yes' if config.encrypt else 'no'}",
                f"TrustServerCertificate={'yes' if config.trust_server_certificate else 'no'}",
            )
        )
        + ";"
    )
