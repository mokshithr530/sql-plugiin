import os
import re
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from active_database import get_session_database_path
from config import MCP_DATABASE_PATH, QUERY_ROW_LIMIT
from database_manager import db_manager
from schema_reader import SchemaReader
from validator import validator


mcp = FastMCP("SQL Assistant")
_SUPPORTED_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}
_WORDS = re.compile(r"[A-Za-z0-9]+")


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


def _connect_read_only(path: Path):
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


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
) -> dict:
    """Return real tables, columns, primary keys, and foreign keys."""
    path = _database_path(database_path, session_id)
    return {"database": str(path), "schema": _schema(path)}


@mcp.tool()
def validate_sql(
    sql: str,
    session_id: str | None = None,
    database_path: str | None = None,
) -> dict:
    """Validate one read-only SELECT/WITH query against the resolved schema."""
    path = _database_path(database_path, session_id)
    return _validate(sql, path)


@mcp.tool()
def dry_run_query(
    sql: str,
    session_id: str | None = None,
    database_path: str | None = None,
) -> dict:
    """Validate SQL and return SQLite EXPLAIN QUERY PLAN without running it."""
    path = _database_path(database_path, session_id)
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
) -> dict:
    """Validate and execute one bounded, read-only SQLite query."""
    path = _database_path(database_path, session_id)
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
) -> dict:
    """Match question keywords to real schema tables and columns without an LLM."""
    path = _database_path(database_path, session_id)
    schema = _schema(path)
    question_words = {word.lower() for word in _WORDS.findall(question)}
    candidates = []

    for table, info in schema.items():
        table_words = {word.lower() for word in _WORDS.findall(table)}
        matched_columns = []
        for column in info["columns"]:
            column_words = {
                word.lower() for word in _WORDS.findall(column["name"])
            }
            if question_words & column_words:
                matched_columns.append(column["name"])
        if question_words & table_words or matched_columns:
            candidates.append(
                {"table": table, "columns": matched_columns}
            )

    return {
        "question": question,
        "candidates": candidates,
        "resolved_database": str(path),
    }


if __name__ == "__main__":
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))
