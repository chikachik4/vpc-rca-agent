import asyncio
import json
from datetime import datetime, timezone

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


def _has_insufficient_evidence_marker(text: str) -> bool:
    markers = [
        "timeout",
        "timed out",
        "access denied",
        "permission denied",
        "insufficient",
        "failed to fetch",
        "validation_failures",
        "invalid type",
    ]
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


def _build_insufficient_evidence_report(plan: str, sprint_result: str) -> str:
    return (
        "[증거 부족 RCA 상태 보고]\n"
        "1. [상태] 근거 데이터가 부족하여 확정 RCA를 생성하지 않습니다.\n"
        "2. [이유] Sprint/MCP 조회에서 타임아웃, 권한, 또는 파라미터 검증 오류가 발생했습니다.\n"
        "3. [수집된 단서]\n"
        f"- 계획 입력: {plan[:500]}\n"
        f"- Sprint 결과: {sprint_result[:500]}\n"
        "4. [필요한 추가 증거]\n"
        "- VPC1 EKS 이벤트/파드 상태\n"
        "- VPC1 EC2 Redis 인스턴스 상태 및 CloudWatch 지표\n"
        "- VPC3 OpenSearch 로그 및 ArgoCD 최근 변경 이력\n"
        "- Prometheus 핵심 지표(응답시간, DB 연결, 에러율)\n"
        "5. [다음 액션]\n"
        "- 권한/연결/파라미터 형식 문제를 해결한 뒤 같은 타임윈도우로 재수집\n"
        "- 재수집 후 가설 축소형 RCA를 재실행\n"
    )


RCA_PROMPT_BASE = """
You are a DevOps RCA agent for Bookjjeok AWS.

[Environment topology]
- VPC1 runs workload on EKS.
- Redis for VPC1 backend is an EC2 Redis instance (not ElastiCache).
- VPC3 contains RDS, OpenSearch, ArgoCD, Prometheus, and Tempo.

[Rules]
1. Stay inside VPC1/VPC3 only.
2. Read-only evidence only.
3. Treat incoming symptom as trigger, not diagnosis.
4. Build and reduce hypotheses from evidence.
5. If VPC3 data is needed, request exactly one Sprint line:
   __SPRINT__:{specific query}
6. If evidence is insufficient, do not output a confident final root cause.
7. For aws___call_aws time parameters (for example --start-time / --end-time),
   always pass Unix epoch integers in seconds, not ISO strings.
"""

MODE_INSTRUCTIONS = {
    "beginner": """
[Beginner mode]
- Use plain Korean explanations.
- Separate symptom, cause candidate, and action steps clearly.
""",
    "expert": """
[Expert mode]
- Prioritize concrete evidence and rejected hypotheses.
- Avoid generic conclusions without data.
""",
}

RCA_OUTPUT_FORMAT = """
[Output format in Korean]
1. [증상 요약]
2. [영향 범위]
3. [타임라인]
4. [증거 요약]
5. [가설 검증]
6. [가장 가능성 높은 원인]
7. [권장 조치]
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
        self._is_running = False
        self._last_started_at: datetime | None = None

    async def _init_mcp(self):
        try:
            with open(settings.MCP_CONFIG_PATH, "r", encoding="utf-8") as file:
                config = json.load(file)
        except FileNotFoundError:
            logger.error("MCP config file not found: %s - continuing without MCP", settings.MCP_CONFIG_PATH)
            self._build_agent("beginner")
            return
        except json.JSONDecodeError as exc:
            logger.error("MCP config parse failed: %s - continuing without MCP", exc)
            self._build_agent("beginner")
            return

        for srv_name, srv in config.get("mcpServers", {}).items():
            env = {
                key: _expand_mcp_value(value) if isinstance(value, str) else value
                for key, value in srv.get("env", {}).items()
            }
            env.setdefault("AWS_REGION", settings.AWS_REGION)
            args = [_expand_mcp_value(arg) if isinstance(arg, str) else arg for arg in srv["args"]]

            client = MCPClient(
                lambda srv=srv, env=env, args=args: stdio_client(
                    StdioServerParameters(command=srv["command"], args=args, env=env)
                )
            )
            try:
                tools = await client.load_tools()
                self._mcp_clients.append(client)
                self._mcp_tools.extend(tools)
                logger.info("MCP server [%s] loaded %d tools", srv_name, len(tools))
            except Exception as exc:
                logger.error("MCP server [%s] init failed, skipping: %s", srv_name, exc)
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
            model=BedrockModel(model_id=settings.LLM_MODEL_EXPERT, region_name=settings.AWS_REGION),
            tools=self._mcp_tools,
            system_prompt=system_prompt,
        )

    def _extract_sprint_query(self, result: str) -> str:
        try:
            _, rest = result.split("__SPRINT__:", 1)
            lines = rest.splitlines()
            return lines[0].strip() if lines else ""
        except Exception as exc:
            logger.warning("__SPRINT__ query parse failed: %s", exc)
            return ""

    async def handle_plan(self, data: dict):
        if self._is_running:
            await redis_client.publish(
                "rca.output",
                {
                    "type": "status",
                    "sender": "RCA",
                    "text": "[RCA] previous investigation still running, skipping this trigger",
                },
            )
            return

        self._is_running = True
        self._last_started_at = datetime.now(timezone.utc)
        try:
            raw_mode = data.get("mode", "beginner")
            mode = raw_mode if raw_mode in MODE_INSTRUCTIONS else "beginner"

            plan = data.get("plan", "").strip()
            if not plan:
                plan = json.dumps(
                    {
                        "mode": mode,
                        "symptom": data.get("original", "unknown incident"),
                        "timerange": "last 1h",
                        "vpc_scope": ["vpc1", "vpc3"],
                        "investigation_steps": ["Check CloudWatch", "Check EKS events"],
                        "priority_hypothesis": "fallback investigation due to empty plan",
                    },
                    ensure_ascii=False,
                )
                logger.warning("Empty plan received; fallback plan generated")

            self._build_agent(mode)
            await redis_client.publish(
                "rca.output",
                {"type": "status", "sender": "RCA", "text": f"[RCA] Evidence collection started ({mode})..."},
            )

            first_pass = str(await asyncio.to_thread(self.agent, plan))
            sprint_failed = False
            result = first_pass

            if "__SPRINT__:" in first_pass:
                sprint_query = self._extract_sprint_query(first_pass)
                if not sprint_query:
                    sprint_failed = True
                    self._sprint_result = "empty sprint query"
                else:
                    self._sprint_event.clear()
                    self._sprint_result = ""
                    await redis_client.publish("rca.sprint", {"query": sprint_query})
                    await redis_client.publish(
                        "rca.output",
                        {"type": "status", "sender": "RCA", "text": f"[RCA] Sprint query requested: {sprint_query}"},
                    )
                    try:
                        await asyncio.wait_for(self._sprint_event.wait(), timeout=15.0)
                        logger.info("Sprint result received")
                    except asyncio.TimeoutError:
                        logger.warning("Sprint response timeout (15s)")
                        sprint_failed = True
                        self._sprint_result = "query timeout"

                    if not sprint_failed:
                        final_prompt = (
                            f"{plan}\n\n"
                            f"[Sprint result]\n{self._sprint_result}\n\n"
                            "Use only evidence-backed reasoning. If evidence is insufficient, state that explicitly."
                        )
                        result = str(await asyncio.to_thread(self.agent, final_prompt))

            if sprint_failed or _has_insufficient_evidence_marker(self._sprint_result):
                result = _build_insufficient_evidence_report(plan, self._sprint_result)

            await redis_client.publish("rca.output", {"type": "report", "sender": "RCA", "text": result})
        finally:
            self._is_running = False

    async def handle_sprint_result(self, data: dict):
        self._sprint_result = data.get("result", "")
        self._sprint_event.set()

    async def start(self):
        await self._init_mcp()
        logger.info("[RCA] waiting on rca.plan and rca.sprint.result...")
        self._plan_subscription_task = await redis_client.subscribe("rca.plan", self.handle_plan)
        self._sprint_subscription_task = await redis_client.subscribe("rca.sprint.result", self.handle_sprint_result)
        await asyncio.Future()
