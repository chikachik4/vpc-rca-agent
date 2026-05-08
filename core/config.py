from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    AWS_REGION: str = "ap-northeast-2"
    EKS_CLUSTER_NAME: str = "bookjjeok-test-eks-cluster"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    PROMETHEUS_URL: str = "http://localhost:9090"
    ARGOCD_URL: str = "https://localhost:443"
    ARGOCD_TOKEN: str = ""
    OPENSEARCH_URL: str = "https://localhost:9200"
    TEMPO_URL: str = "http://localhost:3200"

    TLS_VERIFY: bool = True
    CA_BUNDLE_PATH: str = ""
    REQUEST_TIMEOUT_SECONDS: float = 10.0

    LLM_MODEL_EXPERT: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    LLM_MODEL_ROUTING: str = "anthropic.claude-3-haiku-20240307-v1:0"

    MCP_CONFIG_PATH: str = "mcp_config.json"

    # ObserverLoop
    OBSERVER_INTERVAL_SEC: int = 15
    CPU_ALERT_THRESHOLD: float = 0.5   # cores

    # ReportDispatcher
    SLACK_WEBHOOK_URL: str = ""        # 비어있으면 Slack 발송 스킵
    REPORT_DIR: str = "reports"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
