import pytest

import active_database
from sqlserver_adapter import SQLServerAdapter


def test_sqlserver_validate_accepts_select_and_with():
    adapter = SQLServerAdapter()

    assert adapter.validate_sql("SELECT TOP (10) name FROM dbo.people")["valid"] is True
    assert (
        adapter.validate_sql(
            "WITH paid AS (SELECT name FROM dbo.people) SELECT * FROM paid"
        )["valid"]
        is True
    )


def test_sqlserver_validate_rejects_unsafe_sql():
    adapter = SQLServerAdapter()

    assert adapter.validate_sql("DELETE FROM dbo.people")["valid"] is False
    assert adapter.validate_sql("EXEC dbo.do_work")["valid"] is False
    assert adapter.validate_sql("SELECT * FROM otherdb.dbo.people")["valid"] is False
    assert adapter.validate_sql("SELECT 1; SELECT 2")["valid"] is False


def test_sqlserver_go_batches_are_streamed(tmp_path):
    adapter = SQLServerAdapter()
    sql_file = tmp_path / "dump.sql"
    sql_file.write_text(
        "CREATE TABLE dbo.people (id int);\nGO\nINSERT INTO dbo.people VALUES (1);\nGO\n",
        encoding="utf-8",
    )

    assert list(adapter._read_batches(sql_file)) == [
        "CREATE TABLE dbo.people (id int)",
        "INSERT INTO dbo.people VALUES (1)",
    ]


def test_sqlserver_incompatible_dump_has_clear_error(tmp_path):
    adapter = SQLServerAdapter()
    sql_file = tmp_path / "mysql.sql"
    sql_file.write_text("COPY people FROM stdin;", encoding="utf-8")

    with pytest.raises(ValueError, match="does not look SQL Server compatible"):
        list(adapter._read_batches(sql_file))


def test_mysql_dump_batches_are_normalized_for_sqlserver(tmp_path):
    adapter = SQLServerAdapter()
    sql_file = tmp_path / "mysql.sql"
    sql_file.write_text(
        """
-- MySQL dump
DROP TABLE IF EXISTS `account_section`;
CREATE TABLE `account_section` (
  `section_id` int NOT NULL AUTO_INCREMENT,
  `bank_name` varchar(45) DEFAULT NULL,
  `approval_remarks` mediumtext,
  PRIMARY KEY (`section_id`),
  KEY `idx_bank` (`bank_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
LOCK TABLES `account_section` WRITE;
INSERT INTO `account_section` VALUES (1,'hello'),(2,'it\\'s ok');
UNLOCK TABLES;
""",
        encoding="utf-8",
    )

    batches = list(adapter._read_batches(sql_file))

    assert batches[0] == "DROP TABLE IF EXISTS [dbo].[account_section]"
    assert "CREATE TABLE [dbo].[account_section]" in batches[1]
    assert "[section_id] int NOT NULL" in batches[1]
    assert "IDENTITY" not in batches[1]
    assert "[bank_name] nvarchar(45)" in batches[1]
    assert "KEY `idx_bank`" not in batches[1]
    assert batches[2] == "INSERT INTO [dbo].[account_section] VALUES (1,'hello'),(2,'it''s ok')"


def test_mysql_binary_string_prefix_is_removed(tmp_path):
    adapter = SQLServerAdapter()
    sql_file = tmp_path / "binary.sql"
    sql_file.write_text("INSERT INTO `files` VALUES (1,_binary 'NA');", encoding="utf-8")

    assert list(adapter._read_batches(sql_file)) == [
        "INSERT INTO [dbo].[files] VALUES (1,'NA')"
    ]


def test_mysql_large_varchar_uses_nvarchar_max(tmp_path):
    adapter = SQLServerAdapter()
    sql_file = tmp_path / "large_varchar.sql"
    sql_file.write_text(
        """
CREATE TABLE `tax` (
  `id` int NOT NULL,
  `emp_name` varchar(5000) DEFAULT NULL
) ENGINE=InnoDB;
""",
        encoding="utf-8",
    )

    batch = list(adapter._read_batches(sql_file))[0]

    assert "[emp_name] nvarchar(max)" in batch


def test_mysql_large_insert_is_split_for_sqlserver(tmp_path):
    adapter = SQLServerAdapter()
    sql_file = tmp_path / "large_insert.sql"
    values = ",".join(f"({index},'name {index}')" for index in range(1001))
    sql_file.write_text(f"INSERT INTO `people` VALUES {values};", encoding="utf-8")

    batches = list(adapter._read_batches(sql_file))

    assert len(batches) == 2
    assert batches[0].startswith("INSERT INTO [dbo].[people] VALUES ")
    assert batches[0].count("),(") == 899
    assert batches[1].count("),(") == 100


def test_sqlserver_simple_select_limit_uses_top(monkeypatch):
    adapter = SQLServerAdapter()
    captured = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    def fake_read_sql_query(sql, connection):
        captured["sql"] = sql

        class FakeDataFrame:
            columns = ["product"]

            def __len__(self):
                return 0

        return FakeDataFrame()

    monkeypatch.setattr(adapter, "engine", lambda: FakeEngine())
    monkeypatch.setattr("sqlserver_adapter.pd.read_sql_query", fake_read_sql_query)

    adapter.execute_read_query("SELECT product FROM dbo.sales ORDER BY product")

    assert captured["sql"].startswith("SELECT TOP (")
    assert "ORDER BY product" in captured["sql"]


def test_sqlserver_duplicate_import_state(monkeypatch, tmp_path):
    adapter = SQLServerAdapter()
    monkeypatch.setattr(adapter, "IMPORTS_DIR", tmp_path / "imports")

    state = adapter.save_import_state("abc123", "dump.sql", "schema123")

    assert adapter.import_state("abc123") == state
    assert state["connection_id"].startswith("sqlserver:")
    assert state["connection_id"].endswith(":abc123")


def test_session_can_store_sqlserver_connection(monkeypatch, tmp_path):
    monkeypatch.setattr(active_database, "SESSIONS_DIR", tmp_path / "sessions")

    active_database.save_session_sqlserver_connection(
        "sqlserver-session",
        "sqlserver:db:fingerprint",
        "SqlAssistant",
        "dump.sql",
        "schema123",
    )
    source = active_database.get_session_source("sqlserver-session")

    assert source["source_type"] == "sqlserver"
    assert source["connection_id"] == "sqlserver:db:fingerprint"
    assert active_database.get_session_database_path("sqlserver-session") is None
