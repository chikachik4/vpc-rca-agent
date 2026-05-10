from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from observer import ObserverLoop


@pytest.fixture
def loop():
    return ObserverLoop()


def test_queries_count(loop):
    assert len(loop.QUERIES) == 12


def test_query_names(loop):
    names = {query["name"] for query in loop.QUERIES}
    assert "high_cpu" in names
    assert "backend_cpu_cores" in names
    assert "pod_restart" in names
    assert "backend_oomkill" in names
    assert "backend_memory_utilization" in names
    assert "backend_ready_replicas" in names
    assert "backend_pending_pods" in names
    assert "backend_crashloop_waiting" in names
    assert "health_score_low" not in names
    assert "backend_warn_error_logs" in names
    assert "redis_miss_rate" not in names
    assert "db_connections" in names
    assert "response_time" in names
    assert "envoy_error_rate" in names


def test_query_has_required_keys(loop):
    required = {"name", "promql", "threshold", "compare", "symptom_template"}
    for query in loop.QUERIES:
        assert required <= query.keys(), f"query {query['name']} is missing required keys"


def test_query_severity_defaults(loop):
    severities = {query["name"]: query.get("severity") for query in loop.QUERIES}
    assert severities["backend_cpu_cores"] == "strong"
    assert severities["backend_memory_utilization"] == "strong"
    assert severities["backend_ready_replicas"] == "strong"
    assert severities["backend_warn_error_logs"] == "weak"


def test_ready_replicas_uses_lt_compare(loop):
    query = next(query for query in loop.QUERIES if query["name"] == "backend_ready_replicas")
    assert query["compare"] == "lt"


@pytest.mark.parametrize(
    "compare,value,threshold,expected",
    [
        ("gt", 1.0, 0.5, True),
        ("gt", 0.3, 0.5, False),
        ("lt", 60.0, 80.0, True),
        ("lt", 90.0, 80.0, False),
    ],
)
def test_breach_logic(loop, compare, value, threshold, expected):
    assert loop._breached(value, threshold, compare) == expected


@pytest.mark.asyncio
async def test_query_returns_none_on_http_error(loop):
    with patch("observer.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.side_effect = Exception("connection refused")

        result = await loop._query("up")
        assert result is None


@pytest.mark.asyncio
async def test_query_returns_zero_on_empty_result(loop):
    with patch("observer.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": {"result": []}}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await loop._query("up")
        assert result == 0.0


@pytest.mark.asyncio
async def test_query_returns_zero_on_nan(loop):
    with patch("observer.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": {"result": [{"value": [0, "NaN"]}]}
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await loop._query("up")
        assert result == 0.0


def test_cooldown_logic(loop):
    signal = "backend_warn_error_logs"
    assert loop._is_in_cooldown(signal) is False
    loop._last_triggered_at[signal] = 0.0
    # no assertion for absolute monotonic time; just verify explicit recent marker works
    loop._last_triggered_at[signal] = __import__("time").monotonic()
    assert loop._is_in_cooldown(signal) is True
