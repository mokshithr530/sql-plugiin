import sqlite3

from fastapi.testclient import TestClient

import active_database
import chat_pipeline as chat_pipeline_module
import main as main_module
import response_cache as response_cache_module
import sql_importer


client = TestClient(main_module.app)


class DummyLLM:
    def __init__(self):
        self.provider = type(
            "Provider",
            (),
            {
                "provider_name": "test-provider",
                "model_name": "test-model",
            },
        )()

    def generate_sql(self, question, schema_prompt):
        return "SELECT name, salary FROM people ORDER BY salary DESC LIMIT 1"

    def generate_mysql_sql(self, question, schema_prompt):
        return "SELECT name, salary FROM people ORDER BY salary DESC LIMIT 1"

    def generate_answer(self, question, dataframe):
        row = dataframe.iloc[0]
        return f"{row['name']} earns {row['salary']}."

    def rewrite_failed_sql(self, question, schema_prompt, failed_sql, error_message):
        return self.generate_sql(question, schema_prompt)


class CountingLLM(DummyLLM):
    def __init__(self):
        super().__init__()
        self.answer_calls = 0

    def generate_answer(self, question, dataframe):
        self.answer_calls += 1
        return super().generate_answer(question, dataframe)


class InMemoryRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value


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


def test_casual_greeting_before_upload_prompts_for_database(monkeypatch, tmp_path):
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")

    response = client.post(
        "/chat",
        json={"question": "hello", "session_id": "new-session"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "Upload a database" in response.json()["answer"]
    assert response.json()["sql"] is None


def test_casual_greeting_after_upload_does_not_call_llm(monkeypatch, tmp_path):
    class FailingLLM(DummyLLM):
        def generate_sql(self, question, schema_prompt):
            raise AssertionError("LLM should not be called for greetings")

        def generate_answer(self, question, dataframe):
            raise AssertionError("LLM should not be called for greetings")

    monkeypatch.setattr(main_module, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(chat_pipeline_module, "llm", FailingLLM())
    database = tmp_path / "people.db"
    _create_people_database(database, "Alice", 100)
    assert _upload(database, "greeting-session").status_code == 200

    response = client.post(
        "/chat",
        json={"question": "hey!", "session_id": "greeting-session"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "Ask me something" in response.json()["answer"]
    assert response.json()["sql"] is None


def test_sql_upload_stores_converted_sqlite_path(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(main_module, "SQLSERVER_IMPORT_SQL", False)
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


def test_mysql_sql_upload_stores_mysql_session_source(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")
    sql_file = tmp_path / "mysql.sql"
    sql_file.write_text(
        "CREATE TABLE `people` (`id` int AUTO_INCREMENT) ENGINE=InnoDB;",
        encoding="utf-8",
    )

    monkeypatch.setattr(main_module.mysql_adapter, "is_mysql_dump", lambda path: True)
    monkeypatch.setattr(
        main_module.mysql_adapter,
        "import_sql_file",
        lambda path, source_name, session_id: {
            "connection_id": "mysql:sql_assistant_session:abc",
            "database": "sql_assistant_session",
            "schema_fingerprint": "schema123",
            "already_imported": False,
        },
    )
    monkeypatch.setattr(
        main_module.mysql_adapter,
        "inspect_schema",
        lambda database: {
            "people": {
                "columns": [{"column_name": "id", "name": "id", "data_type": "int"}],
                "foreign_keys": [],
            }
        },
    )

    response = _upload(sql_file, "mysql-session")
    source = active_database.get_session_source("mysql-session")

    assert response.status_code == 200
    assert response.json()["database"]["type"] == "MYSQL"
    assert source["source_type"] == "mysql"
    assert source["database"] == "sql_assistant_session"


def test_mysql_list_and_attach_existing_database(monkeypatch, tmp_path):
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(
        main_module.mysql_adapter,
        "list_allowed_databases",
        lambda: ["sql_assistant_existing"],
    )
    monkeypatch.setattr(
        main_module.mysql_adapter,
        "attach_database",
        lambda database: {
            "connection_id": f"mysql:{database}:schema123",
            "database": database,
            "name": database,
            "schema_fingerprint": "schema123",
            "progress": ["Preparing database", "Completed"],
        },
    )
    monkeypatch.setattr(
        main_module.mysql_adapter,
        "inspect_schema",
        lambda database: {
            "sales": {
                "columns": [{"column_name": "id", "name": "id", "data_type": "int"}],
                "foreign_keys": [],
            }
        },
    )

    list_response = client.get("/mysql/databases")
    attach_response = client.post(
        "/mysql/attach",
        json={"session_id": "connect-session", "database": "sql_assistant_existing"},
    )
    source = active_database.get_session_source("connect-session")

    assert list_response.status_code == 200
    assert list_response.json()["databases"] == ["sql_assistant_existing"]
    assert attach_response.status_code == 200
    assert attach_response.json()["database"]["type"] == "MYSQL"
    assert source["source_type"] == "mysql"
    assert source["database"] == "sql_assistant_existing"


def test_supported_sqlite_extensions_upload(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")

    for extension in [".db", ".sqlite", ".sqlite3"]:
        database = tmp_path / f"people{extension}"
        _create_people_database(database, f"Name {extension}", 100)

        response = _upload(database, f"session-{extension.strip('.')}")

        assert response.status_code == 200
        assert response.json()["database"]["tables"] == 1


def test_duplicate_uploads_use_unique_saved_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")
    database = tmp_path / "people.db"
    _create_people_database(database, "Alice", 100)

    assert _upload(database, "dup-session").status_code == 200
    first_path = active_database.get_session_database_path("dup-session")
    assert _upload(database, "dup-session").status_code == 200
    second_path = active_database.get_session_database_path("dup-session")

    assert first_path != second_path
    assert first_path is not None
    assert second_path is not None
    with sqlite3.connect(first_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 1
    with sqlite3.connect(second_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 1


def test_upload_rejects_unsupported_empty_corrupt_no_tables_and_oversized(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(main_module, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")

    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("not a database", encoding="utf-8")
    empty = tmp_path / "empty.db"
    empty.touch()
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not sqlite")
    no_tables = tmp_path / "no_tables.db"
    sqlite3.connect(no_tables).close()
    large = tmp_path / "large.db"
    large.write_bytes(b"1234567890")

    assert _upload(unsupported, "bad-extension").status_code == 400
    assert _upload(empty, "empty-session").status_code == 400
    assert _upload(corrupt, "corrupt-session").status_code == 400
    assert _upload(no_tables, "no-table-session").status_code == 400
    monkeypatch.setattr(main_module, "MAX_UPLOAD_BYTES", 4)
    assert _upload(large, "large-session").status_code == 413


def test_invalid_sql_dump_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(main_module, "SQLSERVER_IMPORT_SQL", False)
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(
        sql_importer,
        "TEMP_DATABASE_FOLDER",
        str(tmp_path / "converted"),
    )
    sql_file = tmp_path / "bad.sql"
    sql_file.write_text("CREATE TABLE broken (", encoding="utf-8")

    response = _upload(sql_file, "bad-sql-session")

    assert response.status_code == 400
    assert active_database.get_session_database_path("bad-sql-session") is None


def test_sql_upload_accepts_cp1252_encoded_dump(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(main_module, "SQLSERVER_IMPORT_SQL", False)
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(
        sql_importer,
        "TEMP_DATABASE_FOLDER",
        str(tmp_path / "converted"),
    )
    sql_file = tmp_path / "cp1252.sql"
    sql_file.write_bytes(
        (
            "CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT);\n"
            "INSERT INTO notes (body) VALUES ('hello\xa0world');"
        ).encode("cp1252")
    )

    response = _upload(sql_file, "cp1252-session")

    assert response.status_code == 200
    stored_path = active_database.get_session_database_path("cp1252-session")
    with sqlite3.connect(stored_path) as connection:
        value = connection.execute("SELECT body FROM notes").fetchone()[0]
    assert value == "hello\xa0world"


def test_repeated_question_on_same_database_returns_cached_response(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(response_cache_module.response_cache, "client", InMemoryRedis())
    counting_llm = CountingLLM()
    monkeypatch.setattr(chat_pipeline_module, "llm", counting_llm)
    database = tmp_path / "people.db"
    _create_people_database(database, "Alice", 100)

    assert _upload(database, "cache-session").status_code == 200

    first = client.post(
        "/chat",
        json={"question": "  Who   is highest paid? ", "session_id": "cache-session"},
    )
    second = client.post(
        "/chat",
        json={"question": "who is highest paid?", "session_id": "cache-session"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert counting_llm.answer_calls == 1


def test_chat_response_hides_token_metrics_and_returns_confidence(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(response_cache_module.response_cache, "client", InMemoryRedis())
    monkeypatch.setattr(chat_pipeline_module, "llm", CountingLLM())
    database = tmp_path / "people.db"
    _create_people_database(database, "Alice", 100)

    assert _upload(database, "presentation-session").status_code == 200

    response = client.post(
        "/chat",
        json={"question": "Who is highest paid?", "session_id": "presentation-session"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "metrics" not in payload
    assert "confidence" in payload
    assert payload["confidence"]["confidence_level"] in {"high", "medium", "low"}
    assert payload["confidence"]["confidence_reasons"]
