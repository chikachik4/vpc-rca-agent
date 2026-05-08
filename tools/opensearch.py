from strands import tool
import httpx
from core.config import settings

@tool
async def search_logs(query: str, index: str = "logs-*", size: int = 10) -> str:
    """OpenSearch에서 로그를 전문 검색합니다."""
    body = {"query": {"match": {"message": query}}, "size": size}
    verify = settings.CA_BUNDLE_PATH if settings.CA_BUNDLE_PATH else settings.TLS_VERIFY
    try:
        async with httpx.AsyncClient(verify=verify) as client:
            r = await client.post(
                f"{settings.OPENSEARCH_URL}/{index}/_search",
                json=body,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            return r.text
    except Exception as exc:
        return f"ERROR: OpenSearch search failed on index {index}: {exc}"

@tool
async def vector_search(query_text: str, index: str = "rca-cases", k: int = 3) -> str:
    """OpenSearch k-NN으로 유사 장애 사례를 벡터 검색합니다."""
    body = {"query": {"neural": {"embedding": {"query_text": query_text, "k": k}}}}
    verify = settings.CA_BUNDLE_PATH if settings.CA_BUNDLE_PATH else settings.TLS_VERIFY
    try:
        async with httpx.AsyncClient(verify=verify) as client:
            r = await client.post(
                f"{settings.OPENSEARCH_URL}/{index}/_search",
                json=body,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            return r.text
    except Exception as exc:
        return f"ERROR: OpenSearch vector search failed on index {index}: {exc}"
