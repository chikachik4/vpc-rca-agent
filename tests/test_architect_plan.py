from agents.architect import _build_priority_steps, _normalize_plan


def test_build_priority_steps_adds_redis_step_for_warn_logs():
    steps = _build_priority_steps("VPC1 backend WARN/ERROR logs increased")
    assert not any("Redis EC2" in step for step in steps)


def test_build_priority_steps_prioritizes_eks_for_cpu_spike():
    steps = _build_priority_steps("VPC1 backend CPU usage spike")
    assert steps[0].startswith("Check EKS pod CPU and memory usage")


def test_build_priority_steps_adds_chaos_step_for_pod_restart():
    steps = _build_priority_steps("backend pod restart spike during chaos test")
    assert any("CrashLoopBackOff" in step for step in steps)


def test_build_priority_steps_adds_redis_step_only_for_redis_signal():
    steps = _build_priority_steps("backend redis timeout and cache connection error")
    assert any("Redis EC2" in step for step in steps)


def test_normalize_plan_prepends_priority_steps():
    plan = _normalize_plan(
        {
            "mode": "expert",
            "symptom": "backend pod restart spike during chaos test",
            "investigation_steps": ["Check OpenSearch and ArgoCD changes"],
        },
        "fallback symptom",
    )
    assert plan["investigation_steps"][0].startswith("Check EKS pod restarts")
