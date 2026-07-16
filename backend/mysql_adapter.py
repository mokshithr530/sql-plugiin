import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd

from config import (
    MYSQL_DATABASE_PREFIX,
    MYSQL_ALLOWED_DATABASES,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_QUERY_TIMEOUT_SECONDS,
    MYSQL_USERNAME,
    QUERY_ROW_LIMIT,
)
from business_catalog import business_catalog


class MySQLAdapter:
    MYSQL_MARKERS = (
        "ENGINE=INNODB",
        "AUTO_INCREMENT",
        "LOCK TABLES",
        "UNLOCK TABLES",
        "/*!",
    )
    BLOCKED = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|EXEC|"
        r"EXECUTE|GRANT|REVOKE|LOAD|LOCK|UNLOCK|USE)\b",
        re.IGNORECASE,
    )
    TABLE_REF = re.compile(
        r"\b(?:FROM|JOIN)\s+`?([A-Za-z_][\w]*)`?(?:\s+(?:AS\s+)?`?[A-Za-z_][\w]*`?)?",
        re.IGNORECASE,
    )
    IMPORTS_DIR = Path(__file__).resolve().parent / "runtime" / "mysql_imports"

    def __init__(self):
        self._engines = {}
        self._schema_cache = {}
        self._schema_fingerprint_cache = {}
        self._summary_cache = {}

    def _connection_url(self, database=None):
        username = quote_plus(MYSQL_USERNAME)
        password = quote_plus(MYSQL_PASSWORD)
        target = f"/{quote_plus(database)}" if database else ""
        return f"mysql+pymysql://{username}:{password}@{MYSQL_HOST}:{MYSQL_PORT}{target}?charset=utf8mb4"

    def engine(self, database=None):
        key = database or "__server__"
        if key not in self._engines:
            try:
                from sqlalchemy import create_engine
            except ImportError as error:
                raise RuntimeError(
                    "MySQL support requires sqlalchemy and pymysql. "
                    "Run pip install -r requirements.txt."
                ) from error

            self._engines[key] = create_engine(
                self._connection_url(database),
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=5,
                connect_args={
                    "connect_timeout": MYSQL_QUERY_TIMEOUT_SECONDS,
                    "read_timeout": MYSQL_QUERY_TIMEOUT_SECONDS,
                    "write_timeout": MYSQL_QUERY_TIMEOUT_SECONDS,
                },
            )
        return self._engines[key]

    def test_connection(self):
        with self.engine().connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        return True

    def file_fingerprint(self, path):
        digest = hashlib.sha256()
        with Path(path).open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def is_mysql_dump(self, sql_file_path, max_bytes=1024 * 1024):
        sample = Path(sql_file_path).open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
        ).read(max_bytes)
        upper = sample.upper()
        if any(marker in upper for marker in self.MYSQL_MARKERS):
            return True
        return bool(re.search(r"`[A-Za-z_][\w]*`", sample))

    def _safe_database_name(self, session_id, fingerprint):
        safe_session = re.sub(r"[^A-Za-z0-9_]", "_", session_id)[:32] or "session"
        return (
            f"{MYSQL_DATABASE_PREFIX}_{safe_session}_{fingerprint[:8]}_"
            f"{uuid.uuid4().hex[:8]}"
        ).lower()

    def _quote_identifier(self, identifier):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
            raise ValueError(f"Invalid MySQL identifier: {identifier}")
        return f"`{identifier}`"

    def _import_state_path(self, database):
        self.IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
        return self.IMPORTS_DIR / f"{database}.json"

    def _save_import_state(self, database, source_name, fingerprint, schema_fingerprint):
        state = {
            "source_type": "mysql",
            "connection_id": f"mysql:{database}:{fingerprint[:16]}",
            "database": database,
            "name": source_name,
            "fingerprint": fingerprint,
            "schema_fingerprint": schema_fingerprint,
        }
        self._import_state_path(database).write_text(json.dumps(state), encoding="utf-8")
        return state

    def create_database(self, database):
        quoted = self._quote_identifier(database)
        with self.engine().connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(
                f"CREATE DATABASE IF NOT EXISTS {quoted} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )

    def drop_database(self, database):
        quoted = self._quote_identifier(database)
        with self.engine().connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {quoted}")
        self.clear_schema_cache(database)

    def native_client(self):
        mysql_path = shutil.which("mysql")
        if mysql_path:
            return {
                "kind": "host",
                "args": [
                    mysql_path,
                    "--protocol=tcp",
                    "-h",
                    MYSQL_HOST,
                    "-P",
                    str(MYSQL_PORT),
                    "-u",
                    MYSQL_USERNAME,
                ],
            }
        docker_path = shutil.which("docker")
        if docker_path and MYSQL_HOST in {"127.0.0.1", "localhost"}:
            try:
                result = subprocess.run(
                    [docker_path, "inspect", "-f", "{{.State.Running}}", "sql-assistant-mysql"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except Exception:
                return None
            if result.returncode == 0 and result.stdout.strip().lower() == "true":
                return {
                    "kind": "docker",
                    "args": [
                        docker_path,
                        "exec",
                        "-i",
                        "-e",
                        "MYSQL_PWD",
                        "sql-assistant-mysql",
                        "mysql",
                        "-u",
                        MYSQL_USERNAME,
                    ],
                }
        return None

    def _native_import(self, sql_file_path, database):
        client = self.native_client()
        if not client:
            raise RuntimeError("mysql client is not available.")

        env = None
        if client["kind"] == "host":
            env = {**__import__("os").environ, "MYSQL_PWD": MYSQL_PASSWORD}
        else:
            env = {**__import__("os").environ, "MYSQL_PWD": MYSQL_PASSWORD}
        args = [*client["args"], database]
        prefix = b"SET SESSION innodb_strict_mode=OFF;\nSET FOREIGN_KEY_CHECKS=0;\nSET UNIQUE_CHECKS=0;\n"
        suffix = b"\nSET UNIQUE_CHECKS=1;\nSET FOREIGN_KEY_CHECKS=1;\n"

        with tempfile.TemporaryFile(mode="w+b") as stderr_file:
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=stderr_file,
                env=env,
            )
            assert process.stdin is not None
            try:
                process.stdin.write(prefix)
                with Path(sql_file_path).open("rb") as dump:
                    for chunk in iter(lambda: dump.read(1024 * 1024), b""):
                        process.stdin.write(chunk)
                process.stdin.write(suffix)
                process.stdin.close()
                return_code = process.wait()
            except Exception:
                process.kill()
                process.wait()
                raise

            stderr_file.seek(0)
            stderr = stderr_file.read().decode("utf-8", errors="replace").strip()
            if return_code != 0:
                readable = stderr[-2000:] if stderr else f"mysql exited with code {return_code}"
                raise RuntimeError(readable)
        return client["kind"]

    def _read_statements(self, sql_file_path):
        statement = []
        with open(sql_file_path, "r", encoding="utf-8-sig", errors="replace") as file:
            for line in file:
                stripped = line.strip()
                upper = stripped.upper()
                if not stripped or stripped.startswith("--"):
                    continue
                if upper.startswith("DELIMITER"):
                    raise ValueError(
                        "This MySQL dump uses DELIMITER/stored routine syntax, which this POC importer does not support."
                    )
                statement.append(line)
                if stripped.endswith(";"):
                    sql = "".join(statement).strip().rstrip(";")
                    if sql:
                        yield sql
                    statement = []
        sql = "".join(statement).strip().rstrip(";")
        if sql:
            yield sql

    def _python_import(self, sql_file_path, database):
        raw_connection = self.engine(database).raw_connection()
        try:
            with raw_connection.cursor() as cursor:
                cursor.execute("SET SESSION innodb_strict_mode=OFF")
                cursor.execute("SET FOREIGN_KEY_CHECKS=0")
                cursor.execute("SET UNIQUE_CHECKS=0")
                try:
                    for statement in self._read_statements(sql_file_path):
                        try:
                            cursor.execute(statement)
                        except Exception as error:
                            snippet = " ".join(statement.split())[:500]
                            raise RuntimeError(f"MySQL import failed near: {snippet}") from error
                finally:
                    cursor.execute("SET UNIQUE_CHECKS=1")
                    cursor.execute("SET FOREIGN_KEY_CHECKS=1")
            raw_connection.commit()
        except Exception:
            raw_connection.rollback()
            raise
        finally:
            raw_connection.close()

    def import_sql_file(self, sql_file_path, source_name, session_id):
        if not self.is_mysql_dump(sql_file_path):
            raise ValueError("This .sql file does not look like a MySQL dump.")

        started = time.perf_counter()
        progress = ["Preparing database"]
        fingerprint = self.file_fingerprint(sql_file_path)
        database = self._safe_database_name(session_id, fingerprint)
        native_error = None
        import_method = "python"

        self.create_database(database)
        progress.append("Importing")
        try:
            native_started = time.perf_counter()
            import_method = f"native:{self._native_import(sql_file_path, database)}"
            native_duration = time.perf_counter() - native_started
        except Exception as error:
            native_error = str(error)
            self.drop_database(database)
            self.create_database(database)
            python_started = time.perf_counter()
            self._python_import(sql_file_path, database)
            native_duration = None
            python_duration = time.perf_counter() - python_started
        else:
            python_duration = None

        self.clear_schema_cache(database)
        schema_fingerprint = self.schema_fingerprint(database)
        duration = time.perf_counter() - started
        progress.append("Completed")
        return {
            **self._save_import_state(database, source_name, fingerprint, schema_fingerprint),
            "already_imported": False,
            "import_method": import_method,
            "import_duration_seconds": round(duration, 3),
            "native_duration_seconds": round(native_duration, 3) if native_duration is not None else None,
            "python_duration_seconds": round(python_duration, 3) if python_duration is not None else None,
            "native_error": native_error,
            "progress": progress,
        }

    def list_allowed_databases(self):
        with self.engine().connect() as connection:
            rows = connection.exec_driver_sql("SHOW DATABASES").fetchall()
        databases = [row[0] for row in rows]
        system = {"information_schema", "mysql", "performance_schema", "sys"}
        if MYSQL_ALLOWED_DATABASES:
            allowed = set(MYSQL_ALLOWED_DATABASES)
            return sorted(database for database in databases if database in allowed)
        return sorted(
            database
            for database in databases
            if database not in system
        )

    def attach_database(self, database, source_name=None):
        if database not in self.list_allowed_databases():
            raise ValueError("Selected MySQL database is not configured or allowed.")
        schema = self.inspect_schema(database)
        if not schema:
            raise ValueError("Selected MySQL database does not contain any tables.")
        schema_fingerprint = self.schema_fingerprint(database)
        return {
            "source_type": "mysql",
            "connection_id": f"mysql:{database}:{schema_fingerprint[:16]}",
            "database": database,
            "name": source_name or database,
            "schema_fingerprint": schema_fingerprint,
            "already_imported": True,
            "import_method": "existing",
            "import_duration_seconds": 0,
            "progress": ["Preparing database", "Completed"],
        }

    def clear_schema_cache(self, database=None):
        if database:
            fingerprint = self._schema_fingerprint_cache.get(database)
            self._schema_cache.pop(database, None)
            self._schema_fingerprint_cache.pop(database, None)
            self._summary_cache.pop(database, None)
            if fingerprint:
                business_catalog.clear(fingerprint)
        else:
            self._schema_cache.clear()
            self._schema_fingerprint_cache.clear()
            self._summary_cache.clear()
            business_catalog.clear()

    def inspect_schema(self, database):
        if database in self._schema_cache:
            return self._schema_cache[database]

        sql = """
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """
        schema = {}
        with self.engine(database).connect() as connection:
            rows = connection.exec_driver_sql(sql).mappings().all()
        for row in rows:
            table = row["TABLE_NAME"]
            schema.setdefault(table, {"columns": [], "foreign_keys": []})
            schema[table]["columns"].append(
                {
                    "column_name": row["COLUMN_NAME"],
                    "name": row["COLUMN_NAME"],
                    "data_type": row["DATA_TYPE"],
                    "not_null": row["IS_NULLABLE"] == "NO",
                    "primary_key": row["COLUMN_KEY"] == "PRI",
                }
            )
        self._schema_cache[database] = schema
        return schema

    def schema_prompt(self, database, allowed_tables=None):
        allowed = set(allowed_tables or [])
        prompt = "DATABASE SCHEMA\n"
        for table, info in self.inspect_schema(database).items():
            if allowed and table not in allowed:
                continue
            prompt += f"{table}: "
            for column in self._compact_columns(info["columns"]):
                prompt += f"{column['column_name']} {column['data_type']}, "
            prompt = prompt.rstrip(", ") + "\n"
        return prompt

    def _compact_columns(self, columns, max_columns=18):
        priority_markers = (
            "id",
            "name",
            "date",
            "time",
            "amount",
            "total",
            "price",
            "cost",
            "expense",
            "revenue",
            "qty",
            "quantity",
            "status",
            "type",
            "category",
            "department",
            "project",
            "customer",
            "client",
            "vendor",
            "employee",
            "asset",
            "material",
        )
        scored = []
        for index, column in enumerate(columns):
            name = column["column_name"].lower()
            score = 10 if column.get("primary_key") else 0
            score += sum(1 for marker in priority_markers if marker in name)
            scored.append((score, -index, column))
        selected = [column for _, _, column in sorted(scored, reverse=True)[:max_columns]]
        return sorted(selected, key=lambda column: columns.index(column))

    def database_summary(self, database):
        if database in self._summary_cache:
            return self._summary_cache[database]

        schema = self.inspect_schema(database)
        row_counts = {
            item["table"]: item["approx_rows"]
            for item in self._largest_tables(database)
        }
        catalog = business_catalog.overview(
            schema,
            source_type="mysql",
            row_counts=row_counts,
            fingerprint=self.schema_fingerprint(database),
        )
        summary = {
            "database_type": "MySQL",
            "schema_fingerprint": catalog["schema_fingerprint"],
            "table_count": catalog["table_count"],
            "detected_modules": catalog["detected_modules"],
            "important_tables": [
                table["table"] if isinstance(table, dict) else table
                for table in catalog["important_tables"]
            ],
            "largest_tables": self._largest_tables(database)[:8],
            "key_relationships": catalog["key_relationships"],
            "unsupported_kpis": catalog["unsupported_kpis"],
            "short_schema_summary": catalog["short_schema_summary"],
        }
        self._summary_cache[database] = summary
        return summary

    def business_catalog(self, database):
        return business_catalog.build(
            self.inspect_schema(database),
            source_type="mysql",
            row_counts={
                item["table"]: item["approx_rows"]
                for item in self._largest_tables(database)
            },
            fingerprint=self.schema_fingerprint(database),
        )

    def analyze_question(self, question, database):
        return business_catalog.analyze_question(
            question,
            self.inspect_schema(database),
            source_type="mysql",
            row_counts={
                item["table"]: item["approx_rows"]
                for item in self._largest_tables(database)
            },
            fingerprint=self.schema_fingerprint(database),
        )

    def metadata_prompt(self, database, question):
        return json.dumps(
            {
                **self.database_summary(database),
                "question_relevant_tables": self.relevant_tables(question, database, limit=6),
            },
            indent=2,
        )

    def _detected_modules(self, schema):
        module_keywords = {
            "hr": ("employee", "emp_", "payroll", "attendance", "designation", "department"),
            "projects": ("project", "site", "boq", "milestone", "dpr"),
            "finance": ("finance", "payment", "bank", "bill", "budget", "tax", "invoice"),
            "procurement": ("po_", "purchase", "vendor", "quote", "intend", "indent"),
            "assets": ("asset", "machinery", "repair", "breakdown"),
            "inventory": ("store", "material", "stock", "spare", "grn"),
            "logistics": ("logistic", "transport", "vehicle", "freight", "frieght"),
            "clients": ("client", "customer", "correspond"),
            "admin": ("admin", "module", "role", "privilege", "user"),
        }
        tables = [table.lower() for table in schema]
        modules = []
        for module, markers in module_keywords.items():
            if any(any(marker in table for marker in markers) for table in tables):
                modules.append(module)
        return modules

    def _important_tables(self, schema):
        noisy = re.compile(r"(?:hist|history|approval|attachment|access|log|notification)")
        scored = []
        for table, info in schema.items():
            lower = table.lower()
            score = len(info["columns"])
            if lower.endswith("_table") or lower.endswith("_master") or lower.endswith("_mst"):
                score += 20
            if any(marker in lower for marker in ["employee", "project", "client", "vendor", "material", "asset", "payment", "po_", "department"]):
                score += 15
            if noisy.search(lower):
                score -= 15
            scored.append((score, table))
        return [table for _, table in sorted(scored, key=lambda item: (-item[0], item[1]))]

    def _largest_tables(self, database):
        sql = """
        SELECT TABLE_NAME, COALESCE(TABLE_ROWS, 0) AS row_count
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
        ORDER BY TABLE_ROWS DESC
        LIMIT 20
        """
        with self.engine(database).connect() as connection:
            rows = connection.exec_driver_sql(sql).mappings().all()
        return [
            {"table": row["TABLE_NAME"], "approx_rows": int(row["row_count"] or 0)}
            for row in rows
        ]

    def _relationship_hints(self, schema, tables):
        selected = set(tables[:30])
        column_to_tables = {}
        for table in selected:
            for column in schema[table]["columns"]:
                name = column["column_name"].lower()
                if name.endswith("_id") or name == "id":
                    column_to_tables.setdefault(name, []).append(table)
        return [
            {"column": column, "tables": owners[:6]}
            for column, owners in column_to_tables.items()
            if len(owners) > 1
        ]

    def relevant_tables(self, question, database, limit=20):
        question_lower = question.lower()
        words = self._expanded_words(question_lower)
        matches = []
        for table, info in self.inspect_schema(database).items():
            table_lower = table.lower()
            table_words = self._expanded_words(table_lower)
            column_words = set()
            for column in info["columns"]:
                column_words.update(self._expanded_words(column["column_name"].lower()))
            score = 0
            if table_lower in question_lower:
                score += 100
            if any(f"{word}_table" == table_lower for word in words):
                score += 80
            score += len(words & table_words) * 10
            score += len(words & column_words)
            if re.search(r"(?:hist|history|approval|attachment|access|log|notification)", table_lower):
                score -= 5
            if score > 0:
                matches.append((score, table))
        return [
            table
            for _, table in sorted(matches, key=lambda item: (-item[0], item[1]))[:limit]
        ]

    def count_table_sql(self, question, database):
        question_lower = question.lower()
        if not any(phrase in question_lower for phrase in ["how many", "count", "number of"]):
            return None
        words = self._expanded_words(question_lower)
        for table in self.inspect_schema(database):
            if table.lower() in question_lower:
                return f"SELECT COUNT(*) AS row_count FROM {self._quote_identifier(table)}"
        for table in self.relevant_tables(question, database, limit=10):
            table_lower = table.lower()
            if any(table_lower == word or table_lower == f"{word}_table" for word in words):
                return f"SELECT COUNT(*) AS row_count FROM {self._quote_identifier(table)}"
        return None

    def business_overview_sql(self, question, database):
        question_lower = question.lower()
        if not any(word in question_lower for word in ["insight", "opportunity", "performing well", "overview"]):
            return None
        tables = [
            item["table"]
            for item in self.database_summary(database)["largest_tables"]
            if item["table"] in self.inspect_schema(database)
        ][:6]
        if not tables:
            return None
        parts = [
            f"SELECT '{table}' AS table_name, COUNT(*) AS row_count FROM {self._quote_identifier(table)}"
            for table in tables
        ]
        return "\nUNION ALL\n".join(parts) + "\nORDER BY row_count DESC"

    def catalog_sql(self, question, database):
        question_lower = question.lower()
        schema = self.inspect_schema(database)

        if (
            "billing" in question_lower
            and "project" in question_lower
            and {"client_bill_raising", "project_mst"}.issubset(schema)
        ):
            return """
SELECT
    p.project_id,
    p.project_name,
    COUNT(*) AS bill_count,
    SUM(c.total_amount) AS total_billing,
    SUM(c.amount_to_be_received_this_bill) AS receivable_amount
FROM client_bill_raising c
JOIN project_mst p
    ON c.project_id = p.project_id
GROUP BY p.project_id, p.project_name
ORDER BY total_billing DESC
LIMIT 10
""".strip()

        if (
            "employee" in question_lower
            and "department" in question_lower
            and {"employee_table", "department"}.issubset(schema)
        ):
            return """
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM department d
LEFT JOIN employee_table e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY employee_count DESC
LIMIT 10
""".strip()

        if (
            "department" in question_lower
            and "perform" in question_lower
            and {"employee_table", "department"}.issubset(schema)
        ):
            return """
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM department d
LEFT JOIN employee_table e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY employee_count DESC
LIMIT 10
""".strip()

        return None

    def _expanded_words(self, text):
        words = set(re.findall(r"[a-z0-9]+", text.lower()))
        expanded = set(words)
        for word in words:
            if word.endswith("ies") and len(word) > 3:
                expanded.add(f"{word[:-3]}y")
            if word.endswith("s") and len(word) > 3:
                expanded.add(word[:-1])
            if word.endswith("es") and len(word) > 4:
                expanded.add(word[:-2])
        return expanded

    def schema_fingerprint(self, database):
        if database not in self._schema_fingerprint_cache:
            payload = json.dumps(self.inspect_schema(database), sort_keys=True)
            self._schema_fingerprint_cache[database] = hashlib.sha256(
                payload.encode("utf-8")
            ).hexdigest()
        return self._schema_fingerprint_cache[database]

    def validate_sql(self, sql, database):
        stripped = sql.strip().rstrip(";")
        if ";" in stripped:
            return {"valid": False, "errors": ["Multiple SQL statements are not allowed."]}
        if not re.match(r"^(SELECT|WITH)\b", stripped, re.IGNORECASE):
            return {"valid": False, "errors": ["Only SELECT and WITH queries are allowed."]}
        if self.BLOCKED.search(stripped):
            return {"valid": False, "errors": ["Unsafe MySQL keyword detected."]}
        if re.search(r"\b(?:FROM|JOIN)\s+`?[A-Za-z_][\w]*`?\.`?[A-Za-z_][\w]*`?", stripped, re.IGNORECASE):
            return {"valid": False, "errors": ["Cross-database references are not allowed."]}

        schema = self.inspect_schema(database)
        known_tables = set(schema)
        cte_names = set()
        if re.match(r"^WITH\b", stripped, re.IGNORECASE):
            cte_names = {
                match.group(1)
                for match in re.finditer(
                    r"(?:WITH|,)\s+`?([A-Za-z_][\w]*)`?\s+AS\s*\(",
                    stripped,
                    flags=re.IGNORECASE,
                )
            }
        referenced = {match.group(1) for match in self.TABLE_REF.finditer(stripped)}
        unknown = sorted(
            table for table in referenced if table not in known_tables and table not in cte_names
        )
        if unknown:
            return {"valid": False, "errors": [f"Unknown table(s): {', '.join(unknown)}"]}
        return {"valid": True, "errors": []}

    def execute_read_query(self, sql, database):
        validation = self.validate_sql(sql, database)
        if not validation["valid"]:
            raise ValueError("; ".join(validation["errors"]))

        cleaned = sql.strip().rstrip(";")
        limited_sql = cleaned if re.search(r"\bLIMIT\b", cleaned, re.IGNORECASE) else f"SELECT * FROM ({cleaned}) AS limited_query LIMIT {QUERY_ROW_LIMIT}"
        with self.engine(database).connect() as connection:
            return pd.read_sql_query(limited_sql, connection)

    def dry_run_query(self, sql, database):
        validation = self.validate_sql(sql, database)
        if not validation["valid"]:
            return {**validation, "query_plan": []}
        with self.engine(database).connect() as connection:
            rows = connection.exec_driver_sql(f"EXPLAIN {sql.strip().rstrip(';')}").mappings().all()
        return {**validation, "query_plan": [dict(row) for row in rows]}


mysql_adapter = MySQLAdapter()
