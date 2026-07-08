import google.generativeai as genai

from session_memory import session_memory
from config import GEMINI_API_KEYS, GEMINI_MODEL, LLM_PROVIDER


def _clean_sql(sql):
    cleaned = sql.replace("```sql", "")
    cleaned = cleaned.replace("```", "")
    return cleaned.strip()


class LLMService:

    def __init__(self):

        self.provider = LLM_PROVIDER
        self.model_name = GEMINI_MODEL
        self.api_keys = GEMINI_API_KEYS
        self.active_key_index = 0
        self.model = None

        if self.provider == "gemini" and self.api_keys:
            self._configure_gemini(0)

    def _configure_gemini(self, key_index):
        self.active_key_index = key_index
        genai.configure(api_key=self.api_keys[key_index])
        self.model = genai.GenerativeModel(self.model_name)

    def _should_try_next_key(self, error):
        message = str(error).lower()

        retry_markers = [
            "quota",
            "rate",
            "resource exhausted",
            "429",
            "permission",
            "api key",
            "authentication",
        ]

        return any(marker in message for marker in retry_markers)

    # ----------------------------------
    # Private Model Call
    # ----------------------------------

    def _generate(self, prompt):

        if self.provider != "gemini":
            raise RuntimeError(
                f"Unsupported LLM provider: {self.provider}"
            )

        if not self.api_keys or self.model is None:
            raise RuntimeError(
                "Gemini API key is not configured. Set GEMINI_API_KEY or GEMINI_API_KEYS in backend/.env."
            )

        last_error = None

        for offset in range(len(self.api_keys)):
            key_index = (self.active_key_index + offset) % len(self.api_keys)
            self._configure_gemini(key_index)

            try:
                response = self.model.generate_content(prompt)
                return response.text.strip()
            except Exception as error:
                last_error = error

                if not self._should_try_next_key(error):
                    break

        raise RuntimeError(
            f"Gemini request failed after trying {len(self.api_keys)} configured key(s): {last_error}"
        )
    
    
    def generate_sql(self,question,schema_prompt):

        history = session_memory.get_chat_history()

        conversation = ""

        for message in history:

            conversation += (
                f"{message['role']}: "
                f"{message['content']}\n"
            )

        prompt = f"""
You are a senior data analyst and SQL engineer.

Task:
Convert the user's natural-language question into one safe SQLite SELECT query.

Database schema:
{schema_prompt}

Recent conversation:
{conversation}

Current question:
{question}

Rules:
1. Return only executable SQL. No markdown, comments, explanation, or code fences.
2. Use only SELECT or WITH queries.
3. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, PRAGMA, ATTACH, DETACH, or multiple statements.
4. Use only tables and columns that exist in the schema.
5. Prefer explicit column names over SELECT *.
6. Add a reasonable LIMIT when the question asks for lists, rankings, examples, or broad results.
7. Use SQLite-compatible syntax only.
8. If the question is ambiguous, choose the most likely interpretation using the schema and conversation.
"""

        return _clean_sql(self._generate(prompt))
    

    def generate_answer(self,question,dataframe):

        prompt = f"""
You are a concise business data assistant.

User question:
{question}

SQL result:
{dataframe.to_string(index=False)}

Answer requirements:
1. Answer directly in natural language.
2. Mention the important numbers or records from the result.
3. Do not invent facts outside the result.
4. If the result is empty, clearly say that no matching records were found.
5. Keep the answer short and useful.
"""

        return self._generate(prompt)
    
    
    def rewrite_failed_sql(self,question,schema_prompt,failed_sql,error_message):

        prompt = f"""
You are repairing a failed SQLite query.

Original question:
{question}

Database schema:
{schema_prompt}

Failed SQL:
{failed_sql}

Validation or database error:
{error_message}

Return only one corrected SQLite SELECT or WITH query.
Do not explain, do not use markdown, and do not include unsafe SQL.
"""

        return _clean_sql(self._generate(prompt))
    

    def summarize_schema(self,schema_prompt):
        prompt = f"""
                Summarize this database.
                {schema_prompt}
                Keep it under 80 words."""

        return self._generate(prompt)
    

    def suggest_followup(self, question,answer):

        prompt = f"""
                User Question
                {question}
                Answer
                {answer}
                Suggest three useful follow-up questions.
                """

        return self._generate(prompt)
    
    
llm = LLMService()
