from config import MAX_RETRIES
from llm import llm
from schema_reader import SchemaReader
from session_memory import session_memory
from sql_executor import sql_executor
from validator import validator
from metrics import token_metrics
from response_cache import response_cache
import logging

logger = logging.getLogger(__name__)


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

    def _fallback_answer(self, question, dataframe):
        if dataframe.empty:
            return (
                "I did not find matching records for that question. "
                "Try asking with a specific table, product category, or date range."
            )

        columns = set(dataframe.columns)
        question_lower = question.lower()

        if {"product_category", "units_sold", "revenue"}.issubset(columns):
            top = dataframe.iloc[0]
            category = top["product_category"] or "uncategorized products"
            units = int(top["units_sold"])
            revenue = float(top["revenue"])

            if "focus" in question_lower or "should" in question_lower:
                return (
                    f"I would focus first on {category}. It leads this view with "
                    f"{units:,} units sold and about {revenue:,.2f} in revenue, "
                    "so it has both demand and business impact. Compare it with the next few categories before making a final decision, especially if margin data is available."
                )

            return (
                f"The most sold product category is {category}, with {units:,} units sold. "
                f"It generated about {revenue:,.2f} in revenue, so it is also commercially important, not just high-volume."
            )

        if {"order_status", "affected_orders", "revenue_at_risk"}.issubset(columns):
            top = dataframe.iloc[0]
            status = top["order_status"]
            orders = int(top["affected_orders"])
            revenue_at_risk = float(top["revenue_at_risk"] or 0)

            return (
                "I cannot calculate true profit or loss from this database because it does not include product cost, margin, or refund-cost fields. "
                f"As a practical proxy, the biggest visible risk is {status} orders: {orders:,} orders tied to about {revenue_at_risk:,.2f} in item value. "
                "To manage this, start by reducing cancellations/unavailable orders, checking seller fulfillment issues, and tracking margin or refund data in the next version."
            )

        first_row = dataframe.iloc[0].to_dict()
        readable_values = ", ".join(
            f"{key}: {value}"
            for key, value in first_row.items()
        )

        return f"The top result is {readable_values}."

    def _ecommerce_product_sql(self, question):
        question_lower = question.lower()
        schema = session_memory.get_schema() or {}
        tables = set(schema.keys())

        required_tables = {
            "order_items",
            "products",
            "product_category_name_translation",
        }

        if not required_tables.issubset(tables):
            return None

        product_words = ["product", "item", "category"]
        sold_words = ["sold", "selling", "most", "top", "best"]
        focus_words = ["focus", "recommend", "should", "priority", "improve"]

        asks_product = any(word in question_lower for word in product_words)
        asks_sales_rank = any(word in question_lower for word in sold_words)
        asks_focus = any(word in question_lower for word in focus_words)

        if not asks_product or not (asks_sales_rank or asks_focus):
            return None

        order_by = "revenue DESC" if asks_focus else "units_sold DESC"

        return f"""
SELECT
    t.product_category_name_english AS product_category,
    COUNT(*) AS units_sold,
    SUM(oi.price) AS revenue,
    AVG(oi.price) AS average_price
FROM order_items oi
JOIN products p
    ON oi.product_id = p.product_id
LEFT JOIN product_category_name_translation t
    ON p.product_category_name = t.product_category_name
GROUP BY t.product_category_name_english
ORDER BY {order_by}
LIMIT 10
""".strip()

    def _ecommerce_loss_sql(self, question):
        question_lower = question.lower()
        schema = session_memory.get_schema() or {}
        tables = set(schema.keys())

        required_tables = {
            "orders",
            "order_items",
        }

        if not required_tables.issubset(tables):
            return None

        loss_words = ["loss", "lost", "risk", "problem", "manage", "reduce"]
        asks_loss = any(word in question_lower for word in loss_words)

        if not asks_loss:
            return None

        return """
SELECT
    o.order_status,
    COUNT(DISTINCT o.order_id) AS affected_orders,
    SUM(oi.price + oi.freight_value) AS revenue_at_risk,
    AVG(oi.price + oi.freight_value) AS average_order_item_value
FROM orders o
JOIN order_items oi
    ON o.order_id = oi.order_id
WHERE o.order_status IN ('canceled', 'unavailable')
GROUP BY o.order_status
ORDER BY revenue_at_risk DESC
LIMIT 10
""".strip()

    def ask(self, question):
        # Start token tracking
        token_metrics.start()

        self._ensure_database()
        question = self._validate_question(question)
        database_path = session_memory.get_database()["database_path"]
        cached = response_cache.get(question, database_path)
        if cached:
            cached["cache_hit"] = True
            session_memory.add_message("user", question)
            session_memory.add_message("assistant", cached["answer"])
            return cached

        reader = SchemaReader()
        schema_prompt = reader.get_schema_prompt()

        sql = (
            self._ecommerce_product_sql(question)
            or self._ecommerce_loss_sql(question)
        )

        if not sql:
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
            metrics = token_metrics.get_metrics_summary()
            token_metrics.log_summary()
            return {
                "success": False,
                "answer": (
                    "I could not turn that into a safe query yet. "
                    "Try asking it with the table or field name, for example: "
                    "'Which product had the highest total sales?'"
                ),
                "sql": sql,
                "result": None,
                "error": validation["error"],
                "metrics": metrics,
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
            metrics = token_metrics.get_metrics_summary()
            token_metrics.log_summary()
            return {
                "success": False,
                "answer": (
                    "I found a query idea, but it did not run against this database. "
                    "Try rephrasing with a bit more detail, such as the metric you want "
                    "to rank by: quantity sold, revenue, or order count."
                ),
                "sql": sql,
                "result": None,
                "error": execution["error"],
                "metrics": metrics,
            }

        dataframe = execution["data"]["dataframe"]
        try:
            answer = llm.generate_answer(question, dataframe)
        except RuntimeError:
            answer = self._fallback_answer(question, dataframe)

        result = self._dataframe_payload(dataframe)

        session_memory.add_message("user", question)
        session_memory.add_message("assistant", answer)
        session_memory.set_last_question(question)
        session_memory.set_last_sql(sql)
        session_memory.set_last_result(result)
        session_memory.set_last_error(None)

        metrics = token_metrics.get_metrics_summary()
        token_metrics.log_summary()

        response = {
            "success": True,
            "answer": answer,
            "sql": sql,
            "result": result,
            "error": None,
            "metrics": metrics,
            "cache_hit": False,
        }
        response_cache.set(question, database_path, response)
        return response


chat_pipeline = ChatPipeline()
