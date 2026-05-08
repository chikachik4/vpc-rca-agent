import asyncio
import json
from typing import Any, Callable, Coroutine

from redis.asyncio import ConnectionPool, Redis

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class RedisPubSubClient:
    def __init__(self):
        self.pool = ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True,
        )
        self.client = Redis(connection_pool=self.pool)

    async def publish(self, channel: str, message: dict):
        payload = json.dumps(message, ensure_ascii=False)
        await self.client.publish(channel, payload)

    async def subscribe(self, channel: str, callback: Callable[[dict], Coroutine[Any, Any, None]]):
        pubsub = self.client.pubsub()
        await pubsub.subscribe(channel)
        logger.info("Subscribed to Redis channel: %s", channel)

        async def _listen():
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            await callback(data)
                        except json.JSONDecodeError as e:
                            logger.error("JSON 파싱 실패 on %s: %s", channel, e)
                        except Exception as e:
                            logger.error("Callback 오류 on %s: %s", channel, e)
            except asyncio.CancelledError:
                logger.info("Unsubscribing from channel: %s", channel)
            except Exception as e:
                logger.error("Redis listen 오류 on %s: %s", channel, e)
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.close()

        task = asyncio.create_task(_listen())
        return task

    async def close(self):
        await self.client.aclose()


redis_client = RedisPubSubClient()
