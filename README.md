# VPC RCA Agent

AI 기반 인프라 장애 원인 분석(Root Cause Analysis) 자동화 시스템입니다. Prometheus 모니터링 또는 수동 트리거를 통해 장애를 감지하고, Multi-Agent 아키텍처를 활용하여 증거 수집 및 분석 리포트를 생성합니다.

## 🚀 주요 기능

- **자동 장애 감지 (Observer):** Prometheus 메트릭을 실시간 감시하여 임계값 초과 시 분석을 자동 시작합니다.
- **지능형 분석 계획 (Architect Agent):** 장애 증상을 분석하고 사용자 수준(Beginner/Expert)에 맞춘 조사 계획을 수립합니다.
- **증거 기반 RCA (RCA Agent):** MCP(Model Context Protocol) 도구를 사용하여 인프라 상태를 조사하고 가설을 검증합니다.
- **고속 데이터 조회 (Sprint Agent):** Prometheus, OpenSearch, ArgoCD, Tempo 등 다양한 도구에서 필요한 데이터를 즉시 수집합니다.
- **결과 전파 (Dispatcher):** 분석 완료 후 Markdown 리포트를 생성하고 Slack으로 알림을 전송합니다.

## 🏗 아키텍처

시스템은 Redis Pub/Sub을 기반으로 한 이벤트 드리븐 방식으로 동작합니다.

1.  **ObserverLoop:** Prometheus 쿼리를 통해 이상 징후 감지 (`rca.input` 발행)
2.  **ArchitectAgent:** 증상 요약 및 조사 계획 수립 (`rca.plan` 발행)
3.  **RCAAgent:** 증거 수집 및 가설 검증. 필요 시 SprintAgent에게 데이터 요청
4.  **SprintAgent:** Observability 도구(Prometheus, ArgoCD 등) 호출 및 결과 반환
5.  **ReportDispatcher:** 최종 리포트 파일 저장 및 Slack 발송 (`rca.output` 구독)

## 🛠 기술 스택

- **Language:** Python 3.12+
- **Agent Framework:** `strands-agents`
- **LLM:** AWS Bedrock (Claude 3.x)
- **Communication:** Redis (Pub/Sub)
- **Observability Integration:** Prometheus, ArgoCD, OpenSearch, Tempo
- **Protocol:** MCP (Model Context Protocol)

## ⚙️ 설정 방법

1.  **환경 변수 설정:** `.env.example` 파일을 `.env`로 복사하고 필요한 값을 설정합니다.
    ```bash
    cp .env.example .env
    ```
2.  **의존성 설치:** `uv`를 사용하여 패키지를 설치합니다.
    ```bash
    uv sync
    ```
3.  **MCP 설정:** `mcp_config.json` 파일을 통해 연동할 MCP 서버를 정의합니다.

## 🏃 실행 방법

```bash
python main.py
```

**수동 트리거 예시:**
```bash
redis-cli publish rca.input '{"text": "API 응답 지연 발생", "source": "manual"}'
```

## 📂 프로젝트 구조

- `agents/`: Architect, RCA, Sprint 에이전트 구현
- `core/`: 설정(Config) 및 로깅
- `infrastructure/`: Redis 클라이언트 등 인프라 설정
- `tools/`: Observability 도구별 인터페이스
- `dispatcher.py`: 리포트 처리 및 Slack 발송
- `observer.py`: Prometheus 감시 루프
- `main.py`: 시스템 엔트리 포인트
