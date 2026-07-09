import sqlite3

import pytest

import active_database
import mcp_server


def _database(path, rows=3):
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT, salary INTEGER)"
        )
        connection.executemany(
            "INSERT INTO people (name, salary) VALUES (?, ?)",
            [(f"Person {index}", index * 100) for index in range(1, rows + 1)],
        )


def test_mcp_resolution_order(monkeypatch, tmp_path):
    explicit = tmp_path / "explicit.db"
    session = tmp_path / "session.sqlite"
    fallback = tmp_path / "fallback.sqlite3"
    for database in (explicit, session, fallback):
        database.touch()
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(mcp_server, "MCP_DATABASE_PATH", str(fallback))
    active_database.save_session_database_path("one", str(session))

    assert mcp_server._database_path(str(explicit), "one") == explicit.resolve()
    assert mcp_server._database_path(None, "one") == session.resolve()
    assert mcp_server._database_path() == fallback.resolve()


def test_missing_or_invalid_database_has_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(mcp_server, "MCP_DATABASE_PATH", "")

    with pytest.raises(ValueError, match="No valid database selected"):
        mcp_server._database_path(None, "missing")
    with pytest.raises(ValueError, match="existing"):
        mcp_server._database_path(str(tmp_path / "missing.db"))


def test_validate_sql_accepts_reads_and_rejects_unsafe_sql(tmp_path):
    database = tmp_path / "sample.db"
    _database(database)

    select_result = mcp_server.validate_sql(
        "SELECT name FROM people",
        database_path=str(database),
    )
    with_result = mcp_server.validate_sql(
        "WITH paid AS (SELECT name FROM people) SELECT * FROM paid",
        database_path=str(database),
    )
    unsafe_result = mcp_server.validate_sql(
        "DELETE FROM people",
        database_path=str(database),
    )

    assert select_result["valid"] is True
    assert with_result["valid"] is True
    assert unsafe_result["valid"] is False


def test_dry_run_returns_explain_query_plan(tmp_path):
    database = tmp_path / "sample.sqlite"
    _database(database)

    result = mcp_server.dry_run_query(
        "SELECT name FROM people WHERE salary > 100",
        database_path=str(database),
    )

    assert result["valid"] is True
    assert result["query_plan"]
    assert "detail" in result["query_plan"][0]


def test_execute_validates_and_enforces_limit(monkeypatch, tmp_path):
    database = tmp_path / "sample.sqlite"
    _database(database, rows=5)
    monkeypatch.setattr(mcp_server, "QUERY_ROW_LIMIT", 2)

    result = mcp_server.execute_read_query(
        "SELECT name FROM people ORDER BY id",
        database_path=str(database),
    )

    assert result["row_count"] == 2
    assert result["resolved_database"] == str(database.resolve())
    with pytest.raises(ValueError, match="Blocked SQL keyword"):
        mcp_server.execute_read_query(
            "DROP TABLE people",
            database_path=str(database),
        )


def test_analyze_question_returns_only_real_schema_objects(tmp_path):
    database = tmp_path / "sample.sqlite3"
    _database(database)

    result = mcp_server.analyze_question(
        "Which people have the highest salary?",
        database_path=str(database),
    )

    assert result["candidates"] == [
        {"table": "people", "columns": ["salary"]}
    ]
    schema = mcp_server.inspect_schema(database_path=str(database))
    assert "people" in schema["schema"]
