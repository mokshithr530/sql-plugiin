from config import MAX_CHAT_HISTORY

class SessionMemory:

    def __init__(self):
        self.reset()

    def reset(self):
        self.database_name = None
        self.database_path = None
        self.schema = None

        self.chat_history = []

        self.last_question = None
        self.last_sql = None
        self.last_result = None
        self.last_error = None
        self.retry_count = 0


    def set_last_error(self, error):
        self.last_error = error

    def get_last_error(self):
        return self.last_error
    
    def increment_retry(self):
        self.retry_count += 1

    def reset_retry(self):
         self.retry_count = 0

    def get_retry_count(self):
        return self.retry_count
    # -----------------------
    # Database Information
    # -----------------------

    def set_database(self, name, path):
        self.database_name = name
        self.database_path = path

    def get_database(self):
        return {
            "database_name": self.database_name,
            "database_path": self.database_path
        }

    # -----------------------
    # Schema
    # -----------------------

    def set_schema(self, schema):
        self.schema = schema

    def get_schema(self):
        return self.schema

    # -----------------------
    # Chat History
    # -----------------------

    def add_message(self, role, content): #this is for chat i have keept currently 15 messages for less overhead

        self.chat_history.append({
            "role": role,
            "content": content
    })

        if len(self.chat_history) > MAX_CHAT_HISTORY:
            self.chat_history.pop(0)


    def get_chat_history(self):
        return self.chat_history

    def clear_chat(self):
        self.chat_history = []

    # -----------------------
    # Previous Query
    # -----------------------

    def set_last_question(self, question):
        self.last_question = question

    def get_last_question(self):
        return self.last_question

    def set_last_sql(self, sql):
        self.last_sql = sql

    def get_last_sql(self):
        return self.last_sql

    def set_last_result(self, result):
        self.last_result = result

    def get_last_result(self):
        return self.last_result


session_memory = SessionMemory()