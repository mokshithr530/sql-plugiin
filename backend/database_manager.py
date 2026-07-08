import sqlite3
import os
from config import SUPPORTED_DATABASES

class DatabaseManager:
    def __init__(self):
        self.connection = None
        self.database_path = None
        self.database_type = None

    def connect(self, database_path: str):
        """
        Connect to any supported database.
        """

        self.disconnect()

        extension = os.path.splitext(database_path)[1].lower()

        if extension in [".db", ".sqlite"]:
            self.connection = sqlite3.connect(
                database_path,
                check_same_thread=False
            )
            self.database_type = "sqlite"

        elif extension == ".sql":
            from sql_importer import sql_importer

            sqlite_database = sql_importer.import_sql(database_path)

            self.connection = sqlite3.connect(
                sqlite_database,
                check_same_thread=False
            )

            self.database_type = "sqlite"

            self.database_path = sqlite_database

            return self.connection

        else:
            raise Exception("Unsupported database type.")

        self.database_path = database_path

        return self.connection

    def get_connection(self):
        if self.connection is None:
            raise Exception("No database connected.")

        return self.connection

    def get_database_type(self):
        return self.database_type

    def disconnect(self):
        if self.connection:
            self.connection.close()
            self.connection = None


db_manager = DatabaseManager()
