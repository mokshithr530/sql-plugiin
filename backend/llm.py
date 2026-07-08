import google.generativeai as genai

from session_memory import session_memory
from config import GEMINI_API_KEY, GEMINI_MODEL, LLM_PROVIDER


def _clean_sql(sql):
    cleaned = sql.replace("```sql", "")
    cleaned = cleaned.replace("```", "")
    return cleaned.strip()


class LLMService:

    def __init__(self):

        self.provider = LLM_PROVIDER
        self.model_name = GEMINI_MODEL
        self.model = None

        if self.provider == "gemini" and GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel(self.model_name)

    # ----------------------------------
    # Private Model Call
    # ----------------------------------

    def _generate(self, prompt):

        if self.provider != "gemini":
            raise RuntimeError(
                f"Unsupported LLM provider: {self.provider}"
            )

        if not GEMINI_API_KEY or self.model is None:
            raise RuntimeError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in backend/.env."
            )

        response = self.model.generate_content(prompt)

        return response.text.strip()
    
    
    def generate_sql(self,question,schema_prompt):

        history = session_memory.get_chat_history()

        conversation = ""

        for message in history:

            conversation += (
                f"{message['role']}: "
                f"{message['content']}\n"
            )

        prompt = f"""

        You are an expert SQL engineer.
        Generate ONLY SQL.
        DATABASE SCHEMA
        {schema_prompt}
        Conversation
        {conversation}
        Current Question
        {question}

        Rules
        1. Return ONLY SQL.
        2. Never explain.
        3. Never use markdown.
        4. Never use ```sql
        5. Use only existing tables.
        6. Use only existing columns.

        """

        return _clean_sql(self._generate(prompt))
    

    def generate_answer(self,question,dataframe):

        prompt = f"""
                You are a business assistant.
                Question
                {question}
                SQL Result
                {dataframe.to_string(index=False)}
                Answer naturally.
                Keep it concise and as if you are assisting."""

        return self._generate(prompt)
    
    
    def rewrite_failed_sql(self,question,schema_prompt,failed_sql,error_message):

        prompt = f"""

                The following SQL failed.
                Question
                {question}
                Schema
                {schema_prompt}
                Generated SQL
                {failed_sql}
                Database Error
                {error_message}
                Generate corrected SQL.
                Return ONLY SQL.

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
