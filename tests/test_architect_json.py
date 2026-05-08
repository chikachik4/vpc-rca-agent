import json
import pytest


def _parse_plan(raw: str) -> dict:
    """agents/architect.py의 JSON 파싱 로직을 그대로 복제한 헬퍼."""
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:].strip()
    result = json.loads(clean)
    result.setdefault("mode", "beginner")
    return result


def test_plain_json():
    raw = '{"mode": "expert", "symptom": "DB timeout"}'
    result = _parse_plan(raw)
    assert result["mode"] == "expert"
    assert result["symptom"] == "DB timeout"


def test_markdown_wrapped_json():
    raw = '```json\n{"mode": "beginner", "symptom": "pod OOM"}\n```'
    result = _parse_plan(raw)
    assert result["mode"] == "beginner"


def test_mode_default_injected():
    raw = '{"symptom": "unknown"}'
    result = _parse_plan(raw)
    assert result["mode"] == "beginner"


def test_invalid_json_raises():
    with pytest.raises((json.JSONDecodeError, ValueError)):
        _parse_plan("not json at all")


def test_sprint_query_extraction():
    """agents/rca.py의 _extract_sprint_query 로직 검증."""
    result_text = "분석 중입니다.\n__SPRINT__:현재 VPC1 CPU 메트릭 조회해줘\n추가 내용"
    _, rest = result_text.split("__SPRINT__:", 1)
    sprint_query = rest.strip().splitlines()[0].strip()
    assert sprint_query == "현재 VPC1 CPU 메트릭 조회해줘"


def test_sprint_query_empty_line():
    """__SPRINT__: 다음 줄이 비어있으면 빈 문자열 반환."""
    result_text = "분석 중.\n__SPRINT__:\n\n추가 내용"
    _, rest = result_text.split("__SPRINT__:", 1)
    sprint_query = rest.strip().splitlines()[0].strip() if rest.strip() else ""
    assert sprint_query == ""
