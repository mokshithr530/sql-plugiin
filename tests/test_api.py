from fastapi.testclient import TestClient

import chat_pipeline as chat_pipeline_module
import main as main_module


client = TestClient(main_module.app)


class DummyLLM:
    def generate_sql(self, question, schema_prompt):
        return "SELECT name, salary FROM people ORDER BY salary DESC LIMIT 1"

    def generate_answer(self, question, dataframe):
        row = dataframe.iloc[0]
        return f"{row['name']} earns {row['salary']}."

    def rewrite_failed_sql(self, question, schema_prompt, failed_sql, error_message):
        return self.generate_sql(question, schema_prompt)


def test_upload_and_chat_pipeline(monkeypatch, tmp_path, sample_db):
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(main_module, "UPLOAD_FOLDER", str(uploads))
    monkeypatch.setattr(chat_pipeline_module, "llm", DummyLLM())

    with sample_db.open("rb") as db_file:
        upload = client.post(
            "/upload",
            files={"file": ("sample.db", db_file, "application/octet-stream")},
        )

    assert upload.status_code == 200
    upload_data = upload.json()
    assert upload_data["success"] is True
    assert upload_data["database"] == {
        "name": "sample.db",
        "type": "SQLITE",
        "tables": 1,
        "columns": 3,
    }

    chat = client.post("/chat", json={"question": "Who is highest paid?"})

    assert chat.status_code == 200
    chat_data = chat.json()
    assert chat_data["success"] is True
    assert chat_data["answer"] == "Bob earns 200."
    assert chat_data["result"]["records"] == [{"name": "Bob", "salary": 200}]


def test_chat_requires_uploaded_database():
    response = client.post("/chat", json={"question": "List people"})

    assert response.status_code == 400
    assert "Upload a database" in response.json()["detail"]
