import asyncio
from strands import Agent
from strands.models import BedrockModel
from infrastructure.redis_client import redis_client
from core.config import settings

ARCHITECT_PROMPT = """
당신은 인프라 장애 조사 계획을 수립하는 시니어 SRE입니다.
사용자의 자연어 장애 보고를 받아 반드시 다음 JSON 형식으로만 출력하세요:
{
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
        await redis_client.publish("rca.output",
            {"sender": "Architect", "text": "📐 조사 계획 수립 중..."})

        plan = str(await asyncio.to_thread(self.agent, data.get("text", "")))

        await redis_client.publish("rca.plan",
            {"plan": plan, "original": data.get("text", "")})
        await redis_client.publish("rca.output",
            {"sender": "Architect", "text": f"✅ 조사 계획\n{plan}"})

    async def start(self):
        print("🏗️  [Architect] rca.input 대기 중...")
        self._subscription_task = await redis_client.subscribe("rca.input", self.handle)
        await asyncio.Future()
