import json
import asyncio
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp import StdioServerParameters
from infrastructure.redis_client import redis_client
from core.config import settings

RCA_PROMPT_BASE = """
당신은 AWS 인프라 증거 기반 RCA 전문가입니다. 반드시 다음 규칙을 따르세요:
1. 범위: VPC1(EKS)과 VPC3(공유 허브) 리소스만 조회
2. 조사 순서: CloudWatch 알람/메트릭 → Application Signals(트레이싱) → EKS 이벤트/로그 → CloudTrail 변경 이력
3. VPC3 데이터(Prometheus/ArgoCD/OpenSearch/Tempo)가 필요하면 반드시 "__SPRINT__:{구체적 쿼리}" 형식으로 한 줄 삽입
4. Read-only 원칙: 어떤 리소스도 수정하지 않음
"""

MODE_INSTRUCTIONS = {
    "beginner": """
[Beginner 모드 지침]
- 어려운 IT 기술 용어를 사용할 때는 반드시 쉬운 설명을 덧붙이세요.
- 장애 원인을 비유를 들어 설명하면 좋습니다.
- 조치 가이드는 명령어를 그대로 복사해서 쓸 수 있을 정도로 아주 상세하게 작성하세요.
""",
    "expert": """
[Expert 모드 지침]
- 핵심 메트릭 수치, 에러 로그 원문, CloudTrail API 호출 이력을 가감 없이 보고하세요.
- 불필요한 서술은 줄이고 기술적 사실 위주로 간결하게 작성하세요.
- 아키텍처 관점에서의 근본 원인(Deep Root Cause)을 제시하세요.
""",
}

RCA_OUTPUT_FORMAT = """
[출력 포맷 (한국어)]
1. [증상 요약] ...
2. [영향 범위] ...
3. [타임라인] (지표 변화 및 CloudTrail 변경 이력 포함)
4. [가설 A] ... 신뢰도: XX%
5. [가설 B] ... 신뢰도: XX% (최소 2개 가설 필수)
6. [최종 결론] (가설 검증 결과 요약)
7. [권장 조치] (단기/장기 분리)
"""


class RCAAgent:
    def __init__(self):
        self._mcp_clients = []
        self._mcp_tools = []
        self.agent: Agent | None = None
        self._sprint_event = asyncio.Event()
        self._sprint_result: str = ""
        self._plan_subscription_task = None
        self._sprint_subscription_task = None

    async def _init_mcp(self):
        with open(settings.MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)

        for _, srv in config.get("mcpServers", {}).items():
            env = srv.get("env", {}).copy()
            for k, v in env.items():
                if v == "${EKS_CLUSTER_NAME}":
                    env[k] = settings.EKS_CLUSTER_NAME
            env.setdefault("AWS_REGION", settings.AWS_REGION)

            client = MCPClient(lambda srv=srv, env=env: StdioServerParameters(
                command=srv["command"],
                args=srv["args"],
                env=env,
            ))
            self._mcp_clients.append(client)

        for client in self._mcp_clients:
            await client.__aenter__()
            tools = await client.list_tools()
            self._mcp_tools.extend(tools)
            print(f"📦 [RCA] MCP 서버에서 {len(tools)}개 도구 로드")

        self._build_agent("beginner")

    def _build_agent(self, mode: str):
        system_prompt = (
            f"{RCA_PROMPT_BASE}\n"
            f"{MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS['beginner'])}\n"
            f"{RCA_OUTPUT_FORMAT}"
        )
        self.agent = Agent(
            model=BedrockModel(
                model_id=settings.LLM_MODEL_EXPERT,
                region_name=settings.AWS_REGION,
            ),
            tools=self._mcp_tools,
            system_prompt=system_prompt,
        )

    async def handle_plan(self, data: dict):
        mode = data.get("mode", "beginner")
        plan = data.get("plan", "")

        self._build_agent(mode)

        await redis_client.publish("rca.output", {
            "type": "status",
            "sender": "RCA",
            "text": f"🔍 증거 수집 시작 ({mode} 모드)...",
        })

        result = str(await asyncio.to_thread(self.agent, plan))

        if "__SPRINT__:" in result:
            _, rest = result.split("__SPRINT__:", 1)
            sprint_query = rest.strip().splitlines()[0]

            self._sprint_event.clear()
            self._sprint_result = ""
            await redis_client.publish("rca.sprint", {"query": sprint_query})
            await redis_client.publish("rca.output", {
                "type": "status",
                "sender": "RCA",
                "text": f"⏳ Sprint 조회 요청: {sprint_query}",
            })

            try:
                await asyncio.wait_for(self._sprint_event.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                print("⚠️ [RCA] Sprint 타임아웃")
                self._sprint_result = "조회 타임아웃 발생"

            final_prompt = (
                f"{plan}\n\n"
                f"[Sprint 조회 결과]\n{self._sprint_result}\n\n"
                "위 결과를 포함해 최종 RCA를 완성하세요."
            )
            result = str(await asyncio.to_thread(self.agent, final_prompt))

        await redis_client.publish("rca.output", {
            "type": "report",
            "sender": "RCA",
            "text": result,
        })

    async def handle_sprint_result(self, data: dict):
        self._sprint_result = data.get("result", "")
        self._sprint_event.set()

    async def start(self):
        await self._init_mcp()
        print("🧠  [RCA] rca.plan 및 rca.sprint.result 대기 중...")
        self._plan_subscription_task = await redis_client.subscribe(
            "rca.plan", self.handle_plan
        )
        self._sprint_subscription_task = await redis_client.subscribe(
            "rca.sprint.result", self.handle_sprint_result
        )
        await asyncio.Future()
