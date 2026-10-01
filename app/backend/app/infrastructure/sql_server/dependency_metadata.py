"""Object metadata: dependencies and their column summaries, ported from the previous application.

``sys.dm_sql_referenced_entities`` is walked breadth first in each object's own database, at most
4 levels deep and up to 48 objects; column summaries come from ``sys.columns`` and ``sys.types``
of the database that holds the object; the text is cut at 95,000 characters. A three-part
reference is resolved only in the database it names, and only when that database is one of the
online databases the account can access, system databases excluded; a two-part name that is not
found locally is searched in at most 48 of those databases, once per name in a request
(sql-review/PRDs/002-sql-server-connection Requirement 7). This module runs in a worker thread; it
never logs SQL, names or driver messages.
"""

import logging
from collections import deque
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, closing
from typing import Any, Protocol

from app.infrastructure.sql_server.queries import (
    OBJECT_BY_ID_SQL,
    OBJECT_BY_NAME_SQL,
    REFERENCED_ENTITIES_SQL,
    SCHEMA_AND_NAME_BY_ID_SQL,
    columns_sql,
)

MAX_EXPANSION_DEPTH = 4
MAX_OBJECTS_WITH_COLUMNS = 48
MAX_OUTPUT_CHARS = 95_000
MAX_DATABASES_TO_SCAN = 48

logger = logging.getLogger("app.sql_server")

_EXPAND_TYPES = frozenset({"V", "P", "FN", "IF", "TF", "SF"})
_METADATA_TYPES = frozenset({"U", "V", "TF", "IF", "SF"})


class Cursor(Protocol):
    def execute(self, sql: str, *params: Any) -> Any: ...

    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Any]: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...

    def close(self) -> None: ...


# Opens a read-only connection to the named database; raises the driver error on failure.
Connect = Callable[[str], Connection]


def _skipped(error: BaseException) -> None:
    # Only the exception type: driver messages may carry server, object or SQL details.
    logger.debug(
        "sql_server.metadata_skipped",
        extra={
            "structured_fields": {
                "event": "sql_server.metadata_skipped",
                "error_type": type(error).__name__,
            }
        },
    )


def _type_label(type_char: str) -> str:
    return {
        "U": "TABLE",
        "V": "VIEW",
        "TF": "FUNCTION_TABLE",
        "IF": "FUNCTION_INLINE",
        "SF": "FUNCTION_SQL_INLINE",
        "P": "PROCEDURE",
        "FN": "FUNCTION_SCALAR",
    }.get(type_char.upper(), type_char)


def format_column_type(
    type_name: str,
    max_length: int | None,
    precision: int | None,
    scale: int | None,
) -> str:
    t = (type_name or "").strip().lower()
    ml = max_length if max_length is not None else 0
    if t in ("varchar", "varbinary", "char", "binary"):
        if ml < 0:
            return f"{type_name}(max)"
        return f"{type_name}({ml})"
    if t in ("nvarchar", "nchar"):
        if ml < 0:
            return f"{type_name}(max)"
        n = ml // 2 if ml > 0 else ml
        return f"{type_name}({n})"
    if t in ("decimal", "numeric"):
        return f"{type_name}({precision},{scale})"
    if t == "float":
        return f"{type_name}({precision})" if precision else type_name
    if t == "datetime2" and scale is not None and scale > 0:
        return f"{type_name}({scale})"
    return type_name


def split_sql_identifiers(text: str) -> list[str]:
    """Identifier parts separated by dots, with or without square brackets."""

    t = (text or "").strip()
    if not t:
        return []
    parts: list[str] = []
    i = 0
    n = len(t)
    while i < n:
        if t[i] in " \t\n\r":
            i += 1
            continue
        if t[i] == "[":
            j = i + 1
            while j < n and t[j] != "]":
                j += 1
            if j >= n:
                break
            parts.append(t[i + 1 : j].replace("]]", "]"))
            i = j + 1
            if i < n and t[i] == ".":
                i += 1
            continue
        j = i
        while j < n and t[j] != ".":
            j += 1
        parts.append(t[i:j].strip())
        i = j
        if i < n and t[i] == ".":
            i += 1
    return [p for p in parts if p]


def try_parse_three_part(ref_schema: str, ref_name: str) -> tuple[str, str, str] | None:
    """database.schema.object, or the last three parts of a four-part linked-server name."""

    for candidate in (
        ref_name,
        f"{ref_schema}.{ref_name}" if (ref_schema or "").strip() else ref_name,
    ):
        parts = split_sql_identifiers(candidate)
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        if len(parts) == 4:
            return parts[1], parts[2], parts[3]
        if len(parts) > 4:
            return parts[-3], parts[-2], parts[-1]
    return None


class DependencyMetadataCollector:
    """One metadata request: the root database and the databases it may scan."""

    def __init__(
        self,
        *,
        connect: Connect,
        database_names: Sequence[str],
    ) -> None:
        # The caller passes the online databases the account can access, without system databases.
        self.database_names = [name for name in database_names if name.lower() != "tempdb"]
        self._connect = connect
        # A name is searched across databases once per request, whatever number of objects use it.
        self._found_elsewhere: dict[tuple[str, str], tuple[str, int, str] | None] = {}

    def _open(self, database: str) -> AbstractContextManager[Connection]:
        return closing(self._connect(database))

    def _referenced_rows(
        self, cursor: Cursor, schema: str, name: str
    ) -> list[tuple[str, str, int | None, str | None]]:
        try:
            cursor.execute(REFERENCED_ENTITIES_SQL, f"{schema}.{name}")
        except Exception as error:  # noqa: BLE001 - the source skips unreadable objects
            _skipped(error)
            return []
        out: list[tuple[str, str, int | None, str | None]] = []
        for row in cursor.fetchall():
            rn = row[1]
            if rn is None or str(rn).strip() == "":
                continue
            rs = str(row[0] or "").strip() or "dbo"
            rid = row[2]
            rdb = str(row[3] or "").strip() or None
            out.append((rs, str(rn).strip(), int(rid) if rid is not None else None, rdb))
        return out

    @staticmethod
    def _resolve_object(cursor: Cursor, ref_schema: str, ref_name: str) -> tuple[int | None, str]:
        cursor.execute(OBJECT_BY_NAME_SQL, ref_schema, ref_name)
        row = cursor.fetchone()
        if not row:
            return None, ""
        return int(row[0]), str(row[1] or "").strip().upper()

    def _find_object_any_database(
        self, schema_name: str, object_name: str
    ) -> tuple[str, int, str] | None:
        rs = (schema_name or "").strip() or "dbo"
        rn = (object_name or "").strip()
        if not rn:
            return None
        key = (rs.lower(), rn.lower())
        if key not in self._found_elsewhere:
            self._found_elsewhere[key] = self._scan_databases(rs, rn)
        return self._found_elsewhere[key]

    def _scan_databases(self, rs: str, rn: str) -> tuple[str, int, str] | None:
        for db_name in self.database_names[:MAX_DATABASES_TO_SCAN]:
            try:
                with self._open(db_name) as connection:
                    oid, typ = self._resolve_object(connection.cursor(), rs, rn)
                    if oid is not None and typ:
                        return db_name, oid, typ
            except Exception as error:  # noqa: BLE001 - an unreadable database is skipped
                _skipped(error)
        return None

    def _resolve_in_named_database(
        self, ref_db: str, ref_schema: str, ref_name: str, ref_id: int | None
    ) -> tuple[str | None, int | None, str]:
        """A three-part reference: its id and name belong to ``ref_db``, never to the caller."""

        db_key = next((d for d in self.database_names if d.lower() == ref_db.lower()), None)
        if db_key is None:
            # Offline, not accessible or a system database: it is never opened or scanned.
            return None, None, ""
        with self._open(db_key) as connection:
            cursor = connection.cursor()
            if ref_id is not None and int(ref_id) > 0:
                cursor.execute(OBJECT_BY_ID_SQL, int(ref_id))
                row = cursor.fetchone()
                if row:
                    return db_key, int(row[0]), str(row[1] or "").strip().upper()
            oid, typ = self._resolve_object(cursor, ref_schema, ref_name)
        if oid is None:
            return None, None, ""
        return db_key, oid, typ

    def _resolve_ref_target(
        self,
        context_db: str,
        cursor: Cursor,
        ref_schema: str,
        ref_name: str,
        ref_id: int | None,
        ref_db: str | None = None,
    ) -> tuple[str | None, int | None, str]:
        rs = (ref_schema or "").strip() or "dbo"
        rn = (ref_name or "").strip()
        if not rn:
            return None, None, ""

        if ref_db and ref_db.lower() != context_db.lower():
            return self._resolve_in_named_database(ref_db, rs, rn, ref_id)

        if ref_id is not None and int(ref_id) > 0:
            cursor.execute(OBJECT_BY_ID_SQL, int(ref_id))
            row = cursor.fetchone()
            if row:
                return context_db, int(row[0]), str(row[1] or "").strip().upper()

        oid, typ = self._resolve_object(cursor, rs, rn)
        if oid is not None:
            return context_db, oid, typ

        three_part = try_parse_three_part(rs, rn)
        if three_part:
            db, sch, on = three_part
            db_key = next((d for d in self.database_names if d.lower() == db.lower()), None)
            if db_key:
                try:
                    with self._open(db_key) as connection:
                        oid2, typ2 = self._resolve_object(connection.cursor(), sch, on)
                        if oid2 is not None:
                            return db_key, oid2, typ2
                except Exception as error:  # noqa: BLE001 - skipped like in the source
                    _skipped(error)

        found = self._find_object_any_database(rs, rn)
        if found:
            return found
        return None, None, ""

    def collect_targets(
        self, database: str, root_schema: str, root_name: str
    ) -> list[tuple[str, int]]:
        """Unique (database, object_id) pairs, each in the database that holds the object.

        The root database connection must open; a failure there propagates to the caller.
        Later failures are skipped so one unreadable dependency does not hide the others.
        """

        seen_expand: set[tuple[str, str, str]] = set()
        seen_targets: set[tuple[str, int]] = set()
        ordered: list[tuple[str, int]] = []
        queue: deque[tuple[str, str, str, int]] = deque()
        queue.append((database, (root_schema or "").strip(), (root_name or "").strip(), 0))
        root = True

        while queue and len(ordered) < MAX_OBJECTS_WITH_COLUMNS:
            db, sch, nm, depth = queue.popleft()
            key = (db.lower(), sch.lower(), nm.lower())
            if key in seen_expand:
                continue
            seen_expand.add(key)
            try:
                with self._open(db) as connection:
                    cursor = connection.cursor()
                    for ref_schema, ref_name, ref_id, ref_db in self._referenced_rows(
                        cursor, sch, nm
                    ):
                        self._visit(
                            db,
                            cursor,
                            (ref_schema, ref_name, ref_id, ref_db),
                            depth,
                            queue,
                            seen_expand,
                            seen_targets,
                            ordered,
                        )
            except Exception as error:
                # Only a failure on the root database is fatal; later ones are skipped.
                if root:
                    raise
                _skipped(error)
            root = False
        return ordered

    def _visit(
        self,
        db: str,
        cursor: Cursor,
        reference: tuple[str, str, int | None, str | None],
        depth: int,
        queue: deque[tuple[str, str, str, int]],
        seen_expand: set[tuple[str, str, str]],
        seen_targets: set[tuple[str, int]],
        ordered: list[tuple[str, int]],
    ) -> None:
        try:
            target_db, oid, typ = self._resolve_ref_target(db, cursor, *reference)
        except Exception as error:  # noqa: BLE001 - skipped like in the source
            _skipped(error)
            return
        if oid is None or not typ or not target_db:
            return
        target_key = (target_db.lower(), oid)
        # The source checked the 48-object limit only between queue items; it is strict here.
        if (
            typ in _METADATA_TYPES
            and target_key not in seen_targets
            and len(ordered) < MAX_OBJECTS_WITH_COLUMNS
        ):
            seen_targets.add(target_key)
            ordered.append((target_db, oid))
        if depth < MAX_EXPANSION_DEPTH and typ in _EXPAND_TYPES:
            try:
                with self._open(target_db) as connection:
                    connection_cursor = connection.cursor()
                    connection_cursor.execute(SCHEMA_AND_NAME_BY_ID_SQL, oid)
                    row = connection_cursor.fetchone()
                if row:
                    next_schema, next_name = str(row[0] or "dbo"), str(row[1] or "")
                    next_key = (target_db.lower(), next_schema.lower(), next_name.lower())
                    if next_key not in seen_expand:
                        queue.append((target_db, next_schema, next_name, depth + 1))
            except Exception as error:  # noqa: BLE001 - skipped like in the source
                _skipped(error)

    @staticmethod
    def _columns_blob(cursor: Cursor, object_ids: list[int]) -> str:
        if not object_ids:
            return ""
        cursor.execute(columns_sql(len(object_ids)), *object_ids)
        by_obj: dict[tuple[str, str, str], list[str]] = {}
        for r in cursor.fetchall():
            key = (str(r[0] or ""), str(r[1] or ""), str(r[2] or "").strip().upper())
            line = (
                f"  - {r[3] or ''!s} {format_column_type(str(r[4] or ''), r[5], r[6], r[7])} "
                f"{'NULL' if r[8] else 'NOT NULL'}"
            )
            by_obj.setdefault(key, []).append(line)
        parts: list[str] = []
        for (sch, obj, otyp), lines in sorted(by_obj.items()):
            parts.append(f"- {sch}.{obj} ({_type_label(otyp)})")
            parts.extend(lines)
            parts.append("")
        return "\n".join(parts).strip()

    def columns(self, targets: list[tuple[str, int]]) -> str:
        by_db: dict[str, list[int]] = {}
        for db, oid in targets:
            by_db.setdefault(db, []).append(oid)
        sections: list[str] = []
        for db in sorted(by_db):
            try:
                with self._open(db) as connection:
                    blob = self._columns_blob(connection.cursor(), by_db[db])
                if blob:
                    sections.append(f"### Veritabanı: [{db}]\n{blob}")
            except Exception as error:  # noqa: BLE001 - skipped like in the source
                _skipped(error)
        return "\n\n".join(sections).strip()

    def collect(self, database: str, schema_name: str, object_name: str) -> str:
        targets = self.collect_targets(database, schema_name, object_name)
        if not targets:
            return ""
        blob = self.columns(targets)
        if not blob:
            return ""
        header = (
            f"Analiz kökü veritabanı: {database}\n"
            f"Aşağıdaki kolon listeleri her nesnenin bulunduğu veritabanından "
            f"(sys.dm_sql_referenced_entities + sys.columns) alınmıştır; "
            f"en fazla {MAX_OBJECTS_WITH_COLUMNS} nesne, derinlik ≤ {MAX_EXPANSION_DEPTH}.\n\n"
        )
        text = header + blob
        if len(text) > MAX_OUTPUT_CHARS:
            text = (
                text[: MAX_OUTPUT_CHARS - 80] + "\n\n[… metin uzunluk sınırı nedeniyle kesildi …]"
            )
        return text
