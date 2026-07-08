import os
from abc import ABC, abstractmethod

try:
    import certifi_win32  # noqa: F401
except ImportError:
    certifi_win32 = None

try:
    import certifi
    os.environ.setdefault("GRPC_DEFAULT_SSL_ROOTS_FILE_PATH", certifi.where())
except ImportError:
    certifi = None

try:
    import truststore
except ImportError:
    truststore = None

if truststore:
    truststore.inject_into_ssl()

from google import genai

from config import (
    GEMINI_API_KEYS,
    GEMINI_FALLBACK_MODELS,
    GEMINI_MODEL,
    GEMINI_TIMEOUT_SECONDS,
    LLM_PROVIDER,
)
from session_memory import session_memory


def _clean_sql(sql):
    cleaned = sql.replace("```sql", "")
    cleaned = cleaned.replace("```", "")
    return cleaned.strip()


def _clean_answer(answer):
    cleaned = answer.replace("**", "")
    cleaned = cleaned.replace("`", "")
    return cleaned.strip()


class BaseLLMProvider(ABC):
    def __init__(self, provider_name, model_name):
        self.provider_name = provider_name
        self.model_name = model_name

    @abstractmethod
    def generate(self, prompt):
        raise NotImplementedError


class GeminiProvider(BaseLLMProvider):
    def __init__(self, model_name, fallback_models, api_keys, timeout_seconds):
        super().__init__("gemini", model_name)
        self.model_names = list(dict.fromkeys([model_name, *fallback_models]))
        self.api_keys = api_keys
        self.timeout_seconds = timeout_seconds
        self.active_key_index = 0
        self.client = None

        if self.api_keys:
            self._configure_key(0)

    def _configure_key(self, key_index):
        self.active_key_index = key_index
        self.client = genai.Client(
            api_key=self.api_keys[key_index],
            http_options={"timeout": self.timeout_seconds * 1000},
        )

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

    def _should_try_next_model(self, error):
        message = str(error).lower()
        retry_markers = [
            "503",
            "504",
            "unavailable",
            "deadline_exceeded",
            "deadline exceeded",
            "high demand",
            "overloaded",
            "temporarily",
            "timed out",
            "timeout",
        ]
        return any(marker in message for marker in retry_markers)

    def generate(self, prompt):
        if not self.api_keys or self.client is None:
            raise RuntimeError(
                "LLM API key is not configured. Set LLM_API_KEY, LLM_API_KEYS, GEMINI_API_KEY, or GEMINI_API_KEYS in backend/.env."
            )

        last_error = None

        for offset in range(len(self.api_keys)):
            key_index = (self.active_key_index + offset) % len(self.api_keys)
            self._configure_key(key_index)

            for model_name in self.model_names:
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                    )
                    return response.text.strip()
                except Exception as error:
                    last_error = error

                    if self._should_try_next_model(error):
                        continue

                    if not self._should_try_next_key(error):
                        break

            if last_error and not self._should_try_next_key(last_error):
                break

        raise RuntimeError(
            "LLM request failed after trying "
            f"{len(self.api_keys)} configured key(s) and "
            f"{len(self.model_names)} model(s): {last_error}"
        )


class MCPProvider(BaseLLMProvider):
    def __init__(self):
        super().__init__("mcp", "unconfigured")

    def generate(self, prompt):
        raise RuntimeError(
            "MCP provider is not implemented yet. Add an MCP-backed provider in backend/llm.py."
        )


def create_provider():
    if LLM_PROVIDER == "gemini":
        return GeminiProvider(
            model_name=GEMINI_MODEL,
            fallback_models=GEMINI_FALLBACK_MODELS,
            api_keys=GEMINI_API_KEYS,
            timeout_seconds=GEMINI_TIMEOUT_SECONDS,
        )

    if LLM_PROVIDER == "mcp":
        return MCPProvider()

    raise RuntimeError(f"Unsupported LLM provider: {LLM_PROVIDER}")


class LLMService:
    def __init__(self, provider):
        self.provider = provider

    def _generate(self, prompt):
        return self.provider.generate(prompt)

    def _conversation_history(self):
        history = session_memory.get_chat_history()
        conversation = ""

        for message in history:
            conversation += f"{message['role']}: {message['content']}\n"

        return conversation

    def generate_sql(self, question, schema_prompt):
        prompt = f"""
You are a senior data analyst and SQL engineer.

Task:
Convert the user's natural-language question into one safe SQLite SELECT query.

Database schema:
{schema_prompt}

Recent conversation:
{self._conversation_history()}

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
9. Infer joins from shared ID columns when foreign keys are not declared, such as order_id, product_id, customer_id, and seller_id.
10. For "sold most", "top product", or "best product" questions, rank by item count unless the user explicitly asks for revenue.
11. For "what should I focus on" or business recommendation questions, return useful comparison metrics, usually units/count, revenue, average price, and order count when those columns exist.

Common ecommerce patterns:
- Product/category sold most by units:
  SELECT t.product_category_name_english AS product_category, COUNT(*) AS units_sold, SUM(oi.price) AS revenue
  FROM order_items oi
  JOIN products p ON oi.product_id = p.product_id
  LEFT JOIN product_category_name_translation t ON p.product_category_name = t.product_category_name
  GROUP BY t.product_category_name_english
  ORDER BY units_sold DESC
  LIMIT 10
- Product/category to focus on:
  SELECT t.product_category_name_english AS product_category, COUNT(*) AS units_sold, SUM(oi.price) AS revenue, AVG(oi.price) AS average_price
  FROM order_items oi
  JOIN products p ON oi.product_id = p.product_id
  LEFT JOIN product_category_name_translation t ON p.product_category_name = t.product_category_name
  GROUP BY t.product_category_name_english
  ORDER BY revenue DESC
  LIMIT 10
"""

        return _clean_sql(self._generate(prompt))

    def generate_answer(self, question, dataframe):
        prompt = f"""
You are a helpful data analyst speaking to a business user.

User question:
{question}

SQL result:
{dataframe.to_string(index=False)}

Write the final answer in a natural, human style.

Rules:
1. Answer the question directly in the first sentence.
2. Use the actual values from the SQL result.
3. If there are multiple rows, summarize the top findings in plain English.
4. For recommendation questions like "what should I focus on", explain why the top option is attractive and mention one tradeoff if the data supports it.
5. If columns include revenue and units/count, compare both instead of only naming the first row.
6. If columns include revenue_at_risk, explain that this is a proxy for possible loss, not true profit/loss, unless actual cost or margin columns are present.
7. If the result is empty, say that no matching records were found and suggest what the user can try next.
8. Do not mention "SQL result", "dataframe", "snippet", or internal execution details.
9. Do not sound robotic. Be clear, warm, and concise.
10. Do not invent anything outside the result.
11. Use 2-4 short sentences for analysis questions; use a short bullet list only when comparing several rows.
"""

        return _clean_answer(self._generate(prompt))

    def rewrite_failed_sql(self, question, schema_prompt, failed_sql, error_message):
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

Use only tables and columns from the schema above. If the user asks about products, orders, customers, or sales, infer the likely joins from foreign keys and column names.

Return only one corrected SQLite SELECT or WITH query.
Do not explain, do not use markdown, and do not include unsafe SQL.
"""

        return _clean_sql(self._generate(prompt))

    def summarize_schema(self, schema_prompt):
        prompt = f"""
                Summarize this database.
                {schema_prompt}
                Keep it under 80 words."""

        return self._generate(prompt)

    def suggest_followup(self, question, answer):
        prompt = f"""
                User Question
                {question}
                Answer
                {answer}
                Suggest three useful follow-up questions.
                """

        return self._generate(prompt)


llm = LLMService(create_provider())
