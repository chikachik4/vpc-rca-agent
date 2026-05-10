import asyncio
import math
import time

import httpx

from core.config import settings
from core.logging import get_logger
from infrastructure.redis_client import redis_client

logger = get_logger(__name__)


def _tls():
    return settings.CA_BUNDLE_PATH if settings.CA_BUNDLE_PATH else settings.TLS_VERIFY


class ObserverLoop:
    """Poll broad service health signals and let RCAAgent narrow the root cause."""
    COOLDOWN_SECONDS = 300

    def __init__(self):
        self._last_triggered_at: dict[str, float] = {}

    @property
    def QUERIES(self):
        s = settings
        return [
            {
                "name": "high_cpu",
                "promql": 'sum(rate(container_cpu_usage_seconds_total{id="/",cluster="vpc1"}[2m]))',
                "threshold": s.CPU_ALERT_THRESHOLD,
                "compare": "gt",
                "symptom_template": "VPC1 CPU usage spike: {value:.2f} cores (threshold {threshold})",
            },
            {
                "name": "pod_restart",
                "promql": 'sum(increase(kube_pod_container_status_restarts_total{cluster="vpc1"}[5m]))',
                "threshold": s.POD_RESTART_THRESHOLD,
                "compare": "gt",
                "symptom_template": "VPC1 pod restarts increased: {value:.0f}/5m (threshold {threshold})",
            },
            {
                "name": "backend_oomkill",
                "promql": (
                    'sum(increase(kube_pod_container_status_last_terminated_reason{'
                    'cluster="vpc1",namespace="bookjjeok",reason="OOMKilled"}[5m]))'
                ),
                "threshold": s.OOMKILL_THRESHOLD,
                "compare": "gt",
                "symptom_template": "VPC1 backend OOMKill detected: {value:.0f}/5m",
            },
            {
                "name": "backend_memory_utilization",
                "promql": (
                    "100 * "
                    'sum(container_memory_working_set_bytes{cluster="vpc1",namespace="bookjjeok",pod=~"backend-.*",container!="",image!=""}) '
                    "/ clamp_min("
                    'sum(kube_pod_container_resource_limits{cluster="vpc1",namespace="bookjjeok",pod=~"backend-.*",resource="memory",unit="byte"}), '
                    "1)"
                ),
                "threshold": s.MEMORY_UTILIZATION_THRESHOLD,
                "compare": "gt",
                "symptom_template": "VPC1 backend memory pressure increased: {value:.1f}% (threshold {threshold}%)",
            },
            {
                "name": "backend_ready_replicas",
                "promql": (
                    'sum(kube_pod_status_ready{cluster="vpc1",namespace="bookjjeok",pod=~"backend-.*",condition="true"} == 1)'
                ),
                "threshold": s.BACKEND_READY_REPLICAS_THRESHOLD,
                "compare": "gt",
                "symptom_template": "VPC1 backend ready pod count increased: {value:.0f} (threshold {threshold})",
            },
            {
                "name": "backend_warn_error_logs",
                "promql": (
                    'sum(rate(logback_events_total{job="vpc1-backend",'
                    'level=~"warn|WARN|error|ERROR"}[2m]))'
                ),
                "threshold": 0.05,
                "compare": "gt",
                "symptom_template": "VPC1 backend WARN/ERROR logs increased: {value:.3f} events/s",
            },
            {
                "name": "db_connections",
                "promql": 'avg(hikaricp_connections_active{job="vpc1-backend"})',
                "threshold": s.DB_CONN_THRESHOLD,
                "compare": "gt",
                "symptom_template": "VPC3 RDS connection pressure from VPC1 backend: {value:.0f} active (threshold {threshold})",
            },
            {
                "name": "response_time",
                "promql": (
                    'sum(rate(http_server_requests_seconds_sum{job="vpc1-backend"}[2m]))'
                    ' / clamp_min(sum(rate(http_server_requests_seconds_count{job="vpc1-backend"}[2m])), 0.001)'
                ),
                "threshold": s.RESPONSE_TIME_THRESHOLD,
                "compare": "gt",
                "symptom_template": "VPC1 backend response latency increased: {value:.3f}s (threshold {threshold}s)",
            },
            {
                "name": "envoy_error_rate",
                "promql": "job:envoy_error_rate:rate5m",
                "threshold": s.ERROR_RATE_THRESHOLD,
                "compare": "gt",
                "symptom_template": "Ingress/service mesh error rate spike: {value:.1%} (threshold {threshold:.0%})",
            },
        ]

    async def _query(self, promql: str) -> float | None:
        """Return 0.0 for empty/non-finite data and None when Prometheus itself fails."""
        try:
            async with httpx.AsyncClient(verify=_tls()) as client:
                response = await client.get(
                    f"{settings.PROMETHEUS_URL}/api/v1/query",
                    params={"query": promql},
                    timeout=settings.REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                data = response.json()
                result = data["data"]["result"]
                if not result:
                    return 0.0

                value = float(result[0]["value"][1])
                if math.isnan(value) or math.isinf(value):
                    logger.warning("Prometheus query returned non-finite value (%s): %s", promql[:80], value)
                    return 0.0
                return value
        except KeyError as exc:
            logger.warning("Prometheus response parse failed (%s): %s", promql[:80], exc)
            return None
        except httpx.HTTPStatusError as exc:
            logger.error("Prometheus HTTP error (%s): %s", promql[:80], exc)
            return None
        except Exception as exc:
            logger.error("Prometheus query failed (%s): %s", promql[:80], exc)
            return None

    def _breached(self, value: float, threshold: float, compare: str) -> bool:
        if compare == "gt":
            return value > threshold
        if compare == "lt":
            return value < threshold
        return False

    def _is_in_cooldown(self, signal_name: str) -> bool:
        last_ts = self._last_triggered_at.get(signal_name)
        if last_ts is None:
            return False
        return (time.monotonic() - last_ts) < self.COOLDOWN_SECONDS

    async def start(self):
        logger.info(
            "Prometheus observer started (interval=%ds, queries=%d)",
            settings.OBSERVER_INTERVAL_SEC,
            len(self.QUERIES),
        )
        while True:
            for query in self.QUERIES:
                value = await self._query(query["promql"])
                if value is None:
                    continue

                breached = self._breached(value, query["threshold"], query["compare"])
                logger.info(
                    "Observer query [%s]: value=%s threshold=%s compare=%s breached=%s",
                    query["name"],
                    value,
                    query["threshold"],
                    query["compare"],
                    breached,
                )

                if breached:
                    if self._is_in_cooldown(query["name"]):
                        logger.info(
                            "Observer cooldown active [%s], skipping duplicate trigger",
                            query["name"],
                        )
                        continue

                    symptom = query["symptom_template"].format(
                        value=value,
                        threshold=query["threshold"],
                    )
                    logger.warning("Signal breached [%s]: %s", query["name"], symptom)
                    self._last_triggered_at[query["name"]] = time.monotonic()
                    await redis_client.publish(
                        "rca.input",
                        {
                            "source": "auto",
                            "text": symptom,
                            "metric": {"name": query["name"], "value": value},
                        },
                    )

            await asyncio.sleep(settings.OBSERVER_INTERVAL_SEC)
