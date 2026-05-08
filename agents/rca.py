import asyncio
import json

from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

from core.config import settings
from core.logging import get_logger
from infrastructure.redis_client import redis_client

logger = get_logger(__name__)


def _expand_mcp_value(value: str) -> str:
    replacements = {
        "${AWS_REGION}": settings.AWS_REGION,
        "${EKS_CLUSTER_NAME}": settings.EKS_CLUSTER_NAME,
    }
    for placeholder, replacement in replacements.items():
        value = value.replace(placeholder, replacement)
    return value


RCA_PROMPT_BASE = """
You are a DevOps RCA agent for the Bookjjeok AWS environment. Your job is not
to confirm a pre-written rule. Your job is to reduce the root-cause search
space by forming hypotheses, collecting evidence, rejecting weak hypotheses,
and reporting the most likely cause with supporting facts.

[Environment topology]
- VPC1 runs the application workload on EKS.
- The Redis used by the VPC1 backend is an EC2 Redis instance, not ElastiCache.
- VPC3 is the shared observability and platform hub.
- VPC3 contains RDS, OpenSearch, ArgoCD, Prometheus, and Tempo.
- Prometheus and Tempo show application symptoms and request paths.
- OpenSearch shows application and platform logs.
- ArgoCD shows recent deployment/config changes.
- AWS MCP tools show AWS-side evidence such as EKS state, EC2 instance state,
  CloudWatch metrics/logs, and CloudTrail changes.
- Use AWS MCP Server as the single AWS API/documentation access point. Keep the
  AWS tool surface small; do not ask for unused service-specific MCP servers.

[Investigation rules]
1. Stay within VPC1 and VPC3 resources.
2. Use read-only evidence only. Never modify AWS, Kubernetes, ArgoCD, Redis, or DB resources.
3. Treat Observer input as a symptom, not as a diagnosis.
4. Do not assume Redis is the root cause just because Redis-related symptoms exist.
5. For EC2 Redis incidents, explicitly check AWS/EC2 evidence, application logs,
   request latency, DB pressure, and recent deployment/config changes.
6. Prefer a small set of strong hypotheses over many generic possibilities.
7. If VPC3 Prometheus, Tempo, OpenSearch, or ArgoCD data is needed, request it
   with a single line in this exact format:
   __SPRINT__:{specific query or evidence request}

[Default hypothesis set]
- Recent deployment/configuration change in ArgoCD.
- VPC1 EKS pod/node instability.
- VPC1 EC2 Redis instance stopped, unhealthy, unreachable, or overloaded.
- VPC3 RDS pressure caused by cache fallback or application behavior.
- Network/security path issue between VPC1 backend and VPC3/shared services.
- Application-level regression visible in logs or traces.
"""


MODE_INSTRUCTIONS = {
    "beginner": """
[Beginner mode]
- Explain technical terms in simple language.
- Clearly separate symptom, likely cause, and recommended action.
- Make the action guide concrete enough to follow.
""",
    "expert": """
[Expert mode]
- Report concrete metric values, log evidence, trace evidence, and change events.
- Keep narrative short and focus on evidence quality.
- State which hypotheses were rejected and why.
""",
}

RCA_OUTPUT_FORMAT = """
[Output format in Korean]
1. [증상 요약]
2. [영향 범위]
3. [타임라인]
4. [증거 요약] Prometheus/Tempo/OpenSearch/ArgoCD/AWS 증거를 구분
5. [가설 검증] 남긴 가설과 버린 가설을 함께 설명
6. [가장 가능성 높은 원인] 신뢰도와 근거
7. [권장 조치] 단기 복구와 재발 방지 분리
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
        try:
            with open(settings.MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except FileNotFoundError:
            logger.error("MCP 설정 파일을 찾을 수 없습니다: %s — MCP 없이 계속합니다",
                         settings.MCP_CONFIG_PATH)
            self._build_agent("beginner")
            return
        except json.JSONDecodeError as e:
            logger.error("MCP 설정 파일 파싱 실패: %s — MCP 없이 계속합니다", e)
            self._build_agent("beginner")
            return

        for srv_name, srv in config.get("mcpServers", {}).items():
            env = {
                key: _expand_mcp_value(value) if isinstance(value, str) else value
                for key, value in srv.get("env", {}).items()
            }
            env.setdefault("AWS_REGION", settings.AWS_REGION)
            args = [
                _expand_mcp_value(arg) if isinstance(arg, str) else arg
                for arg in srv["args"]
            ]

            client = MCPClient(lambda srv=srv, env=env, args=args: stdio_client(StdioServerParameters(
                command=srv["command"],
                args=args,
                env=env,
            )))
            try:
                # load_tools() calls start() internally; do NOT call start() manually
                # (double-calling start() raises "the client session is currently running")
                tools = await client.load_tools()
                self._mcp_clients.append(client)
                self._mcp_tools.extend(tools)
                logger.info("MCP 서버 [%s] — %d개 도구 로드", srv_name, len(tools))
            except Exception as e:
                logger.error("MCP 서버 [%s] 초기화 실패, 건너뜀: %s", srv_name, e)
                try:
                    client.stop(None, None, None)
                except Exception:
                    pass

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

    def _extract_sprint_query(self, result: str) -> str:
        """__SPRINT__: 마커 바로 다음 줄의 쿼리를 추출합니다. 빈 줄이면 빈 문자열 반환."""
        try:
            _, rest = result.split("__SPRINT__:", 1)
            # rest.strip() 금지: 뒤따르는 빈 줄을 제거하면 "추가 내용"이 첫 줄로 올라옴
            lines = rest.splitlines()
            return lines[0].strip() if lines else ""
        except Exception as e:
            logger.warning("__SPRINT__ 쿼리 추출 실패: %s", e)
            return ""

    async def handle_plan(self, data: dict):
        raw_mode = data.get("mode", "beginner")
        mode = raw_mode if raw_mode in MODE_INSTRUCTIONS else "beginner"

        plan = data.get("plan", "").strip()
        if not plan:
            plan = json.dumps({
                "mode": mode,
                "symptom": data.get("original", "알 수 없는 장애"),
                "timerange": "last 1h",
                "vpc_scope": ["vpc1", "vpc3"],
                "investigation_steps": ["CloudWatch 확인", "EKS 이벤트 확인"],
                "priority_hypothesis": "빈 계획 수신 — 기본 조사 수행",
            }, ensure_ascii=False)
            logger.warning("빈 plan 수신, fallback plan 사용")

        self._build_agent(mode)

        await redis_client.publish("rca.output", {
            "type": "status",
            "sender": "RCA",
            "text": f"[RCA] 증거 수집 시작 ({mode} 모드)...",
        })

        result = str(await asyncio.to_thread(self.agent, plan))

        if "__SPRINT__:" in result:
            sprint_query = self._extract_sprint_query(result)

            if not sprint_query:
                logger.warning("__SPRINT__ 쿼리가 비어있어 Sprint 호출 건너뜀")
            else:
                self._sprint_event.clear()
                self._sprint_result = ""
                await redis_client.publish("rca.sprint", {"query": sprint_query})
                await redis_client.publish("rca.output", {
                    "type": "status",
                    "sender": "RCA",
                    "text": f"[RCA] Sprint 조회 요청: {sprint_query}",
                })

                try:
                    await asyncio.wait_for(self._sprint_event.wait(), timeout=15.0)
                    logger.info("Sprint 결과 수신 완료")
                except asyncio.TimeoutError:
                    logger.warning("Sprint 응답 타임아웃 (15s)")
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
        logger.info("[RCA] rca.plan 및 rca.sprint.result 대기 중...")
        self._plan_subscription_task = await redis_client.subscribe(
            "rca.plan", self.handle_plan
        )
        self._sprint_subscription_task = await redis_client.subscribe(
            "rca.sprint.result", self.handle_sprint_result
        )
        await asyncio.Future()
