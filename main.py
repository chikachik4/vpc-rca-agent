import asyncio
import sys
from agents.architect import ArchitectAgent
from agents.rca import RCAAgent
from agents.sprint import SprintAgent
from infrastructure.redis_client import redis_client
from observer import ObserverLoop
from dispatcher import ReportDispatcher


async def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    architect  = ArchitectAgent()
    rca        = RCAAgent()
    sprint     = SprintAgent()
    observer   = ObserverLoop()
    dispatcher = ReportDispatcher()

    print("[SYSTEM] 3-Agent RCA 시스템 구동 시작...")
    print("   - [Architect]  rca.input  채널 대기")
    print("   - [RCA]        rca.plan   채널 대기")
    print("   - [Sprint]     rca.sprint 채널 대기")
    print("   - [Observer]   Prometheus 자동 감시")
    print("   - [Dispatcher] rca.output 채널 구독")
    print("\n수동 트리거: redis-cli publish rca.input '{\"text\": \"API 응답 지연 발생\"}'")

    tasks: list[asyncio.Task] = []

    try:
        tasks = [
            asyncio.create_task(architect.start(),  name="architect"),
            asyncio.create_task(rca.start(),        name="rca"),
            asyncio.create_task(sprint.start(),     name="sprint"),
            asyncio.create_task(observer.start(),   name="observer"),
            asyncio.create_task(dispatcher.start(), name="dispatcher"),
        ]
        await asyncio.gather(*tasks)
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\n[SYSTEM] 종료 신호를 받았습니다.")
    except Exception as e:
        print(f"[ERROR] 시스템 구동 중 예외 발생: {e}")
    finally:
        print("[SYSTEM] 종료 절차를 시작합니다...")

        # 1) 모든 태스크 취소 후 완료 대기 (dangling task 방지)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # 2) MCP 클라이언트 정리 (이미 종료된 경우 예외 무시)
        for client in getattr(rca, "_mcp_clients", []):
            try:
                await client.__aexit__(None, None, None)
            except Exception:
                pass
        if getattr(rca, "_mcp_clients", []):
            print("[SYSTEM] MCP 클라이언트 종료 완료")

        # 3) Redis 연결 종료
        try:
            await redis_client.close()
            print("[SYSTEM] Redis 연결 종료 완료")
        except Exception as e:
            print(f"[ERROR] Redis 종료 중 오류: {e}")

        print("[SYSTEM] 안전하게 종료되었습니다.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[SYSTEM] 사용자에 의해 시스템이 종료됩니다.")
    except Exception as e:
        print(f"[FATAL] 예기치 못한 오류로 종료되었습니다: {e}")
