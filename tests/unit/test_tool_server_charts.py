import pytest

from tool_server.charts import render_bar_chart_svg, render_echarts_bar_svg


def test_bar_chart_svg_is_deterministic_and_vector_only():
    data = [
        {"label": "Revenue", "value": 42},
        {"label": "Margin", "value": 18},
    ]

    first = render_bar_chart_svg(data, title="Financial summary").as_payload()
    second = render_bar_chart_svg(reversed(data), title="Financial summary").as_payload()

    assert first["mime_type"] == "image/svg+xml"
    assert first["content_hash"] == second["content_hash"]
    assert first["metadata"]["row_count"] == 2
    assert '<svg xmlns="http://www.w3.org/2000/svg"' in first["body"]
    assert 'data-label="Margin"' in first["body"]
    assert "Financial summary" in first["body"]


def test_chart_rejects_negative_values():
    with pytest.raises(ValueError, match="non-negative"):
        render_bar_chart_svg([{"label": "Loss", "value": -1}])


def test_echarts_adapter_preserves_svg_contract():
    artifact = render_echarts_bar_svg([("A", 1), ("B", 2)])

    assert artifact.kind == "chart.bar"
    assert artifact.metadata["adapter"] == "echarts-compatible"
    assert artifact.body.startswith("<svg")
