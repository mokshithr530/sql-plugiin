from database_manager import db_manager
from validator import validator


def test_validator_blocks_dangerous_sql(sample_db):
    db_manager.connect(str(sample_db))

    result = validator.validate("DROP TABLE people")

    assert result["success"] is False
    assert "Blocked SQL keyword" in result["error"]


def test_validator_accepts_select_against_active_schema(sample_db):
    db_manager.connect(str(sample_db))

    result = validator.validate("SELECT name, salary FROM people")

    assert result["success"] is True


def test_validator_rejects_unknown_table_and_column(sample_db):
    db_manager.connect(str(sample_db))

    missing_table = validator.validate("SELECT name FROM employees")
    missing_column = validator.validate("SELECT department FROM people")

    assert missing_table["success"] is False
    assert "does not exist" in missing_table["error"]
    assert missing_column["success"] is False
    assert "not found" in missing_column["error"]
