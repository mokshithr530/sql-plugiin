import re

from schema_reader import schema_reader
from utils.response import success, failure
from config import BLOCKED_SQL_KEYWORDS


class SQLValidator:

    def __init__(self):

        self.blocked_keywords = BLOCKED_SQL_KEYWORDS

    # -------------------------------------

    def is_safe(self, sql):

        sql_upper = sql.upper()
        stripped = sql.strip()

        if ";" in stripped.rstrip(";"):
            return failure(
                error="Multiple SQL statements are not allowed.",
                message="Validation failed"
            )

        for keyword in self.blocked_keywords:

            if re.search(rf"\b{re.escape(keyword)}\b", sql_upper):
                return failure(
                    error=f"Blocked SQL keyword: {keyword}",
                    message="Validation failed"
                )

        return success(message="Safe")

    # -------------------------------------

    def starts_with_select(self, sql):

        sql = sql.strip().upper()

        return sql.startswith("SELECT") or sql.startswith("WITH")

    # -------------------------------------

    def validate_tables(self, sql):

        tables = schema_reader.get_tables()

        matches = re.findall(

            r"(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)",

            sql,

            flags=re.IGNORECASE

        )

        for table in matches:

            if table not in tables:

                return failure(
                    error=f"Table '{table}' does not exist.",
                    message="Validation failed"
                )

        return success(message= "Tables Valid")

    # -------------------------------------

    def validate_columns(self, sql):

        schema = schema_reader.get_column_names()

        all_columns = []

        for columns in schema.values():

            all_columns.extend(columns)

        selected = re.findall(

            r"SELECT(.*?)FROM",

            sql,

            flags=re.IGNORECASE | re.DOTALL

        )

        if not selected:

            return success(message="Columns Valid")

        cols = selected[0].split(",")

        for col in cols:

            col = col.strip()

            if col == "*":
                continue

            if "." in col:
                col = col.split(".")[-1]

            col = col.split(" AS ")[0]

            col = col.strip()

            if "(" in col:
                continue

            if col not in all_columns:

                return failure(error= f"Column '{col}' not found.",message= "validation failed")

        return success(message="Columns Valid")

    # -------------------------------------

    def validate(self, sql):

        safe_result = self.is_safe(sql)

        if not safe_result["success"]:
            return safe_result

        if not self.starts_with_select(sql):

            return failure(
                error="Only SELECT and WITH queries are allowed.",
                message="Validation failed"
            )

        tables_result = self.validate_tables(sql)

        if not tables_result["success"]:

            return tables_result

        columns_result = self.validate_columns(sql)

        if not columns_result["success"]:

            return columns_result

        return success(message="SQL Valid")


validator = SQLValidator()
