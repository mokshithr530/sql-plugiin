from config import LIVE_DATABASE_CACHE_TTL_SECONDS, MAX_RETRIES
from llm import llm
from schema_reader import SchemaReader
from session_memory import session_memory
from sql_executor import sql_executor
from validator import validator
from metrics import token_metrics
from response_cache import response_cache
from sqlserver_adapter import sqlserver_adapter
from mysql_adapter import mysql_adapter
from confidence_engine import confidence_engine
import logging
import re

logger = logging.getLogger(__name__)


class ChatPipeline:
    _CASUAL_STARTERS = {
        "hello",
        "hi",
        "hey",
        "hii",
        "yo",
        "good morning",
        "good afternoon",
        "good evening",
    }

    def _ensure_database(self):
        database = session_memory.get_database()

        if not database["database_name"]:
            raise ValueError("Upload a database before asking questions.")

    def _validate_question(self, question):
        if not question or not question.strip():
            raise ValueError("Question cannot be empty.")

        return question.strip()

    def is_casual_message(self, question):
        normalized = " ".join(question.strip().lower().split())
        stripped = normalized.rstrip("!.?")
        return stripped in self._CASUAL_STARTERS

    def casual_response(self, has_database=False):
        if has_database:
            return {
                "success": True,
                "answer": (
                    "Hey, I am ready. Ask me something about the uploaded database, "
                    "like top products, revenue, order status, or customer trends."
                ),
                "sql": None,
                "result": None,
                "error": None,
                "metrics": token_metrics.get_metrics_summary(),
                "cache_hit": False,
            }

        return {
            "success": True,
            "answer": (
                "Hello. Upload a database first, then I can help you ask questions "
                "about sales, products, orders, customers, risk, or trends."
            ),
            "sql": None,
            "result": None,
            "error": None,
            "metrics": token_metrics.get_metrics_summary(),
            "cache_hit": False,
        }

    def _llm_cache_identity(self):
        provider = getattr(llm, "provider", None)
        return {
            "provider": getattr(provider, "provider_name", None),
            "model": getattr(provider, "model_name", None),
        }

    def _dataframe_payload(self, dataframe):
        return {
            "rows": len(dataframe),
            "columns": list(dataframe.columns),
            "records": dataframe.to_dict(orient="records"),
        }

    def _confidence_response(self, **signals):
        return confidence_engine.build(**signals)

    def _public_response(self, response):
        public = dict(response)
        public.pop("metrics", None)
        return public

    def _referenced_columns(self, sql, database):
        if not sql:
            return []
        schema = mysql_adapter.inspect_schema(database)
        sql_lower = sql.lower()
        columns = []
        for info in schema.values():
            for column in info["columns"]:
                name = column["column_name"]
                if re.search(rf"`?{re.escape(name.lower())}`?", sql_lower):
                    columns.append(name)
        return sorted(set(columns))[:30]

    def _has_inferred_join(self, sql):
        return bool(sql and re.search(r"\bJOIN\b", sql, re.IGNORECASE))

    def _classify_intent(self, question):
        normalized = " ".join(question.lower().split())
        metadata_patterns = [
            r"\bwhat is this database about\b",
            r"\bdescribe this database\b",
            r"\bwhat tables\b",
            r"\btables (?:exist|are available)\b",
            r"\bbusiness modules\b",
            r"\bwhat data is available\b",
            r"\bexplain this erp\b",
            r"\bdatabase summary\b",
        ]
        business_patterns = [
            r"\binsight",
            r"\bopportunit",
            r"\bperform",
            r"\brevenue",
            r"\bloss\b",
            r"\blost\b",
            r"\brisk\b",
            r"\btrend",
            r"\bcompare\b",
            r"\btop customer",
            r"\btop product",
            r"\bunderutilized",
            r"\bworst\b",
            r"\bbest\b",
        ]
        is_metadata = any(re.search(pattern, normalized) for pattern in metadata_patterns)
        is_business = any(re.search(pattern, normalized) for pattern in business_patterns)
        if is_metadata and is_business:
            return "hybrid"
        if is_metadata:
            return "metadata"
        if is_business:
            return "business_insight"
        return "data_query"

    def _unsupported_loss_answer(self):
        return (
            "Short summary\n"
            "- I could not calculate company profit or loss from the currently selected data.\n\n"
            "Limitations\n"
            "- A true loss calculation needs reliable revenue, cost, expense, refund, or margin fields tied to the same period/entity.\n"
            "- I can only analyze metrics that exist in the connected database.\n\n"
            "Next best step\n"
            "- Ask for a visible proxy such as pending payments, cancelled orders, expenses by department, or revenue by project if those tables are available."
        )

    def _is_loss_question(self, question):
        question_lower = question.lower()
        return any(word in question_lower for word in ["loss", "profit", "margin"])

    def _asks_true_company_loss(self, question):
        question_lower = question.lower()
        return "loss" in question_lower and any(
            phrase in question_lower
            for phrase in ["company", "overall", "total", "how much", "what is"]
        )

    def _has_loss_fields(self, database):
        schema = mysql_adapter.inspect_schema(database)
        revenue_markers = ("revenue", "sales", "income", "billing", "invoice")
        cost_markers = ("cost", "expense", "profit", "loss", "margin")
        has_revenue = False
        has_cost = False
        for info in schema.values():
            for column in info["columns"]:
                name = column["column_name"].lower()
                has_revenue = has_revenue or any(marker in name for marker in revenue_markers)
                has_cost = has_cost or any(marker in name for marker in cost_markers)
                if has_revenue and has_cost:
                    return True
        return False

    def ask_sqlserver(self, question, database_identity, allowed_tables=None):
        token_metrics.start()
        question = self._validate_question(question)
        if self.is_casual_message(question):
            response = self.casual_response(has_database=True)
            token_metrics.log_summary()
            return response

        cache_identity = self._llm_cache_identity()
        cached = response_cache.get_by_identity(
            question,
            database_identity,
            **cache_identity,
        )
        if cached:
            return self._public_response(cached)

        schema_prompt = sqlserver_adapter.schema_prompt(allowed_tables)
        sql = sqlserver_adapter.revenue_product_sql(question, allowed_tables)
        used_local_sql = bool(sql)
        if not sql:
            sql = llm.generate_sqlserver_sql(question, schema_prompt)
        validation = sqlserver_adapter.validate_sql(sql)

        retries = 0
        while not validation["valid"] and retries < MAX_RETRIES:
            retries += 1
            sql = llm.rewrite_failed_mysql_sql(
                question=question,
                schema_prompt=schema_prompt,
                failed_sql=sql,
                error_message="; ".join(validation["errors"]),
            )
            validation = sqlserver_adapter.validate_sql(sql)

        if not validation["valid"]:
            metrics = token_metrics.get_metrics_summary()
            token_metrics.log_summary()
            return {
                "success": False,
                "answer": "I could not turn that into a safe SQL Server query yet.",
                "sql": sql,
                "result": None,
                "error": "; ".join(validation["errors"]),
                "metrics": metrics,
            }

        try:
            dataframe = sqlserver_adapter.execute_read_query(sql)
        except Exception as error:
            metrics = token_metrics.get_metrics_summary()
            token_metrics.log_summary()
            return {
                "success": False,
                "answer": "I found a query idea, but it did not run against SQL Server.",
                "sql": sql,
                "result": None,
                "error": str(error),
                "metrics": metrics,
            }

        if used_local_sql:
            answer = self._fallback_answer(question, dataframe)
        elif len(dataframe) == 1 and len(dataframe.columns) == 1:
            column = dataframe.columns[0]
            value = dataframe.iloc[0][column]
            answer = f"{column.replace('_', ' ').title()} is {value}."
        else:
            try:
                answer = llm.generate_answer(question, dataframe)
            except RuntimeError:
                answer = self._fallback_answer(question, dataframe)

        result = self._dataframe_payload(dataframe)
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
        response_cache.set_by_identity(
            question,
            database_identity,
            response,
            **cache_identity,
            ttl_seconds=LIVE_DATABASE_CACHE_TTL_SECONDS,
        )
        return response

    def ask_mysql(self, question, database, database_identity):
        token_metrics.start()
        question = self._validate_question(question)
        if self.is_casual_message(question):
            response = self.casual_response(has_database=True)
            token_metrics.log_summary()
            return response

        cache_identity = self._llm_cache_identity()
        cached = response_cache.get_by_identity(
            question,
            database_identity,
            **cache_identity,
        )
        if cached:
            return cached

        intent = self._classify_intent(question)
        if intent == "metadata":
            metadata = mysql_adapter.metadata_prompt(database, question)
            try:
                answer = llm.generate_metadata_answer(question, metadata)
            except RuntimeError:
                summary = mysql_adapter.database_summary(database)
                answer = (
                    f"Short summary\n- This is a {summary['database_type']} database with "
                    f"{summary['table_count']} tables.\n\n"
                    f"Detected modules\n- {', '.join(summary['detected_modules']) or 'No clear modules detected.'}\n\n"
                    f"Important tables\n- {', '.join(summary['important_tables'][:10])}"
                )
            metrics = token_metrics.get_metrics_summary()
            token_metrics.log_summary()
            response = {
                "success": True,
                "answer": answer,
                "sql": None,
                "result": None,
                "error": None,
                "metrics": metrics,
                "cache_hit": False,
                "intent": intent,
                "confidence": self._confidence_response(
                    intent=intent,
                    question=question,
                    selected_tables=mysql_adapter.database_summary(database)["important_tables"][:8],
                    validation_ok=True,
                    execution_ok=True,
                    row_count=None,
                    metadata_only=True,
                ),
            }
            response = self._public_response(response)
            response_cache.set_by_identity(
                question,
                database_identity,
                response,
                **cache_identity,
                ttl_seconds=LIVE_DATABASE_CACHE_TTL_SECONDS,
            )
            return response

        if self._asks_true_company_loss(question) or (
            self._is_loss_question(question) and not self._has_loss_fields(database)
        ):
            metrics = token_metrics.get_metrics_summary()
            token_metrics.log_summary()
            response = {
                "success": True,
                "answer": self._unsupported_loss_answer(),
                "sql": None,
                "result": None,
                "error": None,
                "metrics": metrics,
                "cache_hit": False,
                "intent": intent,
                "confidence": self._confidence_response(
                    intent=intent,
                    question=question,
                    validation_ok=True,
                    execution_ok=True,
                    missing_kpi=True,
                    assumptions=1,
                    metadata_only=False,
                    limitations=[
                        "True profit/loss requires cost, expense, refund, or margin data tied to revenue."
                    ],
                ),
            }
            response = self._public_response(response)
            response_cache.set_by_identity(
                question,
                database_identity,
                response,
                **cache_identity,
                ttl_seconds=LIVE_DATABASE_CACHE_TTL_SECONDS,
            )
            return response

        relevant_tables = mysql_adapter.relevant_tables(question, database, limit=10)
        if not relevant_tables:
            relevant_tables = mysql_adapter.database_summary(database)["important_tables"][:8]
        schema_prompt = mysql_adapter.schema_prompt(database, relevant_tables or None)
        sql = (
            mysql_adapter.catalog_sql(question, database)
            or mysql_adapter.count_table_sql(question, database)
            or mysql_adapter.business_overview_sql(question, database)
        )
        used_local_sql = bool(sql)
        if not sql:
            sql = llm.generate_mysql_sql(question, schema_prompt)
        validation = mysql_adapter.validate_sql(sql, database)

        retries = 0
        while not validation["valid"] and retries < min(MAX_RETRIES, 1):
            retries += 1
            sql = llm.rewrite_failed_mysql_sql(
                question=question,
                schema_prompt=schema_prompt,
                failed_sql=sql,
                error_message="; ".join(validation["errors"]),
            )
            validation = mysql_adapter.validate_sql(sql, database)

        if not validation["valid"]:
            metrics = token_metrics.get_metrics_summary()
            token_metrics.log_summary()
            return self._public_response({
                "success": False,
                "answer": "I could not turn that into a safe MySQL query yet.",
                "sql": sql,
                "result": None,
                "error": "; ".join(validation["errors"]),
                "metrics": metrics,
                "confidence": self._confidence_response(
                    intent=intent,
                    question=question,
                    sql=sql,
                    selected_tables=relevant_tables,
                    selected_columns=self._referenced_columns(sql, database),
                    validation_ok=False,
                    execution_ok=False,
                    assumptions=1,
                    limitations=validation["errors"],
                ),
            })

        try:
            dataframe = mysql_adapter.execute_read_query(sql, database)
        except Exception as error:
            metrics = token_metrics.get_metrics_summary()
            token_metrics.log_summary()
            return self._public_response({
                "success": False,
                "answer": "I found a query idea, but it did not run against MySQL.",
                "sql": sql,
                "result": None,
                "error": str(error),
                "metrics": metrics,
                "confidence": self._confidence_response(
                    intent=intent,
                    question=question,
                    sql=sql,
                    selected_tables=relevant_tables,
                    selected_columns=self._referenced_columns(sql, database),
                    validation_ok=True,
                    execution_ok=False,
                    inferred_join=self._has_inferred_join(sql),
                    assumptions=1,
                    limitations=[str(error)],
                ),
            })

        try:
            answer = (
                self._fallback_answer(question, dataframe)
                if used_local_sql or dataframe.empty
                else llm.generate_answer(question, dataframe)
            )
        except RuntimeError:
            answer = self._fallback_answer(question, dataframe)

        result = self._dataframe_payload(dataframe)
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
            "intent": intent,
            "confidence": self._confidence_response(
                intent=intent,
                question=question,
                sql=sql,
                selected_tables=relevant_tables,
                selected_columns=list(dataframe.columns),
                validation_ok=True,
                execution_ok=True,
                row_count=len(dataframe),
                inferred_join=self._has_inferred_join(sql),
                assumptions=1 if self._has_inferred_join(sql) else 0,
            ),
        }
        response = self._public_response(response)
        response_cache.set_by_identity(
            question,
            database_identity,
            response,
            **cache_identity,
            ttl_seconds=LIVE_DATABASE_CACHE_TTL_SECONDS,
        )
        return response

    def _fallback_answer(self, question, dataframe):
        if dataframe.empty:
            return (
                "Short summary\n"
                "- I did not find matching records for that question.\n\n"
                "Limitations\n"
                "- This means the selected tables/columns did not contain enough matching data for that metric.\n\n"
                "Next step\n"
                "- Try asking with a specific table, module, date range, or business metric."
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

        if {"product", "revenue"}.issubset(columns):
            top = dataframe.iloc[0]
            product = top["product"] or "unknown product"
            revenue = float(top["revenue"] or 0)
            return (
                f"{product} has the highest revenue at {revenue:,.2f}. "
                "This is based only on the rows returned by the query."
            )

        if "row_count" in columns and len(dataframe) == 1:
            row_count = int(dataframe.iloc[0]["row_count"] or 0)
            return f"There are {row_count:,} matching rows."

        if {"table_name", "row_count"}.issubset(columns):
            rows = dataframe.head(6).to_dict(orient="records")
            bullets = "\n".join(
                f"- {row['table_name']}: {int(row['row_count']):,} rows"
                for row in rows
            )
            top = rows[0] if rows else None
            summary = (
                f"- The busiest visible area is {top['table_name']} with "
                f"{int(top['row_count']):,} rows."
                if top
                else "- No table activity was found."
            )
            return (
                "Short summary\n"
                f"{summary}\n\n"
                "Key findings\n"
                f"{bullets}\n\n"
                "Limitations\n"
                "- This is a volume-based overview, not a revenue or profit analysis."
            )

        if {"project_name", "total_billing"}.issubset(columns):
            top = dataframe.iloc[0]
            project = top["project_name"] or f"project {top.get('project_id')}"
            total = float(top["total_billing"] or 0)
            return (
                "Short summary\n"
                f"- {project} is the top project by visible billing in the selected data, with {total:,.2f}.\n\n"
                "Key findings\n"
                "- Use this table to see which projects are contributing the most billing volume.\n"
                "- A project manager can use this to spot high-value projects and projects with weak billing activity.\n"
                "- Compare receivable amount with total billing to understand where collection follow-up may be needed.\n\n"
                "Limitations\n"
                "- This is billing value, not profit or cash collected unless receivable/payment fields confirm it."
            )

        if {"department_name", "employee_count"}.issubset(columns):
            top = dataframe.iloc[0]
            department = top["department_name"] or f"department {top.get('department_id')}"
            count = int(top["employee_count"] or 0)
            return (
                "Short summary\n"
                f"- {department} has the highest staffing concentration with {count:,} employees.\n\n"
                "Key findings\n"
                "- The table ranks departments by headcount, which helps managers understand where people are allocated.\n"
                "- Larger departments may need closer workload, attendance, and cost tracking.\n"
                "- Smaller departments may be support functions or specialized teams, depending on the business context.\n\n"
                "Limitations\n"
                "- This measures staffing size, not true department performance."
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

        question = self._validate_question(question)
        if self.is_casual_message(question):
            response = self.casual_response(has_database=True)
            token_metrics.log_summary()
            return response

        self._ensure_database()
        database_path = session_memory.get_database()["database_path"]
        cache_identity = self._llm_cache_identity()
        cached = response_cache.get(question, database_path, **cache_identity)
        if cached:
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
        response_cache.set(question, database_path, response, **cache_identity)
        return response


chat_pipeline = ChatPipeline()
