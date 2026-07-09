import hashlib
import json
import logging
import os
import re

from config import CACHE_TTL_SECONDS, LLM_MODEL, LLM_PROVIDER, REDIS_URL


logger = logging.getLogger(__name__)


class ResponseCache:
    def __init__(self):
        self.client = None
        if REDIS_URL:
            try:
                import redis

                self.client = redis.Redis.from_url(
                    REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=1,
                    socket_timeout=1,
                )
                self.client.ping()
            except Exception as error:
                logger.warning("Redis cache unavailable; continuing without cache: %s", error)
                self.client = None

    def _key(self, question, database_path):
        stat = os.stat(database_path)
        normalized = re.sub(r"\s+", " ", question.strip().lower())
        identity = "|".join(
            [
                os.path.abspath(database_path),
                str(stat.st_size),
                str(stat.st_mtime_ns),
                LLM_PROVIDER,
                LLM_MODEL,
                normalized,
            ]
        )
        return "sql-assistant:answer:" + hashlib.sha256(identity.encode()).hexdigest()

    def get(self, question, database_path):
        if not self.client:
            return None
        try:
            value = self.client.get(self._key(question, database_path))
            return json.loads(value) if value else None
        except Exception as error:
            logger.warning("Redis cache read failed: %s", error)
            return None

    def set(self, question, database_path, response):
        if not self.client:
            return
        try:
            self.client.setex(
                self._key(question, database_path),
                CACHE_TTL_SECONDS,
                json.dumps(response),
            )
        except Exception as error:
            logger.warning("Redis cache write failed: %s", error)


response_cache = ResponseCache()
