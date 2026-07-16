import hashlib
import json
import logging
import re
from pathlib import Path

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
                logger.info("Redis connected")
            except Exception as error:
                logger.warning(
                    "Redis unavailable (caching disabled): %s",
                    error,
                )
                self.client = None
        else:
            logger.info("Redis unavailable (caching disabled)")

    def normalize_question(self, question):
        return re.sub(r"\s+", " ", question.strip().lower())

    def database_fingerprint(self, database_path):
        path = Path(database_path)
        digest = hashlib.sha256()
        with path.open("rb") as database_file:
            for chunk in iter(lambda: database_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _key_for_identity(self, question, database_identity, provider=None, model=None):
        normalized = self.normalize_question(question)
        identity = "|".join(
            [
                database_identity,
                normalized,
                provider or LLM_PROVIDER,
                model or LLM_MODEL,
            ]
        )
        return "sql-assistant:answer:" + hashlib.sha256(identity.encode()).hexdigest()

    def _key(self, question, database_path, provider=None, model=None):
        return self._key_for_identity(
            question,
            self.database_fingerprint(database_path),
            provider,
            model,
        )

    def get(self, question, database_path, provider=None, model=None):
        return self.get_by_identity(
            question,
            self.database_fingerprint(database_path),
            provider,
            model,
        )

    def get_by_identity(self, question, database_identity, provider=None, model=None):
        if not self.client:
            return None
        try:
            value = self.client.get(
                self._key_for_identity(question, database_identity, provider, model)
            )
            logger.info("Cache HIT" if value else "Cache MISS")
            return json.loads(value) if value else None
        except Exception as error:
            logger.warning("Redis cache read failed: %s", error)
            return None

    def set(self, question, database_path, response, provider=None, model=None):
        self.set_by_identity(
            question,
            self.database_fingerprint(database_path),
            response,
            provider,
            model,
        )

    def set_by_identity(
        self,
        question,
        database_identity,
        response,
        provider=None,
        model=None,
        ttl_seconds=CACHE_TTL_SECONDS,
    ):
        if not self.client:
            return
        try:
            self.client.setex(
                self._key_for_identity(question, database_identity, provider, model),
                ttl_seconds,
                json.dumps(response),
            )
            logger.info("Cache STORE")
        except Exception as error:
            logger.warning("Redis cache write failed: %s", error)


response_cache = ResponseCache()
