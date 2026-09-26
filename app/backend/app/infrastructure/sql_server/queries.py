"""Read-only catalog and definition queries, ported from the previous application.

Every value travels as a ``?`` parameter; no statement is assembled from user text.
"""

LIST_DATABASES_SQL = """
SELECT name
FROM sys.databases
WHERE state = 0
ORDER BY name;
"""

# User procedures, views and T-SQL functions (scalar, inline, multi-statement table-valued).
LIST_OBJECTS_SQL = """
SELECT
    s.name AS schema_name,
    o.name AS object_name,
    o.type AS type_code,
    CASE o.type
        WHEN 'P' THEN 'PROCEDURE'
        WHEN 'V' THEN 'VIEW'
        WHEN 'FN' THEN 'FUNCTION_SCALAR'
        WHEN 'IF' THEN 'FUNCTION_INLINE'
        WHEN 'TF' THEN 'FUNCTION_TABLE'
        WHEN 'SF' THEN 'FUNCTION_SQL_INLINE'
        ELSE o.type
    END AS object_type,
    o.create_date AS create_date,
    o.modify_date AS last_modified
FROM sys.objects o
INNER JOIN sys.schemas s ON o.schema_id = s.schema_id
WHERE o.type IN ('P', 'V', 'FN', 'IF', 'TF', 'SF')
  AND o.is_ms_shipped = 0
ORDER BY s.name, o.name;
"""

GET_DEFINITION_SQL = """
SELECT OBJECT_DEFINITION(o.object_id) AS definition
FROM sys.objects o
INNER JOIN sys.schemas s ON o.schema_id = s.schema_id
WHERE s.name = ? AND o.name = ? AND RTRIM(o.type) = ?;
"""

REFERENCED_ENTITIES_SQL = """
SELECT referenced_schema_name, referenced_entity_name, referenced_id
FROM sys.dm_sql_referenced_entities (?, 'OBJECT')
"""

OBJECT_BY_ID_SQL = "SELECT object_id, RTRIM(type) FROM sys.objects WHERE object_id = ?"

OBJECT_BY_NAME_SQL = """
SELECT o.object_id, RTRIM(o.type)
FROM sys.objects o
INNER JOIN sys.schemas s ON o.schema_id = s.schema_id
WHERE s.name = ? AND o.name = ?
"""

SCHEMA_AND_NAME_BY_ID_SQL = """
SELECT SCHEMA_NAME(o.schema_id), o.name
FROM sys.objects o
WHERE o.object_id = ?
"""

# The IN list holds only "?" placeholders, one per object id (at most 48 per database).
COLUMNS_SQL_TEMPLATE = """
SELECT
    OBJECT_SCHEMA_NAME(c.object_id) AS sch,
    OBJECT_NAME(c.object_id) AS obj,
    RTRIM(o.type) AS obj_type,
    c.name AS col_name,
    t.name AS type_name,
    c.max_length,
    c.precision,
    c.scale,
    c.is_nullable,
    c.column_id
FROM sys.columns c
INNER JOIN sys.objects o ON o.object_id = c.object_id
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
WHERE c.object_id IN ({placeholders})
ORDER BY sch, obj, c.column_id
"""


def columns_sql(count: int) -> str:
    if count < 1:
        raise ValueError("at least one object id is required")
    return COLUMNS_SQL_TEMPLATE.format(placeholders=",".join("?" * count))
