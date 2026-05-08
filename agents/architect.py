import asyncio
import json

from strands import Agent
from strands.models import BedrockModel

from core.config import settings
from core.logging import get_logger
from infrastructure.redis_client import redis_client

logger = get_logger(__name__)

ARCHITECT_PROMPT = """
당신은 인프라 장애 조사 계획을 수립하는 시니어 SRE입니다.
사용자의 자연어 장애 보고를 받아 분석하고, 사용자의 의도나 말투를 보고 'beginner' 또는 'expert' 모드를 판별하세요.
- beginner: 자동화된 전체 조사 선호, 친절하고 쉬운 용어 설명 필요.
- expert: 특정 시간대/리소스 지정 선호, 기술적인 상세 메트릭 및 가설 검증 중심.

반드시 다음 JSON 형식으로만 출력하세요:
{
  "mode": "beginner" 또는 "expert",
  "symptom": "증상 한 줄 요약",
  "timerange": "조사 시간 범위 (예: last 30m)",
  "vpc_scope": ["vpc1", "vpc3"],
  "investigation_steps": ["CloudWatch 알람 확인", "EKS pod 이벤트 확인", ...],
  "priority_hypothesis": "최초 유력 가설"
}
다른 텍스트 없이 JSON만 출력하세요.
"""


class ArchitectAgent:
    def __init__(self):
        self._subscription_task = None
        self.agent = Agent(
            model=BedrockModel(
                model_id=settings.LLM_MODEL_EXPERT,
                region_name=settings.AWS_REGION,
            ),
            system_prompt=ARCHITECT_PROMPT,
        )

    async def handle(self, data: dict):
        source = data.get("source", "manual")
        await redis_client.publish("rca.output", {
            "type": "status",
            "sender": "Architect",
            "text": f"[Architect] 조사 계획 수립 중... (트리거: {source})",
        })

        raw_plan = str(await asyncio.to_thread(self.agent, data.get("text", "")))

        # LLM이 간혹 ```json ... ``` 래퍼를 포함할 수 있으므로 정규화
        try:
            clean = raw_plan.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:].strip()

            plan_json = json.loads(clean)
            plan_json.setdefault("mode", "beginner")
            plan_str = json.dumps(plan_json, ensure_ascii=False)
        except Exception as e:
            logger.error("Architect JSON 파싱 실패: %s", e)
            plan_json = {
                "mode": "beginner",
                "symptom": data.get("text", "알 수 없는 장애"),
                "timerange": "last 1h",
                "vpc_scope": ["vpc1", "vpc3"],
                "investigation_steps": ["CloudWatch 확인"],
                "priority_hypothesis": "분석 실패로 인한 기본 조사",
            }
            plan_str = json.dumps(plan_json, ensure_ascii=False)

        await redis_client.publish("rca.plan", {
            "plan": plan_str,
            "mode": plan_json["mode"],
            "original": data.get("text", ""),
        })
        await redis_client.publish("rca.output", {
            "type": "status",
            "sender": "Architect",
            "text": f"[Architect] 조사 계획 완료 ({plan_json['mode']} 모드)\n{plan_str}",
        })

    async def start(self):
        logger.info("[Architect] rca.input 대기 중...")
        self._subscription_task = await redis_client.subscribe("rca.input", self.handle)
        await asyncio.Future()
