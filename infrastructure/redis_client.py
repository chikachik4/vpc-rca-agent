import json
import asyncio
from typing import Callable, Any, Coroutine
from redis.asyncio import Redis, ConnectionPool
from core.config import settings

class RedisPubSubClient:
    def __init__(self):
        self.pool = ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True
        )
        self.client = Redis(connection_pool=self.pool)

    async def publish(self, channel: str, message: dict):
        """메시지를 지정된 채널에 발행합니다."""
        payload = json.dumps(message)
        await self.client.publish(channel, payload)

    async def subscribe(self, channel: str, callback: Callable[[dict], Coroutine[Any, Any, None]]):
        """지정된 채널을 구독하고 메시지가 올 때마다 콜백을 실행합니다."""
        pubsub = self.client.pubsub()
        await pubsub.subscribe(channel)
        print(f"[SYSTEM] Subscribed to Redis channel: {channel}")

        async def _listen():
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            await callback(data)
                        except Exception as callback_err:
                            print(f"[ERROR] Callback error on {channel}: {callback_err}")
            except asyncio.CancelledError:
                print(f"[SYSTEM] Unsubscribing from channel: {channel}")
            except Exception as e:
                print(f"[ERROR] Redis listen error on {channel}: {e}")
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.close()

        # 백그라운드 태스크로 실행하고 태스크 객체 반환
        task = asyncio.create_task(_listen())
        return task

    async def close(self):
        """연결을 안전하게 닫습니다."""
        await self.client.aclose()

# 싱글톤 인스턴스
redis_client = RedisPubSubClient()
