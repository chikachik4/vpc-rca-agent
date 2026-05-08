from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config import settings
from dispatcher import ReportDispatcher


@pytest.mark.asyncio
async def test_report_saves_file_and_sends_slack(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REPORT_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://example.invalid/webhook")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("dispatcher.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        dispatcher = ReportDispatcher()
        await dispatcher.handle({"type": "report", "sender": "RCA", "text": "root cause"})

    saved_reports = list(tmp_path.glob("rca_*.md"))
    assert len(saved_reports) == 1
    assert saved_reports[0].read_text(encoding="utf-8") == "root cause"
    mock_client.post.assert_awaited_once()
    mock_response.raise_for_status.assert_called_once()


@pytest.mark.asyncio
async def test_report_skips_slack_when_webhook_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REPORT_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "")

    dispatcher = ReportDispatcher()

    with patch("dispatcher.httpx.AsyncClient") as client_cls:
        await dispatcher.handle({"type": "report", "sender": "RCA", "text": "root cause"})

    client_cls.assert_not_called()
    assert len(list(tmp_path.glob("rca_*.md"))) == 1
