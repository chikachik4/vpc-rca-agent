from strands import tool
import httpx
from core.config import settings

@tool
async def query_prometheus(promql: str) -> str:
    """VPC3 중앙 Prometheus에 PromQL 쿼리를 실행합니다."""
    verify = settings.CA_BUNDLE_PATH if settings.CA_BUNDLE_PATH else settings.TLS_VERIFY
    try:
        async with httpx.AsyncClient(verify=verify) as client:
            r = await client.get(
                f"{settings.PROMETHEUS_URL}/api/v1/query",
                params={"query": promql},
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            return r.text
    except Exception as exc:
        return f"ERROR: Prometheus query failed: {exc}"
