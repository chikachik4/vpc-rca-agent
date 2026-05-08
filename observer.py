import asyncio
import httpx
from infrastructure.redis_client import redis_client
from core.config import settings


def _tls():
    return settings.CA_BUNDLE_PATH if settings.CA_BUNDLE_PATH else settings.TLS_VERIFY


class ObserverLoop:
    """Prometheus를 주기적으로 폴링하여 임계값 초과 시 rca.input에 이벤트를 발행합니다."""

    QUERIES = [
        {
            "name": "high_cpu",
            "promql": 'sum(rate(container_cpu_usage_seconds_total{id="/",cluster="vpc1"}[2m]))',
            "threshold": settings.CPU_ALERT_THRESHOLD,
            "symptom_template": "VPC1 CPU 사용량 이상: {value:.2f} cores (임계값 {threshold})",
        },
        {
            "name": "pod_restart",
            "promql": 'sum(increase(kube_pod_container_status_restarts_total{cluster="vpc1"}[5m]))',
            "threshold": 3,
            "symptom_template": "VPC1 Pod 재시작 급증: {value:.0f}회/5분",
        },
    ]

    async def _query(self, promql: str) -> float:
        try:
            async with httpx.AsyncClient(verify=_tls()) as client:
                r = await client.get(
                    f"{settings.PROMETHEUS_URL}/api/v1/query",
                    params={"query": promql},
                    timeout=settings.REQUEST_TIMEOUT_SECONDS,
                )
                r.raise_for_status()
                data = r.json()
                result = data["data"]["result"]
                return float(result[0]["value"][1]) if result else 0.0
        except KeyError as e:
            print(f"[Observer] Prometheus 응답 파싱 실패 (예상치 못한 구조): {e}")
            return 0.0
        except Exception as e:
            print(f"[Observer] Prometheus 쿼리 실패: {e}")
            return 0.0

    async def start(self):
        print(f"[Observer] Prometheus 감시 시작 (간격: {settings.OBSERVER_INTERVAL_SEC}s)")
        while True:
            for q in self.QUERIES:
                value = await self._query(q["promql"])
                if value > q["threshold"]:
                    symptom = q["symptom_template"].format(
                        value=value, threshold=q["threshold"]
                    )
                    print(f"[Observer] 이상 감지: {symptom}")
                    await redis_client.publish("rca.input", {
                        "source": "auto",
                        "text": symptom,
                        "metric": {"name": q["name"], "value": value},
                    })
            await asyncio.sleep(settings.OBSERVER_INTERVAL_SEC)
