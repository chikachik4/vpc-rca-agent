import httpx
from strands import tool

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


def _tls():
    return settings.CA_BUNDLE_PATH if settings.CA_BUNDLE_PATH else settings.TLS_VERIFY


@tool
async def search_logs(query: str, index: str = "logs-*", size: int = 10) -> str:
    """OpenSearch에서 로그를 전문 검색합니다."""
    body = {"query": {"match": {"message": query}}, "size": size}
    try:
        async with httpx.AsyncClient(verify=_tls()) as client:
            r = await client.post(
                f"{settings.OPENSEARCH_URL}/{index}/_search",
                json=body,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            return r.text
    except Exception as exc:
        logger.error("OpenSearch search failed on index %s: %s", index, exc)
        return f"ERROR: OpenSearch search failed on index {index}: {exc}"


@tool
async def vector_search(query_text: str, index: str = "rca-cases", k: int = 3) -> str:
    """OpenSearch k-NN으로 유사 장애 사례를 벡터 검색합니다.
    rca-cases 인덱스에 벡터 파이프라인이 구성되어 있어야 합니다.
    """
    body = {"query": {"neural": {"embedding": {"query_text": query_text, "k": k}}}}
    try:
        async with httpx.AsyncClient(verify=_tls()) as client:
            r = await client.post(
                f"{settings.OPENSEARCH_URL}/{index}/_search",
                json=body,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            return r.text
    except Exception as exc:
        logger.error("OpenSearch vector search failed on index %s: %s", index, exc)
        return f"ERROR: OpenSearch vector search failed on index {index}: {exc}"
