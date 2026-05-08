from agents.rca import _expand_mcp_value
from core.config import settings


def test_expand_mcp_value_replaces_known_placeholders():
    assert _expand_mcp_value("AWS_REGION=${AWS_REGION}") == (
        f"AWS_REGION={settings.AWS_REGION}"
    )
    assert _expand_mcp_value("${EKS_CLUSTER_NAME}") == settings.EKS_CLUSTER_NAME


def test_expand_mcp_value_leaves_unknown_placeholders():
    assert _expand_mcp_value("${UNKNOWN}") == "${UNKNOWN}"
