import asyncio
from datetime import datetime
from pathlib import Path

import httpx

from core.config import settings
from core.logging import get_logger
from infrastructure.redis_client import redis_client

logger = get_logger(__name__)


class ReportDispatcher:
    """
    Subscribe to rca.output.
    type="status" logs progress.
    type="report" saves the RCA report and sends it to Slack when configured.
    """

    def __init__(self):
        self._subscription_task: asyncio.Task | None = None
        Path(settings.REPORT_DIR).mkdir(exist_ok=True)

    async def _save_file(self, text: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path(settings.REPORT_DIR) / f"rca_{ts}.md"
        path.write_text(text, encoding="utf-8")
        return str(path)

    async def _send_slack(self, text: str):
        if not settings.SLACK_WEBHOOK_URL:
            logger.warning("SLACK_WEBHOOK_URL is not set; skipping RCA Slack notification")
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    settings.SLACK_WEBHOOK_URL,
                    json={"text": f"[RCA Report]\n```{text[:2900]}```"},
                    timeout=settings.REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                logger.info("RCA report sent to Slack")
        except Exception as e:
            logger.error("Slack send failed: %s", e)

    async def handle(self, msg: dict):
        sender = msg.get("sender", "SYSTEM")
        text = msg.get("text", "")
        mtype = msg.get("type", "status")

        if mtype == "report":
            logger.info("[%s] RCA report received", sender)
            path = await self._save_file(text)
            logger.info("RCA report saved: %s", path)
            await self._send_slack(text)
        else:
            logger.info("[%s] %s", sender, text)

    async def start(self):
        logger.info("[Dispatcher] subscribing to rca.output...")
        self._subscription_task = await redis_client.subscribe("rca.output", self.handle)
        await asyncio.Future()
