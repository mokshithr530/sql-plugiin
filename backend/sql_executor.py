import pandas as pd

from database_manager import db_manager
from utils.response import success, failure
from config import QUERY_ROW_LIMIT

class SQLExecutor:

    def __init__(self):
        pass

    def execute(self, sql):

        connection = db_manager.get_connection()

        limited_sql = sql.strip().rstrip(";")

        if " LIMIT " not in limited_sql.upper():
            limited_sql = f"{limited_sql} LIMIT {QUERY_ROW_LIMIT}"

        dataframe = pd.read_sql_query(
            limited_sql,
            connection
        )

        return dataframe

    def execute_safe(self, sql):

        try:

            dataframe = self.execute(sql)
            return success(
                    data={
                        "dataframe": dataframe,
                        "rows": len(dataframe),
                        "columns": list(dataframe.columns)},message="Query Executed")

        except Exception as e:

            return failure(
                    error=str(e),
                    message="Execution Failed"
                    )

sql_executor = SQLExecutor()
