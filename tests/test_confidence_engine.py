from confidence_engine import ConfidenceEngine


def test_high_confidence_valid_query_with_verified_join():
    confidence = ConfidenceEngine().build(
        question="Compare billing across projects",
        sql="SELECT p.project_id, SUM(b.amount) FROM project p JOIN billing b ON p.project_id=b.project_id GROUP BY p.project_id",
        selected_tables=["project", "billing"],
        selected_columns=["project_id", "amount"],
        validation_ok=True,
        execution_ok=True,
        row_count=5,
        foreign_key_evidence=True,
    )

    assert confidence["confidence_level"] == "high"
    assert confidence["confidence_score"] >= 75
    assert confidence["confidence_reasons"]


def test_medium_confidence_inferred_join_is_penalized():
    confidence = ConfidenceEngine().build(
        question="Compare billing across projects",
        sql="SELECT p.project_id, SUM(b.amount) FROM project p JOIN billing b ON p.project_id=b.project_id GROUP BY p.project_id",
        selected_tables=["project", "billing"],
        selected_columns=["project_id", "amount"],
        validation_ok=True,
        execution_ok=True,
        row_count=5,
        inferred_join=True,
        assumptions=1,
    )

    assert confidence["confidence_level"] == "medium"
    assert any("inferred" in item.lower() for item in confidence["limitations"])


def test_low_confidence_missing_kpi_data():
    confidence = ConfidenceEngine().build(
        question="What is the company loss?",
        selected_tables=[],
        selected_columns=[],
        validation_ok=True,
        execution_ok=True,
        missing_kpi=True,
        assumptions=1,
    )

    assert confidence["confidence_level"] == "low"
    assert confidence["confidence_score"] < 50
    assert confidence["limitations"]


def test_validation_failure_cannot_be_high_confidence():
    confidence = ConfidenceEngine().build(
        question="delete data",
        sql="DELETE FROM people",
        validation_ok=False,
        execution_ok=False,
    )

    assert confidence["confidence_level"] != "high"
    assert confidence["confidence_score"] <= 59


def test_execution_failure_cannot_be_high_confidence():
    confidence = ConfidenceEngine().build(
        question="show people",
        sql="SELECT * FROM people",
        selected_tables=["people"],
        selected_columns=["id"],
        validation_ok=True,
        execution_ok=False,
    )

    assert confidence["confidence_level"] != "high"
    assert confidence["confidence_score"] <= 59
