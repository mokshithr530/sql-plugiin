import os
import re
import sqlite3
import hashlib
from config import TEMP_DATABASE_FOLDER


class SQLImporter:
    SQL_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")

    def __init__(self):
        self.temp_db_path = None

    def import_sql(self, sql_file_path: str) -> str:

        if not os.path.exists(sql_file_path):
            raise FileNotFoundError(f"{sql_file_path} not found.")

        # Folder to store converted databases
        temp_folder = TEMP_DATABASE_FOLDER
        os.makedirs(temp_folder, exist_ok=True)

        source_id = hashlib.sha256(
            os.path.abspath(sql_file_path).encode("utf-8")
        ).hexdigest()[:12]
        db_name = (
            os.path.splitext(os.path.basename(sql_file_path))[0]
            + f"_{source_id}_temp.sqlite"
        )

        self.temp_db_path = os.path.join(temp_folder, db_name)

        # Remove existing temp database
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

        connection = sqlite3.connect(self.temp_db_path)

        try:
            sql_script = self._read_sql_script(sql_file_path)

            sql_script = self._normalize_sql_dump(sql_script)

            connection.executescript(sql_script)
            connection.commit()

        except Exception:
            connection.close()
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
            raise

        finally:
            if connection:
                connection.close()

        if os.path.getsize(self.temp_db_path) == 0:
            os.remove(self.temp_db_path)
            raise sqlite3.DatabaseError("SQL dump did not create a readable SQLite database.")

        return self.temp_db_path

    def _read_sql_script(self, sql_file_path: str) -> str:
        last_error = None
        for encoding in self.SQL_ENCODINGS:
            try:
                with open(sql_file_path, "r", encoding=encoding) as file:
                    return file.read()
            except UnicodeDecodeError as error:
                last_error = error

        raise UnicodeDecodeError(
            last_error.encoding,
            last_error.object,
            last_error.start,
            last_error.end,
            (
                "Could not decode SQL dump. Save it as UTF-8, CP1252, or Latin-1 "
                "and try again."
            ),
        )

    def _normalize_sql_dump(self, sql_script: str) -> str:
        script = sql_script

        script = re.sub(r"/\*![\s\S]*?\*/;", "", script)
        script = re.sub(r"^\s*--.*$", "", script, flags=re.MULTILINE)
        script = re.sub(r"^\s*SET\s+.*?;\s*$", "", script, flags=re.IGNORECASE | re.MULTILINE)
        script = re.sub(r"^\s*(LOCK|UNLOCK)\s+TABLES.*?;\s*$", "", script, flags=re.IGNORECASE | re.MULTILINE)
        script = re.sub(r"^\s*(START\s+TRANSACTION|COMMIT|DELIMITER)\b.*?;\s*$", "", script, flags=re.IGNORECASE | re.MULTILINE)

        script = re.sub(r"\bAUTO_INCREMENT\b", "", script, flags=re.IGNORECASE)
        script = re.sub(r"\bUNSIGNED\b", "", script, flags=re.IGNORECASE)
        script = re.sub(r"\bTINYINT\s*\(\s*1\s*\)", "INTEGER", script, flags=re.IGNORECASE)
        script = re.sub(r"\b(INT|INTEGER|BIGINT|SMALLINT|MEDIUMINT)\s*\(\s*\d+\s*\)", "INTEGER", script, flags=re.IGNORECASE)
        script = re.sub(r"\b(VARCHAR|CHAR)\s*\(\s*\d+\s*\)", "TEXT", script, flags=re.IGNORECASE)
        script = re.sub(r"\b(DATETIME|TIMESTAMP|DATE|TIME)\b", "TEXT", script, flags=re.IGNORECASE)
        script = re.sub(r"\b(ENUM|SET)\s*\([^)]+\)", "TEXT", script, flags=re.IGNORECASE)
        script = re.sub(r"\bDOUBLE\b|\bFLOAT\b|\bDECIMAL\s*\([^)]+\)", "REAL", script, flags=re.IGNORECASE)

        script = re.sub(r"\)\s*ENGINE\s*=\s*\w+[^;]*;", ");", script, flags=re.IGNORECASE)
        script = re.sub(r"\)\s*DEFAULT\s+CHARSET\s*=\s*\w+[^;]*;", ");", script, flags=re.IGNORECASE)
        script = re.sub(r"\s+CHARACTER\s+SET\s+\w+", "", script, flags=re.IGNORECASE)
        script = re.sub(r"\s+COLLATE\s+\w+", "", script, flags=re.IGNORECASE)

        cleaned_lines = []

        for line in script.splitlines():
            stripped = line.strip()

            if re.match(r"^(KEY|UNIQUE KEY|FULLTEXT KEY|CONSTRAINT)\b", stripped, flags=re.IGNORECASE):
                continue

            cleaned_lines.append(line)

        script = "\n".join(cleaned_lines)
        script = re.sub(r",\s*\)", "\n)", script)

        return script

    def cleanup(self):
        if self.temp_db_path and os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)


sql_importer = SQLImporter()
