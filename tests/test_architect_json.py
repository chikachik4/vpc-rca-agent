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


def _extract_sprint_query(result: str) -> str:
    """agents/rca.py의 _extract_sprint_query 로직 복제."""
    try:
        _, rest = result.split("__SPRINT__:", 1)
        lines = rest.splitlines()
        return lines[0].strip() if lines else ""
    except Exception:
        return ""


def test_sprint_query_extraction():
    """__SPRINT__: 다음 줄에 쿼리가 있으면 추출."""
    result_text = "분석 중입니다.\n__SPRINT__:현재 VPC1 CPU 메트릭 조회해줘\n추가 내용"
    assert _extract_sprint_query(result_text) == "현재 VPC1 CPU 메트릭 조회해줘"


def test_sprint_query_empty_line():
    """__SPRINT__: 다음 줄이 비어있으면 빈 문자열 반환."""
    result_text = "분석 중.\n__SPRINT__:\n\n추가 내용"
    assert _extract_sprint_query(result_text) == ""
