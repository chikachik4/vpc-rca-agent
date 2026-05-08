import asyncio
import sys
from agents.architect import ArchitectAgent
from agents.rca import RCAAgent
from agents.sprint import SprintAgent

async def main():
    # Windows 환경에서 인코딩 문제 방지
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')

    architect = ArchitectAgent()
    rca = RCAAgent()
    sprint = SprintAgent()

    print("[SYSTEM] 3-Agent RCA 시스템 구동 시작...")
    print("   - [Architect] rca.input 채널 대기")
    print("   - [RCA]       rca.plan 채널 대기")
    print("   - [Sprint]    rca.sprint 채널 대기")
    print("\n테스트 방법: redis-cli publish rca.input '{\"text\": \"API 응답 지연 발생\"}'")

    try:
        await asyncio.gather(
            architect.start(),
            rca.start(),
            sprint.start(),
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
