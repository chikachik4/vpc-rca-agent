import time
from strands import tool
import httpx
from core.config import settings


def _tls():
    return settings.CA_BUNDLE_PATH if settings.CA_BUNDLE_PATH else settings.TLS_VERIFY


@tool
async def query_tempo_traces(service: str, minutes: int = 30, limit: int = 5) -> str:
    """Grafana Tempo에서 특정 서비스의 최근 트레이스를 조회합니다.
    service: 서비스 이름 (예: fastapi, backend)
    minutes: 조회할 최근 분 범위
    """
    now_ns = int(time.time() * 1e9)
    start_ns = now_ns - minutes * 60 * int(1e9)
    params = {
        "tags": f"service.name={service}",
        "start": start_ns,
        "end": now_ns,
        "limit": limit,
    }
    try:
        async with httpx.AsyncClient(verify=_tls()) as client:
            r = await client.get(
                f"{settings.TEMPO_URL}/api/search",
                params=params,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            return r.text
    except Exception as exc:
        return f"ERROR: Tempo search failed for service={service}: {exc}"


@tool
async def get_tempo_trace(trace_id: str) -> str:
    """Grafana Tempo에서 특정 트레이스 ID의 전체 스팬(span) 상세를 조회합니다."""
    try:
        async with httpx.AsyncClient(verify=_tls()) as client:
            r = await client.get(
                f"{settings.TEMPO_URL}/api/traces/{trace_id}",
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            return r.text
    except Exception as exc:
        return f"ERROR: Tempo trace fetch failed for id={trace_id}: {exc}"
