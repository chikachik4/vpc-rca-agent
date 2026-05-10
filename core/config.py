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

    # ObserverLoop polling interval
    OBSERVER_INTERVAL_SEC: int = 15

    # ObserverLoop thresholds
    CPU_ALERT_THRESHOLD: float = 0.5
    BACKEND_CPU_CORES_THRESHOLD: float = 0.1
    POD_RESTART_THRESHOLD: int = 3
    OOMKILL_THRESHOLD: int = 0
    MEMORY_UTILIZATION_THRESHOLD: float = 80.0
    BACKEND_READY_REPLICAS_THRESHOLD: int = 2
    BACKEND_PENDING_PODS_THRESHOLD: int = 0
    BACKEND_CRASHLOOP_THRESHOLD: int = 0
    REDIS_MISS_RATE_THRESHOLD: float = 0.1
    DB_CONN_THRESHOLD: int = 15
    RESPONSE_TIME_THRESHOLD: float = 0.1
    ERROR_RATE_THRESHOLD: float = 0.05

    # ReportDispatcher
    SLACK_WEBHOOK_URL: str = ""
    REPORT_DIR: str = "reports"

    # Logging
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
