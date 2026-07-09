import sqlite3

from fastapi.testclient import TestClient

import active_database
import chat_pipeline as chat_pipeline_module
import main as main_module
import sql_importer


client = TestClient(main_module.app)


class DummyLLM:
    def generate_sql(self, question, schema_prompt):
        return "SELECT name, salary FROM people ORDER BY salary DESC LIMIT 1"

    def generate_answer(self, question, dataframe):
        row = dataframe.iloc[0]
        return f"{row['name']} earns {row['salary']}."

    def rewrite_failed_sql(self, question, schema_prompt, failed_sql, error_message):
        return self.generate_sql(question, schema_prompt)


def _create_people_database(path, name, salary):
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT, salary INTEGER)"
        )
        connection.execute(
            "INSERT INTO people (name, salary) VALUES (?, ?)",
            (name, salary),
        )


def _upload(database, session_id):
    with database.open("rb") as db_file:
        return client.post(
            "/upload",
            data={"session_id": session_id},
            files={
                "file": (
                    database.name,
                    db_file,
                    "application/octet-stream",
                )
            },
        )


def test_two_sessions_upload_and_chat_are_isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(chat_pipeline_module, "llm", DummyLLM())
    database_a = tmp_path / "a.db"
    database_b = tmp_path / "b.db"
    _create_people_database(database_a, "Alice", 100)
    _create_people_database(database_b, "Bob", 200)

    assert _upload(database_a, "session-a").status_code == 200
    assert _upload(database_b, "session-b").status_code == 200

    response_a = client.post(
        "/chat",
        json={"question": "Who is highest paid?", "session_id": "session-a"},
    )
    response_b = client.post(
        "/chat",
        json={"question": "Who is highest paid?", "session_id": "session-b"},
    )

    assert response_a.json()["answer"] == "Alice earns 100."
    assert response_b.json()["answer"] == "Bob earns 200."


def test_clear_removes_only_requested_session(monkeypatch, tmp_path):
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")
    database_a = tmp_path / "a.db"
    database_b = tmp_path / "b.db"
    database_a.touch()
    database_b.touch()
    active_database.save_session_database_path("session-a", str(database_a))
    active_database.save_session_database_path("session-b", str(database_b))

    response = client.post("/clear", json={"session_id": "session-a"})

    assert response.status_code == 200
    assert active_database.get_session_database_path("session-a") is None
    assert active_database.get_session_database_path("session-b") == str(
        database_b.resolve()
    )


def test_chat_requires_database_for_same_session(monkeypatch, tmp_path):
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")

    response = client.post(
        "/chat",
        json={"question": "List people", "session_id": "missing-session"},
    )

    assert response.status_code == 400
    assert "this session" in response.json()["detail"]


def test_sql_upload_stores_converted_sqlite_path(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(
        sql_importer,
        "TEMP_DATABASE_FOLDER",
        str(tmp_path / "converted"),
    )
    sql_file = tmp_path / "sample.sql"
    sql_file.write_text(
        "CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT);",
        encoding="utf-8",
    )

    response = _upload(sql_file, "sql-session")
    stored_path = active_database.get_session_database_path("sql-session")

    assert response.status_code == 200
    assert stored_path is not None
    assert stored_path.endswith("_temp.sqlite")
    assert stored_path != str(sql_file.resolve())
