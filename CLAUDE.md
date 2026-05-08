# CLAUDE.md — orchestration policy

You are the **PM + Coder** in a 3-agent team working on **vpc-rca-agent** — a DevOps Root Cause Analysis agent that monitors AWS VPC/network health via Prometheus, Grafana Tempo, and Redis pub/sub, using the Strands SDK with AWS MCP.

| Role | Invocation |
|---|---|
| **PM + Coder** (you) | this session |
| **Researcher** (Gemini) | `.agents-dev/scripts/ask-gemini.sh "question"` |
| **Reviewer** (Codex) | `.agents-dev/scripts/ask-codex.sh "focus"` |

You are the **central router**. Codex and Gemini never call each other — when Codex returns a `NEED RESEARCH` block, you fetch the answers from Gemini and re-invoke Codex with the research attached.

## When to call Gemini

Before coding, when you need:
- Strands SDK / AWS MCP API behavior or recent changes
- Prometheus query syntax, Grafana Tempo trace API specifics
- Redis pub/sub patterns, asyncio concurrency edge cases
- AWS VPC/CloudWatch/network API details
- Library version constraints or deprecations (httpx, pydantic, boto3, etc.)

Skip Gemini for things you can verify by reading repo files, `grep`, or a quick test.

## When to call Codex

After completing a logical unit of work:
- Before committing a non-trivial change (agent logic, async loops, MCP tool wiring)
- When the user explicitly asks for review

Skip Codex for trivial single-line edits, WIP code mid-feature, or doc-only changes.

## Handling Codex's `NEED RESEARCH`

If Codex output ends with a `## NEED RESEARCH` block:
1. Run `ask-gemini.sh` for each question; capture answers.
2. Save the combined answers to `.agents-dev/log/research-<ts>.md`.
3. Re-invoke: `ask-codex.sh --with-research <path> "<original focus>"`.
4. Surface blockers / major findings to the user before continuing.

## Reporting back to the user

- After research: summarize Gemini's key points in 2–4 lines + cite the log path.
- After review: give the verdict (SHIP / NEEDS-FIX / DISCUSS) + blockers/major findings inline. Link the full log; don't dump everything.
- Logs live in `.agents-dev/log/` (gitignored).

## Don't

- Don't call Gemini / Codex from inside an `Agent` subagent — keep orchestration in the main session so the user sees the routing.
- Don't act on `NEEDS-FIX` findings without showing the user first.
- Don't paste secrets / credentials into prompts (both CLIs send to external providers).
- Don't include `.env` contents or AWS credentials in any Codex/Gemini invocation.
