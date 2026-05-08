import asyncio
import sys
import signal
from agents.architect import ArchitectAgent
from agents.rca import RCAAgent
from agents.sprint import SprintAgent
from infrastructure.redis_client import redis_client

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

    # 실행 중인 모든 태스크를 관리하기 위한 리스트
    tasks = []

    try:
        # 각 에이전트의 start()를 태스크로 생성
        tasks = [
            asyncio.create_task(architect.start()),
            asyncio.create_task(rca.start()),
            asyncio.create_task(sprint.start()),
        ]
        
        # 모든 태스크가 완료될 때까지 대기 (실제로는 무한 루프)
        await asyncio.gather(*tasks)
        
    except asyncio.CancelledError:
        print("\n[SYSTEM] 태스크 취소 요청을 받았습니다.")
    except Exception as e:
        print(f"[ERROR] 시스템 구동 중 예외 발생: {e}")
    finally:
        # 종료 절차 (Graceful Shutdown)
        print("[SYSTEM] 종료 절차를 시작합니다...")
        
        # 1. 실행 중인 에이전트 태스크 취소
        for task in tasks:
            if not task.done():
                task.cancel()
        
        # 2. MCP 클라이언트 종료 (RCA 에이전트 내부 리소스)
        if hasattr(rca, "_mcp_clients"):
            for client in rca._mcp_clients:
                try:
                    await client.__aexit__(None, None, None)
                    print(f"[SYSTEM] MCP Client 종료 완료")
                except Exception as e:
                    print(f"[ERROR] MCP Client 종료 중 오류: {e}")

        # 3. Redis 연결 종료
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
        # asyncio.run() 내부에서 CancelledError로 전파됨
        pass
    except Exception as e:
        print(f"[FATAL] 예기치 못한 오류로 종료되었습니다: {e}")
