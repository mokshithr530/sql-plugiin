import os
import re
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from active_database import get_session_database_path, get_session_source
from config import MCP_DATABASE_PATH, QUERY_ROW_LIMIT
from database_manager import db_manager
from schema_reader import SchemaReader
from mysql_adapter import mysql_adapter
from sqlserver_adapter import sqlserver_adapter
from validator import validator
from business_catalog import business_catalog


mcp = FastMCP("SQL Assistant")
_SUPPORTED_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}
_WORDS = re.compile(r"[A-Za-z0-9]+")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PROFILE_LIMIT = 8
_SAMPLE_LIMIT = 10


def _database_path(
    database_path: str | None = None,
    session_id: str | None = None,
) -> Path:
    session_path = get_session_database_path(session_id) if session_id else None
    candidate = database_path or session_path or MCP_DATABASE_PATH
    if not candidate:
        raise ValueError(
            "No valid database selected. Pass database_path, provide a session_id "
            "with an uploaded database, or set MCP_DATABASE_PATH."
        )

    path = Path(candidate).expanduser().resolve()
    if path.suffix.lower() not in _SUPPORTED_EXTENSIONS or not path.is_file():
        raise ValueError(
            "No valid database selected. The resolved path must be an existing "
            ".db, .sqlite, or .sqlite3 file."
        )
    return path


def _source(database_path=None, session_id=None, source_type=None):
    if source_type == "sqlserver":
        return {"source_type": "sqlserver"}
    if source_type == "mysql":
        session_source = get_session_source(session_id) if session_id else None
        if session_source and session_source.get("source_type") == "mysql":
            return session_source
        raise ValueError("MySQL MCP tools require a session_id with an uploaded MySQL dump.")
    session_source = get_session_source(session_id) if session_id else None
    if session_source and session_source.get("source_type") == "sqlserver":
        return session_source
    if session_source and session_source.get("source_type") == "mysql":
        return session_source
    return {"source_type": "sqlite", "path": _database_path(database_path, session_id)}


def _connect_read_only(path: Path):
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _quote_identifier(identifier: str) -> str:
    if not _IDENTIFIER.match(identifier):
        raise ValueError(f"Invalid identifier: {identifier}")
    return f'"{identifier}"'


def _table_columns(path: Path, table_name: str) -> list[str]:
    schema = _schema(path)
    if table_name not in schema:
        raise ValueError(f"Unknown table: {table_name}")
    return [column["name"] for column in schema[table_name]["columns"]]


def _validated_columns(path: Path, table_name: str, columns: list[str] | None) -> list[str]:
    available = _table_columns(path, table_name)
    if not columns:
        return available[:_PROFILE_LIMIT]

    unknown = [column for column in columns if column not in available]
    if unknown:
        raise ValueError(f"Unknown column(s): {', '.join(unknown)}")
    return columns[:_PROFILE_LIMIT]


def _schema(path: Path) -> dict:
    with _connect_read_only(path) as connection:
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        schema = {}
        for (table,) in table_rows:
            escaped = table.replace("'", "''")
            columns = connection.execute(
                f"PRAGMA table_info('{escaped}')"
            ).fetchall()
            foreign_keys = connection.execute(
                f"PRAGMA foreign_key_list('{escaped}')"
            ).fetchall()
            schema[table] = {
                "columns": [
                    {
                        "name": row[1],
                        "type": row[2],
                        "not_null": bool(row[3]),
                        "primary_key": bool(row[5]),
                    }
                    for row in columns
                ],
                "foreign_keys": [
                    {"column": row[3], "table": row[2], "references": row[4]}
                    for row in foreign_keys
                ],
            }
        return schema


def _sqlite_row_counts(path: Path, schema: dict) -> dict:
    counts = {}
    with _connect_read_only(path) as connection:
        for table in schema:
            quoted_table = _quote_identifier(table)
            counts[table] = connection.execute(
                f"SELECT COUNT(*) FROM {quoted_table}"
            ).fetchone()[0]
    return counts


def _catalog_for_source(source):
    if source["source_type"] == "mysql":
        return mysql_adapter.business_catalog(source["database"])
    if source["source_type"] == "sqlserver":
        schema = sqlserver_adapter.inspect_schema()
        return business_catalog.build(schema, source_type="sqlserver")
    path = source["path"]
    schema = _schema(path)
    return business_catalog.build(
        schema,
        source_type="sqlite",
        row_counts=_sqlite_row_counts(path, schema),
        fingerprint=business_catalog.fingerprint(schema),
    )


def _validate(sql: str, path: Path) -> dict:
    db_manager.connect(str(path))
    try:
        result = validator.validate(sql)
    finally:
        db_manager.disconnect()

    error = result.get("error")
    warnings = []
    if result["success"] and not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        warnings.append(f"Results will be limited to {QUERY_ROW_LIMIT} rows.")
    return {
        "valid": result["success"],
        "errors": [] if result["success"] else [error or "SQL validation failed."],
        "warnings": warnings,
        "resolved_database": str(path),
    }


@mcp.tool()
def inspect_schema(
    session_id: str | None = None,
    database_path: str | None = None,
    source_type: str | None = None,
) -> dict:
    """Return real tables, columns, primary keys, and foreign keys."""
    source = _source(database_path, session_id, source_type)
    if source["source_type"] == "sqlserver":
        return {
            "database": source.get("database"),
            "source_type": "sqlserver",
            "schema": sqlserver_adapter.inspect_schema(),
        }
    if source["source_type"] == "mysql":
        return {
            "database": source.get("database"),
            "source_type": "mysql",
            "schema": mysql_adapter.inspect_schema(source["database"]),
        }
    path = source["path"]
    return {"database": str(path), "schema": _schema(path)}


@mcp.tool()
def validate_sql(
    sql: str,
    session_id: str | None = None,
    database_path: str | None = None,
    source_type: str | None = None,
) -> dict:
    """Validate one read-only SELECT/WITH query against the resolved schema."""
    source = _source(database_path, session_id, source_type)
    if source["source_type"] == "sqlserver":
        validation = sqlserver_adapter.validate_sql(sql)
        return {
            "valid": validation["valid"],
            "errors": validation["errors"],
            "warnings": [],
            "resolved_database": source.get("database"),
            "source_type": "sqlserver",
        }
    if source["source_type"] == "mysql":
        validation = mysql_adapter.validate_sql(sql, source["database"])
        return {
            "valid": validation["valid"],
            "errors": validation["errors"],
            "warnings": [],
            "resolved_database": source.get("database"),
            "source_type": "mysql",
        }
    path = source["path"]
    return _validate(sql, path)


@mcp.tool()
def dry_run_query(
    sql: str,
    session_id: str | None = None,
    database_path: str | None = None,
    source_type: str | None = None,
) -> dict:
    """Validate SQL and return SQLite EXPLAIN QUERY PLAN without running it."""
    source = _source(database_path, session_id, source_type)
    if source["source_type"] == "sqlserver":
        return {
            **sqlserver_adapter.dry_run_query(sql),
            "resolved_database": source.get("database"),
            "source_type": "sqlserver",
        }
    if source["source_type"] == "mysql":
        return {
            **mysql_adapter.dry_run_query(sql, source["database"]),
            "resolved_database": source.get("database"),
            "source_type": "mysql",
        }
    path = source["path"]
    validation = _validate(sql, path)
    if not validation["valid"]:
        return {**validation, "query_plan": []}

    with _connect_read_only(path) as connection:
        rows = connection.execute(f"EXPLAIN QUERY PLAN {sql.strip()}").fetchall()
    return {
        **validation,
        "query_plan": [
            {"id": row[0], "parent": row[1], "not_used": row[2], "detail": row[3]}
            for row in rows
        ],
    }


@mcp.tool()
def execute_read_query(
    sql: str,
    session_id: str | None = None,
    database_path: str | None = None,
    source_type: str | None = None,
) -> dict:
    """Validate and execute one bounded, read-only SQLite query."""
    source = _source(database_path, session_id, source_type)
    if source["source_type"] == "sqlserver":
        dataframe = sqlserver_adapter.execute_read_query(sql)
        return {
            "sql": sql.strip().rstrip(";"),
            "columns": list(dataframe.columns),
            "rows": dataframe.to_dict(orient="records"),
            "row_count": len(dataframe),
            "resolved_database": source.get("database"),
            "source_type": "sqlserver",
        }
    if source["source_type"] == "mysql":
        dataframe = mysql_adapter.execute_read_query(sql, source["database"])
        return {
            "sql": sql.strip().rstrip(";"),
            "columns": list(dataframe.columns),
            "rows": dataframe.to_dict(orient="records"),
            "row_count": len(dataframe),
            "resolved_database": source.get("database"),
            "source_type": "mysql",
        }
    path = source["path"]
    validation = _validate(sql, path)
    if not validation["valid"]:
        raise ValueError("; ".join(validation["errors"]))

    cleaned = sql.strip().rstrip(";")
    limited_sql = f"SELECT * FROM ({cleaned}) LIMIT {QUERY_ROW_LIMIT}"
    with _connect_read_only(path) as connection:
        cursor = connection.execute(limited_sql)
        columns = [description[0] for description in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return {
        "sql": cleaned,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "resolved_database": str(path),
    }


@mcp.tool()
def analyze_question(
    question: str,
    session_id: str | None = None,
    database_path: str | None = None,
    source_type: str | None = None,
) -> dict:
    """Match question keywords to real schema tables and columns without an LLM."""
    source = _source(database_path, session_id, source_type)
    if source["source_type"] == "mysql":
        result = mysql_adapter.analyze_question(question, source["database"])
        resolved_database = source.get("database")
    elif source["source_type"] == "sqlserver":
        schema = sqlserver_adapter.inspect_schema()
        result = business_catalog.analyze_question(question, schema, source_type="sqlserver")
        resolved_database = source.get("database")
    else:
        path = source["path"]
        schema = _schema(path)
        result = business_catalog.analyze_question(
            question,
            schema,
            source_type="sqlite",
            row_counts=_sqlite_row_counts(path, schema),
        )
        resolved_database = str(path)

    return {
        "question": question,
        "candidates": result["candidates"],
        "missing_kpis": result["missing_kpis"],
        "schema_fingerprint": result["schema_fingerprint"],
        "resolved_database": resolved_database,
        "source_type": source["source_type"],
    }


@mcp.tool()
def database_overview(
    session_id: str | None = None,
    database_path: str | None = None,
    source_type: str | None = None,
) -> dict:
    """Return compact dynamic business catalog overview without using an LLM."""
    source = _source(database_path, session_id, source_type)
    catalog = _catalog_for_source(source)
    return {
        "source_type": source["source_type"],
        "schema_fingerprint": catalog["schema_fingerprint"],
        "table_count": catalog["table_count"],
        "detected_modules": list(catalog["entities"].keys())[:12],
        "important_tables": catalog["important_tables"][:12],
        "unsupported_kpis": catalog["unsupported_kpis"],
        "summary": catalog["summary"],
    }


@mcp.tool()
def discover_business_entities(
    session_id: str | None = None,
    database_path: str | None = None,
    source_type: str | None = None,
) -> dict:
    """Return discovered business entities, aliases, and matched schema objects."""
    source = _source(database_path, session_id, source_type)
    catalog = _catalog_for_source(source)
    return {
        "source_type": source["source_type"],
        "schema_fingerprint": catalog["schema_fingerprint"],
        "entities": catalog["entities"],
        "aliases": catalog["aliases"],
        "unsupported_kpis": catalog["unsupported_kpis"],
    }


@mcp.tool()
def discover_join_paths(
    session_id: str | None = None,
    database_path: str | None = None,
    source_type: str | None = None,
) -> dict:
    """Return declared and inferred join paths with evidence/confidence."""
    source = _source(database_path, session_id, source_type)
    catalog = _catalog_for_source(source)
    return {
        "source_type": source["source_type"],
        "schema_fingerprint": catalog["schema_fingerprint"],
        "join_paths": catalog["join_paths"],
    }


@mcp.tool()
def list_tables(
    session_id: str | None = None,
    database_path: str | None = None,
) -> dict:
    """Return compact table names and row counts for the resolved database."""
    path = _database_path(database_path, session_id)
    schema = _schema(path)
    tables = []
    with _connect_read_only(path) as connection:
        for table_name in schema:
            quoted_table = _quote_identifier(table_name)
            row_count = connection.execute(
                f"SELECT COUNT(*) FROM {quoted_table}"
            ).fetchone()[0]
            tables.append({"table": table_name, "row_count": row_count})
    return {"tables": tables, "resolved_database": str(path)}


@mcp.tool()
def get_table_profile(
    table_name: str,
    columns: list[str] | None = None,
    session_id: str | None = None,
    database_path: str | None = None,
) -> dict:
    """Return safe column profile metrics for selected real columns."""
    path = _database_path(database_path, session_id)
    selected_columns = _validated_columns(path, table_name, columns)
    quoted_table = _quote_identifier(table_name)
    profile = []

    with _connect_read_only(path) as connection:
        for column in selected_columns:
            quoted_column = _quote_identifier(column)
            row = connection.execute(
                f"""
                SELECT
                    SUM(CASE WHEN {quoted_column} IS NULL THEN 1 ELSE 0 END),
                    COUNT(DISTINCT {quoted_column}),
                    MIN({quoted_column}),
                    MAX({quoted_column})
                FROM {quoted_table}
                """
            ).fetchone()
            profile.append(
                {
                    "column": column,
                    "null_count": row[0] or 0,
                    "distinct_count": row[1] or 0,
                    "min": row[2],
                    "max": row[3],
                }
            )

    return {
        "table": table_name,
        "profile": profile,
        "resolved_database": str(path),
    }


@mcp.tool()
def sample_rows(
    table_name: str,
    limit: int = 5,
    session_id: str | None = None,
    database_path: str | None = None,
) -> dict:
    """Return a small bounded sample from one real table."""
    path = _database_path(database_path, session_id)
    columns = _table_columns(path, table_name)
    bounded_limit = max(1, min(int(limit), _SAMPLE_LIMIT))
    quoted_table = _quote_identifier(table_name)

    with _connect_read_only(path) as connection:
        cursor = connection.execute(
            f"SELECT * FROM {quoted_table} LIMIT ?",
            (bounded_limit,),
        )
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return {
        "table": table_name,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "resolved_database": str(path),
    }


if __name__ == "__main__":
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))
