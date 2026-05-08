import asyncio
import json

from strands import Agent
from strands.models import BedrockModel

from core.config import settings
from core.logging import get_logger
from infrastructure.redis_client import redis_client

logger = get_logger(__name__)

ALLOWED_SCOPE = ["vpc1", "vpc3"]

ARCHITECT_PROMPT = """
You are a senior SRE planning assistant for Bookjjeok incident response.
Return JSON only.

Rules:
1. Scope is fixed to VPC1 and VPC3 only.
2. Redis is an EC2 instance in VPC1 (not ElastiCache).
3. VPC3 contains RDS, OpenSearch, ArgoCD, Prometheus, and Tempo.
4. Keep the plan evidence-oriented, not diagnosis-oriented.

Output JSON shape:
{
  "mode": "beginner" or "expert",
  "symptom": "short symptom summary",
  "timerange": "last 30m|last 1h|...",
  "vpc_scope": ["vpc1", "vpc3"],
  "investigation_steps": ["...", "..."],
  "priority_hypothesis": "..."
}
"""


def _normalize_plan(plan: dict, fallback_symptom: str) -> dict:
    mode = plan.get("mode", "beginner")
    if mode not in {"beginner", "expert"}:
        mode = "beginner"

    symptom = str(plan.get("symptom", "")).strip() or fallback_symptom or "unknown incident"
    timerange = str(plan.get("timerange", "")).strip() or "last 1h"
    steps = plan.get("investigation_steps", [])
    if not isinstance(steps, list) or not steps:
        steps = ["Check CloudWatch and EKS events", "Check OpenSearch and ArgoCD changes"]
    hypothesis = str(plan.get("priority_hypothesis", "")).strip() or "initial hypothesis pending evidence"

    # Force canonical scope to avoid LLM drift such as "prod-vpc".
    return {
        "mode": mode,
        "symptom": symptom,
        "timerange": timerange,
        "vpc_scope": ALLOWED_SCOPE,
        "investigation_steps": steps,
        "priority_hypothesis": hypothesis,
    }


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
        await redis_client.publish(
            "rca.output",
            {
                "type": "status",
                "sender": "Architect",
                "text": f"[Architect] Building investigation plan... (trigger: {source})",
            },
        )

        raw_plan = str(await asyncio.to_thread(self.agent, data.get("text", "")))

        try:
            clean = raw_plan.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:].strip()
            parsed = json.loads(clean)
        except Exception as exc:
            logger.error("Architect JSON parse failed: %s", exc)
            parsed = {}

        plan_json = _normalize_plan(parsed, str(data.get("text", "")))
        plan_str = json.dumps(plan_json, ensure_ascii=False)

        await redis_client.publish(
            "rca.plan",
            {
                "plan": plan_str,
                "mode": plan_json["mode"],
                "original": data.get("text", ""),
            },
        )
        await redis_client.publish(
            "rca.output",
            {
                "type": "status",
                "sender": "Architect",
                "text": f"[Architect] Plan ready ({plan_json['mode']})\n{plan_str}",
            },
        )

    async def start(self):
        logger.info("[Architect] waiting on rca.input...")
        self._subscription_task = await redis_client.subscribe("rca.input", self.handle)
        await asyncio.Future()
