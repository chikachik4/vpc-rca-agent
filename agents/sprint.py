import asyncio
from strands import Agent
from strands.models import BedrockModel
from tools.prometheus import query_prometheus
from tools.argocd import list_argocd_apps, get_argocd_app_status
from tools.opensearch import search_logs, vector_search
from tools.tempo import query_tempo_traces, get_tempo_trace
from infrastructure.redis_client import redis_client
from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

SPRINT_PROMPT = """
당신은 빠른 인프라 데이터 조회 전문가입니다.
요청받은 내용을 도구로 즉시 조회하여 사실만 간결하게 반환합니다.
추론이나 해석 없이 원본 데이터를 정리해서 제시하세요.
사용 가능 도구: Prometheus(메트릭), ArgoCD(배포 상태), OpenSearch(로그), Tempo(분산 트레이스)
"""


class SprintAgent:
    def __init__(self):
        self._subscription_task = None
        self.agent = Agent(
            model=BedrockModel(
                model_id=settings.LLM_MODEL_ROUTING,
                region_name=settings.AWS_REGION,
            ),
            tools=[
                query_prometheus,
                list_argocd_apps,
                get_argocd_app_status,
                search_logs,
                vector_search,
                query_tempo_traces,
                get_tempo_trace,
            ],
            system_prompt=SPRINT_PROMPT,
        )

    async def handle(self, data: dict):
        query = data.get("query", "")
        logger.info("[Sprint] 조회 시작: %s", query)
        await redis_client.publish("rca.output", {
            "type": "status",
            "sender": "Sprint",
            "text": f"[Sprint] 조회 중: {query}",
        })

        result = str(await asyncio.to_thread(self.agent, query))

        await redis_client.publish("rca.sprint.result", {"result": result})
        await redis_client.publish("rca.output", {
            "type": "status",
            "sender": "Sprint",
            "text": result,
        })

    async def start(self):
        logger.info("[Sprint] rca.sprint 대기 중...")
        self._subscription_task = await redis_client.subscribe("rca.sprint", self.handle)
        await asyncio.Future()
