"""
Service de Cache — Redis
Utilisé pour mettre en cache les réponses du LLM pour des questions identiques.
"""
import os
import json
import hashlib
from redis import Redis
from backend.services.logging_service import logger

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
CACHE_ENABLED = os.getenv("ENABLE_CACHE", "true").lower() == "true"
CACHE_TTL = int(os.getenv("CACHE_TTL", 3600))  # 1 hour by default

_REDIS_CLIENT = None
_CACHE_UNAVAILABLE = False

def get_redis():
    global _REDIS_CLIENT, _CACHE_UNAVAILABLE
    if _CACHE_UNAVAILABLE:
        return None
    if _REDIS_CLIENT is None:
        hosts = [REDIS_HOST]
        if REDIS_HOST == "redis":
            hosts.append("127.0.0.1")

        last_error = None
        for host in hosts:
            try:
                candidate = Redis(
                    host=host,
                    port=REDIS_PORT,
                    decode_responses=True,
                    socket_connect_timeout=0.25,
                    socket_timeout=0.25,
                    retry_on_timeout=False,
                )
                candidate.ping()
                _REDIS_CLIENT = candidate
                break
            except Exception as e:
                last_error = e

        if _REDIS_CLIENT is None:
            _CACHE_UNAVAILABLE = True
            logger.warning(f"Could not connect to Redis: {last_error}")
            return None
    return _REDIS_CLIENT

def _get_key(prefix: str, content: str) -> str:
    h = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"chatbot:{prefix}:{h}"

def get_cached_response(prefix: str, query: str) -> str | None:
    if not CACHE_ENABLED:
        return None
    
    client = get_redis()
    if not client:
        return None
        
    key = _get_key(prefix, query)
    try:
        return client.get(key)
    except Exception as e:
        logger.error(f"Redis get error: {e}")
        return None

def set_cached_response(prefix: str, query: str, response: str, ttl: int = CACHE_TTL):
    if not CACHE_ENABLED or not response:
        return
        
    client = get_redis()
    if not client:
        return
        
    key = _get_key(prefix, query)
    try:
        client.set(key, response, ex=ttl)
    except Exception as e:
        logger.error(f"Redis set error: {e}")

def get_semantic_cache(query: str) -> tuple[str | None, str | None]:
    """Récupère une réponse sémantique (réponse + source) du cache."""
    data_raw = get_cached_response("semantic_v2", query)
    if not data_raw:
        return None, None
    try:
        data = json.loads(data_raw)
        return data.get("answer"), data.get("source")
    except Exception:
        return data_raw, None

def set_semantic_cache(query: str, answer: str, source: str | None = None, ttl: int = CACHE_TTL):
    """Stocke une réponse sémantique en JSON dans le cache."""
    if not answer:
        return
    data = json.dumps({"answer": answer, "source": source})
    set_cached_response("semantic_v2", query, data, ttl=ttl)

def invalidate_cache(prefix: str = "*"):
    client = get_redis()
    if not client:
        return
    try:
        keys = client.keys(f"chatbot:{prefix}:*")
        if keys:
            client.delete(*keys)
            logger.info(f"Invalidated {len(keys)} cache keys for prefix {prefix}")
    except Exception as e:
        logger.error(f"Redis delete error: {e}")
