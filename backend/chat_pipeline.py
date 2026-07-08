from config import MAX_RETRIES
from llm import llm
from schema_reader import SchemaReader
from session_memory import session_memory
from sql_executor import sql_executor
from validator import validator


class ChatPipeline:
    def _ensure_database(self):
        database = session_memory.get_database()

        if not database["database_name"]:
            raise ValueError("Upload a database before asking questions.")

    def _validate_question(self, question):
        if not question or not question.strip():
            raise ValueError("Question cannot be empty.")

        return question.strip()

    def _dataframe_payload(self, dataframe):
        return {
            "rows": len(dataframe),
            "columns": list(dataframe.columns),
            "records": dataframe.to_dict(orient="records"),
        }

    def ask(self, question):
        self._ensure_database()
        question = self._validate_question(question)

        reader = SchemaReader()
        schema_prompt = reader.get_schema_prompt()

        sql = llm.generate_sql(question, schema_prompt)
        validation = validator.validate(sql)

        retries = 0
        last_error = validation["error"]

        while not validation["success"] and retries < MAX_RETRIES:
            retries += 1
            sql = llm.rewrite_failed_sql(
                question=question,
                schema_prompt=schema_prompt,
                failed_sql=sql,
                error_message=last_error,
            )
            validation = validator.validate(sql)
            last_error = validation["error"]

        if not validation["success"]:
            session_memory.set_last_error(validation["error"])
            return {
                "success": False,
                "answer": "I could not safely generate SQL for that question.",
                "sql": sql,
                "result": None,
                "error": validation["error"],
            }

        execution = sql_executor.execute_safe(sql)

        retries = 0

        while not execution["success"] and retries < MAX_RETRIES:
            retries += 1
            sql = llm.rewrite_failed_sql(
                question=question,
                schema_prompt=schema_prompt,
                failed_sql=sql,
                error_message=execution["error"],
            )

            validation = validator.validate(sql)

            if not validation["success"]:
                execution = {
                    "success": False,
                    "error": validation["error"],
                }
                continue

            execution = sql_executor.execute_safe(sql)

        if not execution["success"]:
            session_memory.set_last_error(execution["error"])
            return {
                "success": False,
                "answer": "I generated SQL, but it could not be executed safely.",
                "sql": sql,
                "result": None,
                "error": execution["error"],
            }

        dataframe = execution["data"]["dataframe"]
        answer = llm.generate_answer(question, dataframe)
        result = self._dataframe_payload(dataframe)

        session_memory.add_message("user", question)
        session_memory.add_message("assistant", answer)
        session_memory.set_last_question(question)
        session_memory.set_last_sql(sql)
        session_memory.set_last_result(result)
        session_memory.set_last_error(None)

        return {
            "success": True,
            "answer": answer,
            "sql": sql,
            "result": result,
            "error": None,
        }


chat_pipeline = ChatPipeline()
