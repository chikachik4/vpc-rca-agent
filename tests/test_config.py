from core.config import settings


def test_defaults():
    assert settings.AWS_REGION == "ap-northeast-2"
    assert settings.REDIS_PORT == 6379
    assert settings.CPU_ALERT_THRESHOLD == 0.5
    assert settings.POD_RESTART_THRESHOLD == 3
    assert settings.HEALTH_SCORE_THRESHOLD == 80.0
    assert settings.DB_CONN_THRESHOLD == 15
    assert settings.ERROR_RATE_THRESHOLD == 0.05
    assert settings.RESPONSE_TIME_THRESHOLD == 0.1
    assert settings.OBSERVER_INTERVAL_SEC == 15
    assert settings.LOG_LEVEL == "INFO"


def test_tls_defaults():
    assert settings.TLS_VERIFY is True
    assert settings.CA_BUNDLE_PATH == ""


def test_tls_helper_returns_bool_when_no_bundle():
    verify = settings.CA_BUNDLE_PATH if settings.CA_BUNDLE_PATH else settings.TLS_VERIFY
    assert isinstance(verify, bool)
    assert verify is True
