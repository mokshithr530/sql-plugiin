import sql_executor as sql_executor_module
from database_manager import db_manager


def test_execute_safe_returns_dataframe_payload(sample_db):
    db_manager.connect(str(sample_db))

    result = sql_executor_module.sql_executor.execute_safe(
        "SELECT name, salary FROM people ORDER BY salary DESC LIMIT 1"
    )

    assert result["success"] is True
    assert result["data"]["rows"] == 1
    assert result["data"]["columns"] == ["name", "salary"]
    assert result["data"]["dataframe"].iloc[0]["name"] == "Bob"


def test_execute_adds_default_limit(monkeypatch, sample_db):
    db_manager.connect(str(sample_db))
    monkeypatch.setattr(sql_executor_module, "QUERY_ROW_LIMIT", 2)

    dataframe = sql_executor_module.sql_executor.execute(
        "SELECT name FROM people ORDER BY id"
    )

    assert len(dataframe) == 2
    assert list(dataframe["name"]) == ["Alice", "Bob"]


def test_execute_safe_returns_failure_for_bad_sql(sample_db):
    db_manager.connect(str(sample_db))

    result = sql_executor_module.sql_executor.execute_safe(
        "SELECT missing_column FROM people"
    )

    assert result["success"] is False
    assert result["error"]
