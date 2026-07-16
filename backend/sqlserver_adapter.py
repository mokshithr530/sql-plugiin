import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd

from config import (
    QUERY_ROW_LIMIT,
    SQLSERVER_DATABASE,
    SQLSERVER_DRIVER,
    SQLSERVER_ENCRYPT,
    SQLSERVER_HOST,
    SQLSERVER_PASSWORD,
    SQLSERVER_PORT,
    SQLSERVER_QUERY_TIMEOUT_SECONDS,
    SQLSERVER_TRUST_CERT,
    SQLSERVER_USERNAME,
)


class SQLServerAdapter:
    BLOCKED = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|MERGE|EXEC|EXECUTE|"
        r"GRANT|REVOKE|DENY|BACKUP|RESTORE|USE|ATTACH|DETACH)\b",
        re.IGNORECASE,
    )
    CROSS_DATABASE = re.compile(
        r"\b(?:FROM|JOIN)\s+[A-Za-z_][\w]*\.[A-Za-z_][\w]*\.[A-Za-z_][\w]*",
        re.IGNORECASE,
    )
    GO_LINE = re.compile(r"^\s*GO\s*(?:--.*)?$", re.IGNORECASE)
    MYSQL_VERSION_COMMENT = re.compile(r"/\*![\s\S]*?\*/;?", re.IGNORECASE)
    IMPORTS_DIR = Path(__file__).resolve().parent / "runtime" / "sqlserver_imports"

    def __init__(self):
        self._engine = None
        self._schema_cache = None
        self._schema_fingerprint_cache = None
        self._schema_prompt_cache = None

    def _connection_url(self, database=None):
        password = quote_plus(SQLSERVER_PASSWORD)
        username = quote_plus(SQLSERVER_USERNAME)
        driver = quote_plus(SQLSERVER_DRIVER)
        target_database = quote_plus(database or SQLSERVER_DATABASE)
        return (
            f"mssql+pyodbc://{username}:{password}@{SQLSERVER_HOST}:{SQLSERVER_PORT}/"
            f"{target_database}?driver={driver}&Encrypt={SQLSERVER_ENCRYPT}"
            f"&TrustServerCertificate={SQLSERVER_TRUST_CERT}"
        )

    def ensure_database(self):
        try:
            from sqlalchemy import create_engine
        except ImportError as error:
            raise RuntimeError(
                "SQL Server support requires sqlalchemy and pyodbc. "
                "Run pip install -r requirements.txt."
            ) from error

        engine = create_engine(
            self._connection_url("master"),
            pool_pre_ping=True,
            connect_args={"timeout": SQLSERVER_QUERY_TIMEOUT_SECONDS},
        )
        database_name = SQLSERVER_DATABASE.replace("]", "]]")
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(
                f"IF DB_ID(N'{database_name}') IS NULL CREATE DATABASE [{database_name}]"
            )
        engine.dispose()

    def engine(self):
        if self._engine is None:
            try:
                from sqlalchemy import create_engine
            except ImportError as error:
                raise RuntimeError(
                    "SQL Server support requires sqlalchemy and pyodbc. "
                    "Run pip install -r requirements.txt."
                ) from error

            self.ensure_database()
            self._engine = create_engine(
                self._connection_url(),
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=5,
                connect_args={"timeout": SQLSERVER_QUERY_TIMEOUT_SECONDS},
            )
        return self._engine

    def test_connection(self):
        with self.engine().connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        return True

    def _import_state_path(self, fingerprint):
        self.IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
        return self.IMPORTS_DIR / f"{fingerprint}.json"

    def file_fingerprint(self, path):
        digest = hashlib.sha256()
        with Path(path).open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def import_state(self, fingerprint):
        state_path = self._import_state_path(fingerprint)
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def save_import_state(self, fingerprint, source_name, schema_fingerprint):
        return self._save_import_state(fingerprint, source_name, schema_fingerprint, [])

    def _save_import_state(
        self,
        fingerprint,
        source_name,
        schema_fingerprint,
        imported_tables,
    ):
        state = {
            "source_type": "sqlserver",
            "connection_id": f"sqlserver:{SQLSERVER_DATABASE}:{fingerprint[:16]}",
            "database": SQLSERVER_DATABASE,
            "name": source_name,
            "fingerprint": fingerprint,
            "schema_fingerprint": schema_fingerprint,
            "imported_tables": imported_tables,
        }
        self._import_state_path(fingerprint).write_text(
            json.dumps(state),
            encoding="utf-8",
        )
        return state

    def _detect_incompatible_dump(self, line):
        markers = [
            "DELIMITER",
            "COPY ",
            "\\.",
            "PRAGMA ",
            "WITHOUT ROWID",
        ]
        upper = line.upper()
        for marker in markers:
            if marker in upper:
                raise ValueError(
                    "This .sql dump does not look SQL Server compatible. "
                    "Import it into its original database first, or provide a SQL Server dump."
                )

    def _normalize_identifier(self, name):
        parts = [part for part in name.replace("`", "").split(".") if part]
        if len(parts) == 1:
            parts = ["dbo", parts[0]]
        return ".".join(f"[{part.replace(']', ']]')}]" for part in parts[-2:])

    def _normalize_mysql_statement(self, sql):
        statement = sql.strip()
        if not statement:
            return None

        statement = self.MYSQL_VERSION_COMMENT.sub("", statement).strip()
        if not statement or statement.startswith("--"):
            return None

        upper = statement.upper()
        ignored_prefixes = (
            "SET ",
            "LOCK TABLES",
            "UNLOCK TABLES",
            "START TRANSACTION",
            "COMMIT",
        )
        if upper.startswith(ignored_prefixes):
            return None
        if "DISABLE KEYS" in upper or "ENABLE KEYS" in upper:
            return None

        statement = re.sub(
            r"DROP\s+TABLE\s+IF\s+EXISTS\s+`([A-Za-z_][\w]*)`",
            lambda match: f"DROP TABLE IF EXISTS {self._normalize_identifier(match.group(1))}",
            statement,
            flags=re.IGNORECASE,
        )
        statement = re.sub(
            r"CREATE\s+TABLE\s+`([A-Za-z_][\w]*)`\s*\(",
            lambda match: f"CREATE TABLE {self._normalize_identifier(match.group(1))} (",
            statement,
            flags=re.IGNORECASE,
        )
        statement = re.sub(
            r"INSERT\s+INTO\s+`([A-Za-z_][\w]*)`",
            lambda match: f"INSERT INTO {self._normalize_identifier(match.group(1))}",
            statement,
            flags=re.IGNORECASE,
        )

        statement = re.sub(r"`([^`]+)`", r"[\1]", statement)
        statement = re.sub(
            r"\)\s*ENGINE[\s\S]*$",
            ")",
            statement,
            flags=re.IGNORECASE,
        )
        statement = re.sub(r"\bAUTO_INCREMENT\b", "", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\bUNSIGNED\b", "", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\bTINYINT\s*\(\s*1\s*\)", "bit", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\b(TINYINT|SMALLINT|MEDIUMINT)\s*\(\s*\d+\s*\)", "int", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\b(INT|INTEGER)\s*\(\s*\d+\s*\)", "int", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\bBIGINT\s*\(\s*\d+\s*\)", "bigint", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\bBIT\s*\(\s*\d+\s*\)", "bit", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\bDOUBLE\b", "float", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\bFLOAT\b", "float", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\bDECIMAL\s*\(([^)]+)\)", r"decimal(\1)", statement, flags=re.IGNORECASE)
        statement = re.sub(
            r"\bVARCHAR\s*\((\d+)\)",
            lambda match: "nvarchar(max)"
            if int(match.group(1)) > 4000
            else f"nvarchar({match.group(1)})",
            statement,
            flags=re.IGNORECASE,
        )
        statement = re.sub(r"\bCHAR\s*\((\d+)\)", r"nchar(\1)", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\b(LONGTEXT|MEDIUMTEXT|TINYTEXT|TEXT)\b", "nvarchar(max)", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\b(LONGBLOB|MEDIUMBLOB|TINYBLOB|BLOB)\b", "nvarchar(max)", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\bJSON\b", "nvarchar(max)", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\b(DATETIME|TIMESTAMP)\b", "datetime2", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\bENUM\s*\([^)]+\)", "nvarchar(255)", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\s+ON\s+UPDATE\s+CURRENT_TIMESTAMP(?:\(\))?", "", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\s+COMMENT\s+'(?:''|[^'])*'", "", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\s+CHARACTER\s+SET\s+\w+", "", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\s+COLLATE\s+\w+", "", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\b_binary\s+('(?:''|[^'])*')", r"\1", statement, flags=re.IGNORECASE)
        statement = statement.replace("\\'", "''")

        if upper.startswith("CREATE TABLE"):
            cleaned_lines = []
            for line in statement.splitlines():
                stripped = line.strip().rstrip(",")
                if re.match(
                    r"^(KEY|UNIQUE KEY|FULLTEXT KEY|SPATIAL KEY|CONSTRAINT)\b",
                    stripped,
                    flags=re.IGNORECASE,
                ):
                    continue
                cleaned_lines.append(line)
            statement = "\n".join(cleaned_lines)
            statement = re.sub(r",\s*\)", "\n)", statement)

        return statement.strip().rstrip(";")

    def _split_insert_values(self, sql, chunk_size=900):
        match = re.match(r"(?is)^(INSERT\s+INTO\s+.+?\s+VALUES\s*)(.+)$", sql.strip())
        if not match:
            return [sql]

        prefix = match.group(1)
        values_sql = match.group(2).strip().rstrip(";")
        rows = []
        start = None
        depth = 0
        in_string = False
        index = 0

        while index < len(values_sql):
            char = values_sql[index]
            if char == "'":
                if in_string and index + 1 < len(values_sql) and values_sql[index + 1] == "'":
                    index += 2
                    continue
                in_string = not in_string
            elif not in_string:
                if char == "(":
                    if depth == 0:
                        start = index
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0 and start is not None:
                        rows.append(values_sql[start : index + 1])
                        start = None
            index += 1

        if len(rows) <= chunk_size:
            return [sql]

        return [
            prefix + ",".join(rows[offset : offset + chunk_size])
            for offset in range(0, len(rows), chunk_size)
        ]

    def _normalized_batches(self, sql):
        normalized = self._normalize_mysql_statement(sql)
        if not normalized:
            return []
        return self._split_insert_values(normalized)

    def _read_batches(self, sql_file_path):
        batch = []
        with open(sql_file_path, "r", encoding="utf-8-sig", errors="replace") as file:
            for line in file:
                self._detect_incompatible_dump(line)
                if self.GO_LINE.match(line):
                    yield from self._normalized_batches("".join(batch))
                    batch = []
                elif line.lstrip().startswith("--"):
                    continue
                elif line.rstrip().endswith(";"):
                    batch.append(line)
                    yield from self._normalized_batches("".join(batch))
                    batch = []
                else:
                    batch.append(line)

        yield from self._normalized_batches("".join(batch))

    def import_sql_file(self, sql_file_path, source_name):
        fingerprint = self.file_fingerprint(sql_file_path)
        existing = self.import_state(fingerprint)
        if existing:
            return {**existing, "already_imported": True}

        imported_tables = set()
        with self.engine().begin() as connection:
            for batch in self._read_batches(sql_file_path):
                imported_tables.update(self._created_tables(batch))
                try:
                    connection.exec_driver_sql(batch)
                except Exception as error:
                    snippet = " ".join(batch.split())[:500]
                    raise RuntimeError(f"SQL Server import failed near: {snippet}") from error

        self.clear_schema_cache()
        schema_fingerprint = self.schema_fingerprint()
        state = self._save_import_state(
            fingerprint,
            source_name,
            schema_fingerprint,
            sorted(imported_tables),
        )
        return {**state, "already_imported": False}

    def _created_tables(self, sql):
        tables = set()
        for match in re.findall(
            r"\bCREATE\s+TABLE\s+(?:\[?([A-Za-z_][\w]*)\]?\.)?\[?([A-Za-z_][\w]*)\]?",
            sql,
            flags=re.IGNORECASE,
        ):
            schema, table = match
            tables.add(f"{schema or 'dbo'}.{table}")
        return tables

    def clear_schema_cache(self):
        self._schema_cache = None
        self._schema_fingerprint_cache = None
        self._schema_prompt_cache = None

    def inspect_schema(self):
        if self._schema_cache is not None:
            return self._schema_cache

        sql = """
        SELECT
            t.TABLE_SCHEMA,
            t.TABLE_NAME,
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.IS_NULLABLE
        FROM INFORMATION_SCHEMA.TABLES t
        JOIN INFORMATION_SCHEMA.COLUMNS c
            ON c.TABLE_SCHEMA = t.TABLE_SCHEMA
            AND c.TABLE_NAME = t.TABLE_NAME
        WHERE t.TABLE_TYPE = 'BASE TABLE'
        ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME, c.ORDINAL_POSITION
        """
        schema = {}
        with self.engine().connect() as connection:
            rows = connection.exec_driver_sql(sql).mappings().all()

        for row in rows:
            table = f"{row['TABLE_SCHEMA']}.{row['TABLE_NAME']}"
            schema.setdefault(table, {"columns": [], "foreign_keys": []})
            schema[table]["columns"].append(
                {
                    "column_name": row["COLUMN_NAME"],
                    "data_type": row["DATA_TYPE"],
                    "not_null": row["IS_NULLABLE"] == "NO",
                    "primary_key": False,
                }
            )
        self._schema_cache = schema
        return schema

    def schema_prompt(self, allowed_tables=None):
        if self._schema_prompt_cache is not None:
            if allowed_tables is None:
                return self._schema_prompt_cache

        allowed = set(allowed_tables or [])
        if allowed_tables is None:
            cacheable = True
        else:
            cacheable = False

        if cacheable and self._schema_prompt_cache is not None:
            return self._schema_prompt_cache

        prompt = "DATABASE SCHEMA\n"
        for table, info in self.inspect_schema().items():
            if allowed and table not in allowed:
                continue
            prompt += f"{table}: "
            for column in info["columns"]:
                prompt += f"{column['column_name']} {column['data_type']}, "
            prompt = prompt.rstrip(", ") + "\n"
        if cacheable:
            self._schema_prompt_cache = prompt
        return prompt

    def revenue_product_sql(self, question, allowed_tables=None):
        question_lower = question.lower()
        if not (
            ("revenue" in question_lower or "sales" in question_lower)
            and ("product" in question_lower or "item" in question_lower)
            and ("highest" in question_lower or "top" in question_lower or "most" in question_lower)
        ):
            return None

        allowed = set(allowed_tables or [])
        for table, info in self.inspect_schema().items():
            if allowed and table not in allowed:
                continue
            columns = {column["column_name"].lower(): column["column_name"] for column in info["columns"]}
            if "product" in columns and "revenue" in columns:
                safe_table = ".".join(f"[{part.replace(']', ']]')}]" for part in table.split("."))
                product = f"[{columns['product'].replace(']', ']]')}]"
                revenue = f"[{columns['revenue'].replace(']', ']]')}]"
                return (
                    f"SELECT TOP 10 {product} AS product, SUM({revenue}) AS revenue "
                    f"FROM {safe_table} "
                    f"GROUP BY {product} "
                    "ORDER BY revenue DESC"
                )
        return None

    def schema_fingerprint(self):
        if self._schema_fingerprint_cache is not None:
            return self._schema_fingerprint_cache

        payload = json.dumps(self.inspect_schema(), sort_keys=True)
        self._schema_fingerprint_cache = hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()
        return self._schema_fingerprint_cache

    def validate_sql(self, sql):
        stripped = sql.strip().rstrip(";")
        if ";" in stripped:
            return {"valid": False, "errors": ["Multiple SQL statements are not allowed."]}
        if not re.match(r"^(SELECT|WITH)\b", stripped, re.IGNORECASE):
            return {"valid": False, "errors": ["Only SELECT and WITH queries are allowed."]}
        if self.BLOCKED.search(stripped):
            return {"valid": False, "errors": ["Unsafe SQL Server keyword detected."]}
        if self.CROSS_DATABASE.search(stripped):
            return {"valid": False, "errors": ["Cross-database references are not allowed."]}
        return {"valid": True, "errors": []}

    def execute_read_query(self, sql):
        validation = self.validate_sql(sql)
        if not validation["valid"]:
            raise ValueError("; ".join(validation["errors"]))

        cleaned = sql.strip().rstrip(";")
        limited_sql = cleaned
        if not re.search(r"\b(TOP|OFFSET)\b", cleaned, re.IGNORECASE):
            if re.match(r"^SELECT\b", cleaned, re.IGNORECASE):
                limited_sql = re.sub(
                    r"^SELECT\b",
                    f"SELECT TOP ({QUERY_ROW_LIMIT})",
                    cleaned,
                    count=1,
                    flags=re.IGNORECASE,
                )
            else:
                limited_sql = (
                    f"SELECT TOP ({QUERY_ROW_LIMIT}) * FROM ({cleaned}) AS limited_query"
                )
        with self.engine().connect() as connection:
            dataframe = pd.read_sql_query(limited_sql, connection)
        return dataframe

    def dry_run_query(self, sql):
        validation = self.validate_sql(sql)
        if not validation["valid"]:
            return {**validation, "query_plan": []}
        return {
            **validation,
            "query_plan": [],
            "warning": "SQL Server dry-run plan is not enabled; query was validated only.",
        }


sqlserver_adapter = SQLServerAdapter()
