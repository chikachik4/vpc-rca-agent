from core.config import Settings, settings


def test_defaults():
    assert settings.AWS_REGION == "ap-northeast-2"
    assert settings.REDIS_PORT == 6379
    assert settings.CPU_ALERT_THRESHOLD == 0.5
    assert settings.POD_RESTART_THRESHOLD == 3
    assert settings.DB_CONN_THRESHOLD == 15
    assert settings.ERROR_RATE_THRESHOLD == 0.05
    assert settings.RESPONSE_TIME_THRESHOLD == 0.1
    assert settings.OBSERVER_INTERVAL_SEC == 15
    assert settings.LOG_LEVEL == "INFO"


def test_tls_defaults():
    # Use a fresh instance without .env so production overrides don't leak in.
    s = Settings(_env_file=None)
    assert s.TLS_VERIFY is True
    assert s.CA_BUNDLE_PATH == ""


def test_tls_helper_returns_bool_when_no_bundle():
    s = Settings(_env_file=None)
    verify = s.CA_BUNDLE_PATH if s.CA_BUNDLE_PATH else s.TLS_VERIFY
    assert isinstance(verify, bool)
    assert verify is True
