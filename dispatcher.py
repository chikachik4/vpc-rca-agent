import asyncio
import httpx
from datetime import datetime
from pathlib import Path
from infrastructure.redis_client import redis_client
from core.config import settings


class ReportDispatcher:
    """
    rca.output 채널을 구독합니다.
    type="status" → 콘솔만 출력
    type="report"  → 콘솔 + 파일 저장 + Slack 발송
    """

    def __init__(self):
        Path(settings.REPORT_DIR).mkdir(exist_ok=True)

    async def _save_file(self, text: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path(settings.REPORT_DIR) / f"rca_{ts}.md"
        path.write_text(text, encoding="utf-8")
        return str(path)

    async def _send_slack(self, text: str):
        if not settings.SLACK_WEBHOOK_URL:
            return
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    settings.SLACK_WEBHOOK_URL,
                    json={"text": f"🚨 *RCA 리포트*\n```{text[:2900]}```"},
                    timeout=5.0,
                )
        except Exception as e:
            print(f"[Dispatcher] Slack 발송 실패: {e}")

    async def handle(self, msg: dict):
        sender = msg.get("sender", "SYSTEM")
        text   = msg.get("text", "")
        mtype  = msg.get("type", "status")

        print(f"\n[{sender}] {text}")

        if mtype == "report":
            path = await self._save_file(text)
            print(f"📁 리포트 저장: {path}")
            await self._send_slack(text)

    async def start(self):
        print("📤 [Dispatcher] rca.output 구독 시작...")
        await redis_client.subscribe("rca.output", self.handle)
        await asyncio.Future()
