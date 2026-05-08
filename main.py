import asyncio
import sys
from agents.architect import ArchitectAgent
from agents.rca import RCAAgent
from agents.sprint import SprintAgent
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

    try:
        await asyncio.gather(
            architect.start(),
            rca.start(),
            sprint.start(),
            observer.start(),
            dispatcher.start(),
        )
    except Exception as e:
        print(f"[ERROR] 시스템 구동 중 예외 발생: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[SYSTEM] 사용자에 의해 시스템이 종료됩니다.")
    except Exception as e:
        print(f"[FATAL] 예기치 못한 오류로 종료되었습니다: {e}")
