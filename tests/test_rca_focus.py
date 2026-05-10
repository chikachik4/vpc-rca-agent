from agents.rca import _build_focus_hints


def test_build_focus_hints_prioritizes_eks_for_cpu():
    hints = _build_focus_hints("{}", "backend cpu spike and timeout")
    assert "prioritize EKS evidence first" in hints


def test_build_focus_hints_for_redis_specific_signal():
    hints = _build_focus_hints("{}", "backend redis timeout")
    assert "Only elevate Redis as the leading hypothesis" in hints


def test_build_focus_hints_for_pod_chaos():
    hints = _build_focus_hints("{}", "pod chaos restart and OOM")
    assert "CrashLoopBackOff" in hints
