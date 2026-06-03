import pytest

from tool_server.tables import render_latex_compatible_table_svg, render_table_svg


def test_table_svg_derives_sorted_columns_and_hashes_payload():
    rows = [
        {"metric": "Revenue", "value": "$42M"},
        {"value": "18%", "metric": "Margin"},
    ]

    payload = render_table_svg(rows, title="KPIs").as_payload()

    assert payload["kind"] == "table.svg"
    assert payload["mime_type"] == "image/svg+xml"
    assert payload["metadata"]["columns"] == ["metric", "value"]
    assert payload["metadata"]["row_count"] == 2
    assert "Revenue" in payload["body"]
    assert "Margin" in payload["body"]


def test_table_svg_respects_explicit_column_order():
    artifact = render_table_svg(
        [{"metric": "Revenue", "value": "$42M"}],
        columns=["value", "metric"],
    )

    assert artifact.metadata["columns"] == ["value", "metric"]
    assert artifact.body.index("value") < artifact.body.index("metric")


def test_table_svg_rejects_empty_rows():
    with pytest.raises(ValueError, match="rows"):
        render_table_svg([])


def test_latex_adapter_preserves_table_contract():
    artifact = render_latex_compatible_table_svg([{"a": 1}])

    assert artifact.kind == "table.svg"
    assert artifact.metadata["adapter"] == "latex-compatible"
    assert artifact.body.startswith("<svg")
