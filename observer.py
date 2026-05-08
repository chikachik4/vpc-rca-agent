import asyncio

import httpx

from core.config import settings
from core.logging import get_logger
from infrastructure.redis_client import redis_client

logger = get_logger(__name__)


def _tls():
    return settings.CA_BUNDLE_PATH if settings.CA_BUNDLE_PATH else settings.TLS_VERIFY


class ObserverLoop:
    """Prometheus를 주기적으로 폴링하여 임계값 초과 시 rca.input에 이벤트를 발행합니다."""

    @property
    def QUERIES(self):
        s = settings
        return [
            {
                "name": "high_cpu",
                "promql": 'sum(rate(container_cpu_usage_seconds_total{id="/",cluster="vpc1"}[2m]))',
                "threshold": s.CPU_ALERT_THRESHOLD,
                "compare": "gt",
                "symptom_template": "VPC1 CPU 사용량 이상: {value:.2f} cores (임계값 {threshold})",
            },
            {
                "name": "pod_restart",
                "promql": 'sum(increase(kube_pod_container_status_restarts_total{cluster="vpc1"}[5m]))',
                "threshold": s.POD_RESTART_THRESHOLD,
                "compare": "gt",
                "symptom_template": "VPC1 Pod 재시작 급증: {value:.0f}회/5분 (임계값 {threshold})",
            },
            {
                "name": "health_score_low",
                "promql": "job:bookjjeok_health_score",
                "threshold": s.HEALTH_SCORE_THRESHOLD,
                "compare": "lt",
                "symptom_template": "VPC2 Health Score 저하: {value:.1f} (임계값 {threshold} 미만)",
            },
            {
                "name": "redis_miss_rate",
                "promql": 'rate(cache_gets_total{result="miss",job="vpc1-backend"}[2m])',
                "threshold": s.REDIS_MISS_RATE_THRESHOLD,
                "compare": "gt",
                "symptom_template": "VPC1 Redis Cache Miss 급증: {value:.3f} req/s (임계값 {threshold})",
            },
            {
                "name": "db_connections",
                "promql": 'avg(hikaricp_connections_active{job="vpc1-backend"})',
                "threshold": s.DB_CONN_THRESHOLD,
                "compare": "gt",
                "symptom_template": "VPC1 DB 연결 과부하: {value:.0f}개 활성 (임계값 {threshold})",
            },
            {
                "name": "response_time",
                "promql": (
                    'avg(rate(http_server_requests_seconds_sum{job="vpc1-backend"}[2m])'
                    ' / rate(http_server_requests_seconds_count{job="vpc1-backend"}[2m]))'
                ),
                "threshold": s.RESPONSE_TIME_THRESHOLD,
                "compare": "gt",
                "symptom_template": "VPC1 응답 지연: {value:.3f}s (임계값 {threshold}s)",
            },
            {
                "name": "envoy_error_rate",
                "promql": "job:envoy_error_rate:rate5m",
                "threshold": s.ERROR_RATE_THRESHOLD,
                "compare": "gt",
                "symptom_template": "Envoy 에러율 급증: {value:.1%} (임계값 {threshold:.0%})",
            },
        ]

    async def _query(self, promql: str) -> float | None:
        """None 반환은 Prometheus 자체가 응답 불가 상태임을 의미합니다."""
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
                if not result:
                    return 0.0
                return float(result[0]["value"][1])
        except KeyError as e:
            logger.warning("Prometheus 응답 구조 파싱 실패 (%s): %s", promql[:60], e)
            return None
        except httpx.HTTPStatusError as e:
            logger.error("Prometheus HTTP 오류 (%s): %s", promql[:60], e)
            return None
        except Exception as e:
            logger.error("Prometheus 쿼리 실패 (%s): %s", promql[:60], e)
            return None

    def _breached(self, value: float, threshold: float, compare: str) -> bool:
        if compare == "gt":
            return value > threshold
        if compare == "lt":
            return value < threshold
        return False

    async def start(self):
        logger.info("Prometheus 감시 시작 (간격: %ds, 쿼리 수: %d)",
                    settings.OBSERVER_INTERVAL_SEC, len(self.QUERIES))
        while True:
            for q in self.QUERIES:
                value = await self._query(q["promql"])
                if value is None:
                    continue
                if self._breached(value, q["threshold"], q["compare"]):
                    symptom = q["symptom_template"].format(
                        value=value, threshold=q["threshold"]
                    )
                    logger.warning("이상 감지 [%s]: %s", q["name"], symptom)
                    await redis_client.publish("rca.input", {
                        "source": "auto",
                        "text": symptom,
                        "metric": {"name": q["name"], "value": value},
                    })
            await asyncio.sleep(settings.OBSERVER_INTERVAL_SEC)
