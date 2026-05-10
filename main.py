import asyncio
import sys

from agents.architect import ArchitectAgent
from agents.rca import RCAAgent
from agents.sprint import SprintAgent
from core.config import settings
from core.logging import configure_logging, get_logger
from dispatcher import ReportDispatcher
from infrastructure.redis_client import redis_client
from observer import ObserverLoop


def _log_task_completion(task: asyncio.Task, logger):
    try:
        if task.cancelled():
            logger.warning("Task %s was cancelled", task.get_name())
            return

        exc = task.exception()
        if exc is not None:
            logger.error(
                "Task %s failed with %s: %s",
                task.get_name(),
                type(exc).__name__,
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            return

        result = task.result()
        logger.warning("Task %s exited unexpectedly with result: %r", task.get_name(), result)
    except asyncio.CancelledError:
        logger.warning("Task %s was cancelled during completion logging", task.get_name())
    except Exception as exc:
        logger.error("Failed to inspect task %s: %s", task.get_name(), exc)


async def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    configure_logging(settings.LOG_LEVEL)
    logger = get_logger(__name__)

    architect  = ArchitectAgent()
    rca        = RCAAgent()
    sprint     = SprintAgent()
    observer   = ObserverLoop()
    dispatcher = ReportDispatcher()

    logger.info("3-Agent RCA 시스템 구동 시작...")
    logger.info("  - [Architect]  rca.input  채널 대기")
    logger.info("  - [RCA]        rca.plan   채널 대기")
    logger.info("  - [Sprint]     rca.sprint 채널 대기")
    logger.info("  - [Observer]   Prometheus 자동 감시")
    logger.info("  - [Dispatcher] rca.output 채널 구독")
    logger.info("수동 트리거: redis-cli publish rca.input '{\"text\": \"API 응답 지연 발생\"}'")

    tasks: list[asyncio.Task] = []

    try:
        tasks = [
            asyncio.create_task(architect.start(),  name="architect"),
            asyncio.create_task(rca.start(),        name="rca"),
            asyncio.create_task(sprint.start(),     name="sprint"),
            asyncio.create_task(observer.start(),   name="observer"),
            asyncio.create_task(dispatcher.start(), name="dispatcher"),
        ]
        for task in tasks:
            task.add_done_callback(lambda t, l=logger: _log_task_completion(t, l))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for task, result in zip(tasks, results):
            if isinstance(result, BaseException):
                logger.error(
                    "Gather returned exception from task %s: %s: %s",
                    task.get_name(),
                    type(result).__name__,
                    result,
                    exc_info=(type(result), result, result.__traceback__),
                )
            else:
                logger.warning("Gather returned from task %s with result: %r", task.get_name(), result)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("종료 신호를 받았습니다.")
    except Exception as e:
        logger.exception("시스템 구동 중 예외 발생: %s", e)
    except BaseException as e:
        logger.exception("시스템 구동 중 치명적 예외 발생: %s", e)
    finally:
        logger.info("종료 절차를 시작합니다...")

        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        for client in getattr(rca, "_mcp_clients", []):
            try:
                client.stop(None, None, None)
            except Exception:
                pass
        if getattr(rca, "_mcp_clients", []):
            logger.info("MCP 클라이언트 종료 완료")

        try:
            await redis_client.close()
            logger.info("Redis 연결 종료 완료")
        except Exception as e:
            logger.error("Redis 종료 중 오류: %s", e)

        logger.info("안전하게 종료되었습니다.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("예기치 못한 오류로 종료: %s", e)
