"""
Cache configuration for FastAPI using Redis
"""
import aioredis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from decouple import config

async def init_cache():
    """Initialize Redis cache for FastAPI"""
    redis_url = config("REDIS_URL", default="redis://localhost:6379")
    try:
        redis = await aioredis.from_url(
            redis_url, 
            encoding="utf8", 
            decode_responses=True
        )
        FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
        print("✅ Redis cache initialized successfully")
    except Exception as e:
        print(f"⚠️  Redis cache initialization failed: {e}")
        print("⚠️  Running without cache - app will still work but slower")
        # For development: use in-memory cache if Redis is not available
        from fastapi_cache.backends.inmemory import InMemoryBackend
        FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
