# VPC RCA Agent

AWS VPC/EKS 환경의 장애 징후를 감지하고, 여러 Agent가 증거를 수집해 RCA(Root Cause Analysis) 리포트를 생성하는 자동화 도구입니다. Redis Pub/Sub을 중심으로 Observer, Architect, RCA, Sprint, Dispatcher 컴포넌트가 이벤트 기반으로 동작합니다.

## 주요 기능

- **ObserverLoop**: Prometheus 메트릭을 주기적으로 조회해 임계값 초과 시 `rca.input` 이벤트를 발행합니다.
- **ArchitectAgent**: 장애 증상을 분석해 사용자 수준(`beginner` 또는 `expert`)에 맞는 조사 계획을 만듭니다.
- **RCAAgent**: Bedrock Claude 모델과 MCP 도구를 사용해 CloudWatch, EKS, CloudTrail 등에서 증거를 수집합니다.
- **SprintAgent**: Prometheus, ArgoCD, OpenSearch, Tempo 같은 관측 도구에서 빠른 조회 결과를 제공합니다.
- **ReportDispatcher**: 최종 분석 결과를 Markdown 리포트로 저장하고, 설정된 경우 Slack으로 전송합니다.

## 아키텍처

```text
Prometheus
    |
    v
ObserverLoop --rca.input--> ArchitectAgent --rca.plan--> RCAAgent
                                                        |
                                                        | rca.sprint
                                                        v
                                                   SprintAgent
                                                        |
                                                        v
RCAAgent --rca.output--> ReportDispatcher --> reports/*.md / Slack
```

주요 Redis 채널:

- `rca.input`: 장애 증상 입력
- `rca.plan`: Architect가 만든 조사 계획
- `rca.sprint`: 빠른 관측 데이터 조회 요청
- `rca.sprint.result`: Sprint 조회 결과
- `rca.output`: 상태 메시지와 최종 리포트

## 요구 사항

- Python 3.12 이상
- `uv`
- Redis
- AWS IAM 권한 또는 인스턴스 프로파일
- AWS Bedrock 모델 접근 권한
- Prometheus, ArgoCD, OpenSearch, Tempo 등 관측 도구 접근 경로

## 설치

```bash
uv sync
```

개발 도구까지 포함해 설치하려면:

```bash
uv sync --group dev
```

`uv.lock`은 재현 가능한 설치를 위해 반드시 Git에 포함합니다.

## 설정

`.env.example`을 복사해 `.env`를 만들고 환경에 맞게 값을 채웁니다.

```bash
cp .env.example .env
```

주요 설정:

- `AWS_REGION`: AWS 리전
- `EKS_CLUSTER_NAME`: 조회 대상 EKS 클러스터 이름
- `REDIS_HOST`, `REDIS_PORT`: Redis 연결 정보
- `PROMETHEUS_URL`, `ARGOCD_URL`, `OPENSEARCH_URL`, `TEMPO_URL`: 관측 도구 엔드포인트
- `ARGOCD_TOKEN`: ArgoCD API 토큰
- `TLS_VERIFY`, `CA_BUNDLE_PATH`: TLS 검증 설정
- `MCP_CONFIG_PATH`: MCP 서버 설정 파일 경로
- `SLACK_WEBHOOK_URL`: Slack 전송이 필요할 때만 설정
- `REPORT_DIR`: 리포트 저장 디렉터리

`.env`는 민감정보를 포함할 수 있으므로 Git에 올리지 않습니다.

RCA 리포트 Slack 알림은 Alertmanager의 `slack_api_url`과 별개로 앱의
`SLACK_WEBHOOK_URL` 설정을 사용합니다. 같은 채널로 보내려면 Alertmanager webhook URL을
`.env`의 `SLACK_WEBHOOK_URL`에도 설정하세요.

## MCP 설정

`mcp_config.json`에서 사용할 MCP 서버를 정의합니다.

현재 기본 설정:

- `awslabs.cloudwatch-mcp-server`
- `awslabs.cloudwatch-application-signals-mcp-server`
- `awslabs.eks-mcp-server`
- `awslabs.cloudtrail-mcp-server`

서버에서 MCP 초기화가 실패하면 앱은 MCP 도구 없이 계속 실행되지만, RCA의 AWS 증거 수집 능력이 제한됩니다. 특히 `uvx`로 실행되는 MCP 패키지가 registry에 존재하는지와 IAM 권한, `EKS_CLUSTER_NAME`, `AWS_REGION` 값을 먼저 확인하세요.

## 실행

```bash
uv run python main.py
```

이미 `.venv`가 준비된 서버에서는 다음처럼 실행할 수 있습니다.

```bash
.venv/bin/python main.py
```

수동 트리거 예시:

```bash
redis-cli publish rca.input '{"text": "API 응답 지연 발생", "source": "manual", "mode": "beginner"}'
```

## 테스트와 린트

```bash
uv run ruff check .
uv run pytest -q
```

서버의 `.venv`를 직접 사용할 경우:

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest -q
```

테스트는 로컬 `.env` 값의 영향을 받을 수 있습니다. `TLS_VERIFY=false` 같은 운영 설정 때문에 기본값 테스트가 실패하지 않도록 테스트 환경에서는 필요한 변수를 격리하세요.

## 운영 참고

- 리포트 산출물은 `reports/`에 저장됩니다.
- `reports/`는 런타임 산출물이므로 Git에 올리지 않습니다.
- `.agents-dev/log/`, `.claude/settings.local.json`, `.env`, `.venv/`, `__pycache__/`도 로컬 전용입니다.
- 서버에서 GitHub HTTPS push가 실패하면 로컬 인증 환경에서 push하거나, 서버 원격을 SSH 인증 방식으로 설정하세요.

## 프로젝트 구조

```text
agents/
  architect.py      # 조사 계획 생성
  rca.py            # MCP/Bedrock 기반 RCA 수행
  sprint.py         # 관측 도구 빠른 조회
core/
  config.py         # pydantic-settings 기반 설정
  logging.py        # 로깅 설정
infrastructure/
  redis_client.py   # Redis Pub/Sub 클라이언트
tools/
  argocd.py         # ArgoCD API 조회
  opensearch.py     # OpenSearch 조회
  prometheus.py     # Prometheus 조회
  tempo.py          # Tempo 조회
dispatcher.py       # 리포트 저장 및 Slack 발송
observer.py         # Prometheus 기반 장애 감시
main.py             # 엔트리 포인트
mcp_config.json     # MCP 서버 설정
pyproject.toml      # 의존성/테스트/린트 설정
uv.lock             # 고정된 의존성 lockfile
```
