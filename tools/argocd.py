from strands import tool
import httpx
from core.config import settings

HEADERS = {"Authorization": f"Bearer {settings.ARGOCD_TOKEN}"}

@tool
async def list_argocd_apps() -> str:
    """ArgoCD에 등록된 모든 애플리케이션 목록과 상태를 반환합니다."""
    verify = settings.CA_BUNDLE_PATH if settings.CA_BUNDLE_PATH else settings.TLS_VERIFY
    try:
        async with httpx.AsyncClient(verify=verify) as client:
            r = await client.get(
                f"{settings.ARGOCD_URL}/api/v1/applications",
                headers=HEADERS,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            return r.text
    except Exception as exc:
        return f"ERROR: ArgoCD list query failed: {exc}"

@tool
async def get_argocd_app_status(app_name: str) -> str:
    """지정한 ArgoCD 애플리케이션의 Health/Sync 상태를 반환합니다."""
    verify = settings.CA_BUNDLE_PATH if settings.CA_BUNDLE_PATH else settings.TLS_VERIFY
    try:
        async with httpx.AsyncClient(verify=verify) as client:
            r = await client.get(
                f"{settings.ARGOCD_URL}/api/v1/applications/{app_name}",
                headers=HEADERS,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            return r.text
    except Exception as exc:
        return f"ERROR: ArgoCD status query failed for {app_name}: {exc}"
