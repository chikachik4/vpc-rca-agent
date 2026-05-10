from agents.rca import _build_focus_hints


def test_build_focus_hints_for_redis_warn_error():
    hints = _build_focus_hints("{}", "backend WARN/ERROR logs and redis timeout")
    assert "Redis EC2 instance" in hints


def test_build_focus_hints_for_pod_chaos():
    hints = _build_focus_hints("{}", "pod chaos restart and OOM")
    assert "CrashLoopBackOff" in hints
